interface Props {
  value: string;
  onChange: (q: string) => void;
  searching: boolean;
}

export function SearchBox({ value, onChange, searching }: Props) {
  return (
    <div className="search">
      <input
        type="search"
        placeholder="搜索全部文档…（如：sqlite 中文检索）"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete="off"
        spellCheck={false}
      />
      {searching && <span className="searching">⏳</span>}
      {value && !searching && (
        <button className="clear" onClick={() => onChange("")} title="清空">
          ✕
        </button>
      )}
    </div>
  );
}