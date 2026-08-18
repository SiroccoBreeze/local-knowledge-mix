# SQLite Schema 说明

> 与 `backend/app/db/schema.py` 中的 DDL 互为镜像。改 schema 必须两边同步。
> 数据库 = 派生物（invariant #2）。所有正文永远从 `raw/` 文件系统读取。

## 设计决策

- **contentless FTS5**：`docs_fts` 是 `content=''` 的无内容表 —— 只存倒排索引，
  数据库内没有任何正文副本。代价：`snippet()`/`highlight()` 不可用，Snippet 由
  API 在请求时读取文件自行生成（这反而强制"内容从文件读"，加固不变式 #1）。
- **contentless 维护**：不支持 `DELETE`/`UPDATE`，更新索引必须
  `<delete 命令>` → 重新 `INSERT`（scanner 的 `index.py` 已封装）。
- **tokenizer = trigram**（需求锁定）：零依赖支持中文子串式命中。
  注意：单 token 需 ≥3 个字符；不足 3 字符的查询词走 `LIKE` 兜底（仅标题 /
  headings / rel_path，正文不在兜底范围 —— 这是 contentless 的必然取舍）。

## 表

### meta

键值状态存储，索引/扫描自身的元信息。

| 键 | 含义 |
|---|---|
| `schema_version` | 当前 schema 版本（迁移用） |
| `last_scan_at` | 最近一次扫描完成时间（ISO8601 UTC） |
| `last_scan_report` | 最近一次 ScanReport（JSON） |

### documents —— 文档元数据（不含正文）

| 字段 | 说明 |
|---|---|
| id | 主键；FTS `docs_fts.rowid` 与之对齐 |
| rel_path | **业务主键**，相对 raw/ 的 POSIX 路径；UNIQUE |
| doc_type | 当前恒为 `markdown`；未来扩 sources-* |
| title | `frontmatter.title` > 首个 H1 > 文件名（去扩展名）优先级 |
| sha256 | 内容哈希，差异检测核心 |
| mtime_ns / size | 快速跳过通道（mtime+size 相同则信任不重扫；`--full` 全量重扫） |
| word_count / char_count / line_count | 统计 |
| frontmatter | YAML 元数据（转 JSON 字符串，可为 NULL）—— 只存元数据 |
| headings | JSON 数组 `[{"level":2,"text":"..."}]` |
| first_seen / last_seen / last_indexed | ISO8601 UTC 时间戳 |
| status | `indexed` / `missing` / `failed` |
| scan_error | `failed` 时的原因快照 |

### links —— 文档间链接（图谱的边，P2 直接复用）

| 字段 | 说明 |
|---|---|
| from_doc / to_doc | FK → documents(id)；`to_doc=NULL` 表示目标不存在（断链） |
| target | 笔记中链接的原文 |
| kind | `wiki` / `relative` / `url` |
| UNIQUE(from_doc, target) | 重复链接去重 |

解析规则：
- `[[Target]]`（可选 `[[Target|alias]]`）：按 rel_path 全文/去 `.md`、文件名唯一、
  stem 唯一、title 唯一的顺序解析，都不唯一则 NULL（断链）。
- `[text](relative.md)`：相对当前文件所在目录解析，逃逸出 raw/ 则 NULL。
- `https?://` 链接：to_doc 恒为 NULL（外部资源）。
- 图片 `![...](x.png)` 与非 `.md` 相对目标：不记录为文档链接（走 assets）。

### assets —— 被 Markdown 引用的媒体/附件索引（V0.3）

> 文件**永远只存在于 raw/**，这里只是索引。同一文件被 N 篇文档引用 → N 行。

| 字段 | 说明 |
|---|---|
| id | 主键 |
| document_id | FK → documents(id)，引用它的文档 |
| relative_path | 解析后的相对 raw/ 路径（`../assets/x.png` → `assets/x.png`） |
| filename / extension | 文件名与小写扩展名（含点） |
| mime_type / size / sha256 / mtime_ns / modified_at | 文件元数据与内容哈希 |
| status | `indexed`（文件在）/ `missing`（文件被删，引用仍在） |
| last_seen | 最近一次确认时间 |
| UNIQUE(document_id, relative_path) | 去重 |

维护规则（跟随增量扫描）：
- 文件内容变化 → 哈希/大小/mtime 自动更新（mtime+size 一致时不重读文件）。
- 文件被删 → 行保留、`status='missing'`；重新出现 → 自愈回 `indexed` 并带新哈希。
- 文档撤掉引用 → 该行被修剪（其他文档的引用不受影响）。

被识别为 Asset 的扩展名白名单（与 `/raw/` 端点共用）：
`png jpg jpeg gif webp avif bmp ico svg pdf doc docx xls xlsx ppt pptx zip txt csv`。

### docs_fts —— contentless FTS5 索引

```sql
CREATE VIRTUAL TABLE docs_fts USING fts5(
    title, body, headings,
    content='',            -- contentless：无正文副本
    tokenize='trigram'
);
```

`rowid` = documents.id。搜索时 join documents 且过滤 `status NOT IN ('missing','failed')`。
排名用 `bm25(docs_fts, 1.5, 1.0, 1.2)`（title > body ≈ headings），升序取小。

## PRAGMA

- `journal_mode = WAL`：扫描写入与 API 读取并发友好（同机个人库足够）。
- `synchronous = NORMAL`。
- `foreign_keys = ON`：documents.id 重指派前会先重定向 links（rename 检测流程）。