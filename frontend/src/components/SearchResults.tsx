import type { SearchResult } from "../api";
import { fmtDate } from "../docview";
import { itemOf } from "./DocListView";

interface Props {
  results: SearchResult;
  onOpen: (id: number, relPath: string) => void;
}

export function SearchResults({ results, onOpen }: Props) {
  if (results.hits.length === 0) {
    return (
      <div className="search-page">
        <div className="search-count">没有匹配「{results.query}」的文档</div>
      </div>
    );
  }
  return (
    <div className="search-page">
      <div className="search-count">
        {results.total} 个结果 · “{results.query}”
      </div>
      <div className="search-results">
        {results.hits.map((hit) => {
          const it = itemOf(hit.doc);
          return (
            <button key={hit.doc.id} className="result" onClick={() => onOpen(it.id, it.relPath)}>
              <span className="result-title">{it.title}</span>
              <span className="doc-meta">
                <span className="doc-collection">{it.collection}</span>
                <span className="separator">·</span>
                <span className="doc-time">{fmtDate(it.modifiedAt)}</span>
              </span>
              {hit.snippets.map((s, i) => (
                <span key={i} className="result-snippet">
                  <span className="result-lines">
                    {s.start_line}–{s.end_line}
                  </span>{" "}
                  {s.text}
                </span>
              ))}
            </button>
          );
        })}
      </div>
    </div>
  );
}