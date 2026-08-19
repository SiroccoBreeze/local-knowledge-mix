import { DocRow, itemOf, type ListItem } from "./DocRow";

interface Props {
  title: string;
  items: ListItem[];
  empty?: string;
  onOpen: (id: number, relPath: string) => void;
}

export { itemOf };

export function ListView({ title, items, empty, onOpen }: Props) {
  return (
    <div className="page-wrap">
      <h2 className="page-title">{title}</h2>
      {items.length === 0 ? (
        <div className="list-empty">{empty ?? "这里还没有文档。"}</div>
      ) : (
        <div className="doc-list">
          {items.map((it) => (
            <DocRow key={it.id} item={it} onOpen={onOpen} />
          ))}
        </div>
      )}
    </div>
  );
}