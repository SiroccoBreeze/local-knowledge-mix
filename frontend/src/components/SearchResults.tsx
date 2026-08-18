import { type Hit, type SearchResult } from "../api";

interface Props {
  results: SearchResult;
  onOpen: (id: number, relPath: string) => void;
}

export function SearchResults({ results, onOpen }: Props) {
  if (results.hits.length === 0) {
    return <div className="hint">没有匹配「{results.query}」的文档。</div>;
  }
  return (
    <div className="search-results">
      {results.hits.map((hit) => (
        <SearchHitCard key={hit.doc.id} hit={hit} onOpen={onOpen} />
      ))}
    </div>
  );
}

function SearchHitCard({ hit, onOpen }: { hit: Hit; onOpen: Props["onOpen"] }) {
  return (
    <div
      className="result"
      onClick={() => onOpen(hit.doc.id, hit.doc.rel_path)}
      title="点击打开文档"
    >
      <div className="result-title">{hit.doc.title || hit.doc.rel_path}</div>
      <div className="result-path">
        {hit.doc.rel_path} · 第 {hit.snippets[0]?.start_line ?? "?"} 行
      </div>
      {hit.snippets.map((s, i) => (
        <div key={i} className="result-snippet">
          <span className="result-lines">
            {s.start_line}–{s.end_line}
          </span>{" "}
          {/* 后端已做 HTML 转义并把关键词包在 <mark> 中 */}
          <span dangerouslySetInnerHTML={{ __html: s.text }} />
        </div>
      ))}
    </div>
  );
}