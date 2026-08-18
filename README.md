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
图片等媒体经 `GET /api/v1/raw/{rel_path}` 安全接口读取（仅 raw/ 内白名单类型、
防路径穿越、不暴露目录列表）。

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

现在只实现 M0–M3（扫描 / 索引 / 搜索 / API）。无前端、无 AI/LLM、
无 sources/ wiki/ 管道、无 MCP/Agent/Embedding。