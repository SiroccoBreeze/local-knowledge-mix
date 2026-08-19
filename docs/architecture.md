# 架构设计（第一阶段记录）

## 形态

```text
raw/  ──▶  Markdown Scanner（幂等快照对账器） ──▶  SQLite(contentless FTS5) ──▶  FastAPI
(只读)    手动 CLI / API 触发, 增量或 --full       (只读查询)                     127.0.0.1
```

- **Scanner 是"快照对账器"而非编译器**：每次运行把 raw/ 现状与 documents 表对账，
  输出 ScanReport。天然幂等、可随时重跑、永远以磁盘为准。
- **单进程模型**：FastAPI 常驻，扫描在请求线程中执行（SQLite 单写者自带互斥）。
  无 worker / 队列 / 消息总线。
- **正文永不入库**：
  - 元数据（documents）、链接（links）、FTS 倒排索引（contentless）入 SQLite；
  - snippet 由 API 在请求时读取 raw/ 文件并自行计算（LRU 按 inode+mtime 过期）；
  - `/documents/{id}/content` 每次从磁盘读文件（ETag 由 mtime+sha 决定）。

## 扫描流程

1. 遍历 raw/（忽略隐藏项/已知目录，仅 `.md`，不跟随符号链接；路径 resolve 判根防逃逸）。
2. 快速通道：`mtime_ns + size` 与库一致 → unchanged，跳过。
3. 加速比对：`sha256` 不一致 → changed；一致仅刷 last_seen。
4. 新文件 → 解析（frontmatter / title / headings / 明文提取 / links）→ 入库 + FTS insert。
5. 单事务结束：缺失标记 `status='missing'`；rename 检测（sha 唯一配对，保留 doc id 与链接）；
   links 全量解析（两张表都齐后批量）。
6. 报告落 `meta.last_scan_report`。

## 搜索

- FTS5 trigram + `bm25(docs_fts, 1.5, 1.0, 1.2)`，join documents 过滤 missing/failed。
- 查询子集：`词1 词2` AND、`"短语"`、`-词` 排除；<3 字符词走标题/headings LIKE 兜底。
- snippet：读文件 → 明文 → 查询词定位 → 合并去重叠窗口 → `<mark>` 高亮 + 行号。

## 一致性 / 恢复

- 单事务 = 元数据与 FTS 原子一致；某文件解析异常仅标记 failed，不中断整轮。
- 备份策略：raw/ 在 git；`data/` 可删 → `--full` 重建。无迁移工具。

## 后续扩展（仅记录）

- sources/、wiki/：`doc_type` 区分来源，复用同一条扫描流水线，无新组件。
- MCP / Embedding：contentless 提供"按字节偏移定位 chunk"的能力，向量只定位不存文本。
- 知识图谱：links 表即图边。

## 第一阶段明确不做

前端浏览（V0.2 已补）、AI/LLM、Embedding/向量、RAG、MCP、Agent、sources 导入、
wiki 生成、知识图谱 UI、auth、任何 PostgreSQL/Redis/ES/Milvus/Qdrant/K8s 组件。

## V0.3：Assets + Share

- **Asset 索引**：`assets` 表 = 被 Markdown 引用的媒体/附件索引（一行 = 一篇文档
  对某个文件的引用）。扫描读阶段解析引用（宽松正则、忽略代码围栏）、resolve 判根、
  mtime+size 快速通道复用旧哈希；写阶段 upsert（修改/缺失/自愈）+ 按文档修剪。
  raw/ 依旧只读（有快照测试）。
- **API**：`/documents/{id}/assets`、`/assets/{id}`；`/raw/{rel_path}` 白名单扩到
  Asset 全类型（office/zip 附件下载头，图片/PDF/文本内联）。
- **分享**：`npm run build` 后后端托管前端 dist（StaticFiles + SPA fallback），
  `/share/{id}` 由前端 ShareView 渲染只读文档页（正文/图片/附件/出链/入链），
  单端口即可局域网访问。
- **前端**：阅读器升级为文档详情（标题/分类/路径/修改时间 + 图片/附件面板 +
  出链/入链 + 同目录相关文档）；`shareIdFrom()` 解析路径进入分享模式；
  分享页内部跳转走 pushState，前进/后退正常。

## V0.4：MCP Read-only Knowledge Access

- **形态**：官方 `mcp` SDK（FastMCP，v1.x，stdio 传输）单进程轻量入口
  `python -m scripts.mcp`；不要求 Web 服务在跑，直接读写同一个 `data/knowledge.db` 与 `raw/`。
- **复用而非重实现**：MCP 工具全部调用既有能力 —— `search/query.search`（FTS5+bm25）、
  新增的 **service 层**（`fetch_doc_row` / `list_documents` / `get_neighbors(include_broken=True)`
  / `doc_assets` / `knowledge_stats` / `raw_path_for`+`read_raw_bytes` 统一路径守卫）。
  REST 路由已改为同一 service 层薄调用，行为与响应结构不变（73 个既有测试保驾）。
- **只读保证**：6 个工具无写路径；无任意文件读取工具；document_id 必校验；
  正文永远从 raw/ 当前文件读（改文件+重扫 → MCP 立刻读到新内容，有测试）。
- **测试**：`tests/test_mcp.py` 用 FastMCP 进程内 `list_tools/call_tool` 端到端覆盖 6 工具
  + 断链/缺失资产/路径穿越/raw 逐字节不变/实时磁盘内容。

## V0.2：Knowledge Browser

- 前端：React + TS + Vite（`frontend/`，无 UI 框架，marked 渲染 markdown），
  开发模式经 Vite proxy 访问 `/api`。
- 阅读器：相对链接与 `[[WikiLink]]` 经 `GET /documents/{id}/neighbors` 的
  outgoing 精确映射到目标文档；图片相对路径在浏览器端解析为
  `GET /api/v1/raw/{rel_path}`（后端白名单 + 防穿越 + 不列目录）。
- API 仅新增上述一个只读端点；SQLite schema 未改动；raw/ 依然严格只读。

## V0.3.5：Knowledge Reader UI

- 阅读体验向 Obsidian/GitBook 靠拢：⌘K 命令面板搜索、入口式首页（最近访问）、
  标题去重（frontmatter title 与正文 H1 相同只显示一次）、Document Info 收进
  More 菜单、4/8/12/16/24/32/48/64 间距标尺与正文 400/标题分级字重。
- 本阶段仅改前端；backend/API/schema/scanner/raw 零改动。

## Roadmap 现状