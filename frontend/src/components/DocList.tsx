import { useMemo } from "react";

import { categoryOf, type DocMeta, dirOf } from "../api";
import { fmtTime } from "../docview";

interface Props {
  docs: DocMeta[];
  dir: string | null;
  onOpen: (id: number, relPath: string) => void;
}

export function DocList({ docs, dir, onOpen }: Props) {
  const items = useMemo(() => {
    const list = dir == null ? [...docs] : docs.filter((d) => dirOf(d.rel_path) === dir);
    // 最近修改的排前面
    list.sort((a, b) => b.mtime_ns - a.mtime_ns);
    return list;
  }, [docs, dir]);

  if (items.length === 0) {
    return <div className="hint">该目录下没有文档。</div>;
  }

  return (
    <table className="doc-list">
      <thead>
        <tr>
          <th>标题</th>
          <th>路径</th>
          <th>分类</th>
          <th>修改时间</th>
        </tr>
      </thead>
      <tbody>
        {items.map((doc) => (
          <tr key={doc.id} className="doc-row" onClick={() => onOpen(doc.id, doc.rel_path)}>
            <td className="doc-title">{doc.title || doc.rel_path}</td>
            <td className="doc-path">{doc.rel_path}</td>
            <td className="doc-category">{categoryOf(doc.rel_path)}</td>
            <td className="doc-time">{fmtTime(doc.mtime_ns)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}