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

前端（M4 延后）、AI/LLM、Embedding/向量、RAG、MCP、Agent、sources 导入、
wiki 生成、知识图谱 UI、auth、任何 PostgreSQL/Redis/ES/Milvus/Qdrant/K8s 组件。