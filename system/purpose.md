# 项目意图与不变式

个人 Local-first AI Knowledge Base —— 一个适合长期 DIY、单机、轻量维护的知识库。

## 三条不变式（不可妥协）

1. **raw/ 是唯一可信源（Source of Truth）。**
   Markdown 正文只存在于 `raw/` 的文件里。任何组件不得把正文作为"正式副本"搬进数据库。

2. **SQLite 是派生物（derived artifact）。**
   `data/knowledge.db` 只保存：元数据、headings、frontmatter、links、FTS 索引（contentless，无正文）。
   度量标准：**删掉 `data/knowledge.db` → `python -m scripts.scan --full` → 完整恢复**，
   不需要任何迁移或导回工具。

3. **系统内所有进程对 raw/ 只读。**
   扫描器、API、未来的 AI 子系统，对 raw/ 一律只读。
   未来 AI 写入只发生在 `wiki/`，且只能通过受管写入器进行。

## 第一阶段（当前）禁止清单

- 不做任何 AI / LLM 操作：总结、重写、分类、打标、问答。
- 不做任何写 raw/ 的代码路径：无编辑、删除、移动、重命名 API。
- 不做 sources/ 与 wiki/ 的导入与生成管道（目录仅占位）。
- 不做 Embedding / 向量检索 / RAG / 知识图谱 UI。
- 不做 MCP / Agent。
- 不做多用户、auth、云同步。
- 不引入 PostgreSQL / Redis / Elasticsearch / Milvus / Qdrant / Kubernetes。
- 不为"未来扩展"预埋抽象层。

## 路线图（只做记录，不在本阶段实现）

- P2（已部分完成）：`sources/` 外部资料导入；`wiki/` AI 生成区（未开始）。
- P3（部分完成）：**MCP 只读访问（V0.4 已完成）**、Embedding / 向量检索
  （contentless 按字节偏移定位 chunk，未开始）、知识图谱（未开始）。