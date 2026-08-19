# Local Knowledge

个人 Local-first AI Knowledge Base —— 单机、轻量、可长期 DIY 维护。

## 核心不变量

- `raw/` 是你的 Markdown 资产，**唯一可信源，系统一切组件对它只读**。
- SQLite 只作索引/元数据（contentless FTS5，无正文副本）。
- **恢复 = 重建索引**：删掉 `data/knowledge.db`，再 `python -m scripts.scan --full`，一切恢复。

详见 [system/purpose.md](system/purpose.md) 与 [system/schema.md](system/schema.md)。

## 快速开始

```bash
cd backend
/usr/bin/python3.12 -m venv .venv          # 首次（若系统为 3.10 默认，显式指定 3.12）
.venv/bin/pip install --upgrade pip
# PyPI 直连慢/超时的话，把源换成清华镜像：
# .venv/bin/pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
.venv/bin/pip install -e ".[dev]"          # 首次

# 1) 把你的 Markdown 放进 ../raw/（不动现有文件）
# 2) 建立索引（首次）
.venv/bin/python -m scripts.scan --full

# 3) 启动 API（默认 127.0.0.1:8000，OpenAPI 在 /docs）
.venv/bin/python -m scripts.serve
```

日常增量扫描：`.venv/bin/python -m scripts.scan`（几万文件也在毫秒级）。

## Knowledge Browser（V0.2）

本地 Web 知识库浏览器（React + TypeScript + Vite，无 UI 框架）：

```bash
# 终端 1：启动后端 API
cd backend && .venv/bin/python -m scripts.serve

# 终端 2：启动前端（开发模式，自动代理 /api → 8000）
cd frontend && npm install && npm run dev
# 打开 http://127.0.0.1:5173
```

功能：左侧目录树、中间文档列表（标题/路径/分类/修改时间）、顶部全局搜索
（实时结果 + `<mark>` 高亮 + 行号）、右侧 Markdown 阅读器
（标题/表格/代码块/图片/相对链接/WikiLink/引用/列表；点击相对/WikiLink 直接跳转）。

生产构建：`cd frontend && npm run build`（产物在 `dist/`，可 `npm run preview`）。

## V0.3：Assets + Share（单一端口）

增量扫描会自动把 Markdown 引用的媒体/附件建成 **Asset 索引**（白名单：
png/jpg/gif/webp/avif/bmp/ico/svg/pdf/doc/xls/ppt/zip/txt/csv；只索引、不复制、不移动、
不改 raw/）。`npm run build` 后，**后端直接托管前端**——一个端口全通：

```bash
cd backend && .venv/bin/python -m scripts.serve --host 0.0.0.0
# 打开 http://<本机IP>:8000
# 分享某篇文档（局域网只读）：http://<本机IP>:8000/share/<document_id>
```

新增 API：

- `GET /api/v1/documents/{id}/assets` — 文档引用的全部附件（含缺失标记）
- `GET /api/v1/assets/{id}` — 单个附件元数据
- `GET /api/v1/raw/{rel_path}` — 附件内容（白名单 + 防穿越 + nosniff；
  图片/pdf/txt 内联，office/zip 附件下载；Markdown 正文仅走 content 端点）

前端文档页：标题/分类/路径/修改时间 + 正文（标题/表格/代码块/图片/相对链接/
WikiLink/引用/列表）+ 图片与附件面板 + 出链/入链 + 同目录相关文档 + 一键复制分享地址。

## V0.4：MCP Read-only Knowledge Access

让 Claude Desktop / Claude Code / Cursor 等 MCP 客户端安全地检索并读取本地知识库。
**只读**：raw/ 唯一可信源、永不修改；SQLite 仍是派生索引；复用既有 search/service/scanner，
不引入 Embedding / 向量库 / 新存储。

```bash
cd backend
.venv/bin/python -m scripts.mcp        # stdio 启动，无需启动 Web 服务
```

### MCP Client 配置示例（三选一）

将 `<PY>` 换成实际路径：`/home/ub/WorkerSP/local-knowledge-mix/backend/.venv/bin/python`

- **Claude Desktop**（`claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "local-knowledge": {
      "command": "<PY>",
      "args": ["-m", "scripts.mcp"],
      "cwd": "/home/ub/WorkerSP/local-knowledge-mix/backend"
    }
  }
}
```

- **Claude Code**（项目根 `/home/ub/WorkerSP/local-knowledge-mix/.mcp.json`）：

```json
{
  "mcpServers": {
    "local-knowledge": {
      "command": "<PY>",
      "args": ["-m", "scripts.mcp"],
      "cwd": "/home/ub/WorkerSP/local-knowledge-mix/backend"
    }
  }
}
```

也可用命令注册：`claude mcp add local-knowledge --env -c -- <PY> -m scripts.mcp`。

- **Cursor**（项目根 `.cursor/mcp.json`）：同上（command/args/cwd）。

### 6 个只读工具

| 工具 | 作用 |
|---|---|
| `search_documents(query, limit?, offset?)` | FTS5 全文检索（复用现有搜索）；返回 doc_id/title/rel_path/score/纯文本 snippet + 行号 |
| `get_document(document_id)` | 元数据 + **实时从 raw/ 文件读取** 的完整正文（非 DB 副本） |
| `list_documents(q?, dir?, status?, limit?, offset?)` | 文档列表（同 REST /documents 过滤） |
| `get_document_links(document_id)` | 进出链；断链标记 `broken`、外链标记 `external` |
| `get_document_assets(document_id)` | 资产索引元数据（图片/附件） |
| `get_knowledge_stats()` | 文档/资产/链接/索引/缺失/最近扫描统计 |

安全：document_id 必校验；所有 raw/ 读取经 shared 路径守卫（防穿越/隐藏/绝对路径）；
无任意文件读取工具；不暴露 DB 文件与环境变量。

## API

`GET /api/v1/health` · `POST /api/v1/scan` · `GET /api/v1/scan/status`

`GET /api/v1/documents` · `GET /api/v1/documents/{id}` · `GET /api/v1/documents/{id}/content`

`GET /api/v1/documents/{id}/neighbors` · `GET /api/v1/search?q=` · `GET /api/v1/raw/{rel_path}`（图片等媒体，仅 raw/ 内白名单类型）

## 测试与检查

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/ruff check .
```

测试包含：`raw/` 扫描前后 SHA256 快照像素级一致（证明扫描器只读）、
删库重建恢复、中文内容、frontmatter 各种形态、增删改与重命名等。

## 已知限制

- 搜索分词为 trigram：单个查询词 ≥3 字符（更短词走标题/headings 的 LIKE 兜底）。
- 增量扫描以 `mtime_ns+size` 相同跳过重哈希；若文件被改而两值不变，
  索引会停留旧版 —— 需要强制可选 `--full`。正文唯一可信源始终是文件本身。
- 链接支持：`[[WikiLink]]`、相对 `.md` 路径、`https?://` URL；不含空格目标的链接。

## 阶段边界

已实现：M0–M3（扫描/索引/搜索/API）、V0.2（浏览器）、V0.3（Asset 索引 + 分享）、
V0.3.5（知识库阅读 UI）、V0.4（MCP 只读访问）。
未实现：AI 写作/总结/分类、Embedding/RAG、sources/wiki 管道、用户系统、
任何 PostgreSQL/Redis/ES/Milvus/Qdrant/K8s 组件。