/** 阅读内容：标题头 + Markdown（prose）+ 相关/附件/链接面板 + 灯箱。
 *  抽屉与分享页共用的完整文档渲染（API 数据流不变）。 */

import { useEffect, useMemo, useState } from "react";
import { Copy, ExternalLink, Share2, Star } from "lucide-react";

import {
  AssetPanel,
  LinkPanels,
  RelatedDocs,
  docHeaderOf,
  useDocData,
  useRelatedDocuments,
} from "../docview";
import { dedupeTitle, handleBodyClick, preprocessWiki, renderMarkdown, stripFrontmatter } from "../md";
import { useToast } from "./Toast";

interface Props {
  docId: number;
  favorite: boolean;
  onToggleFavorite: (id: number) => void;
  onOpen: (id: number, relPath: string) => void;
  onBack?: () => void;
  compact?: boolean; // 分享页：不带返回按钮
}

export function ReaderContent({ docId, favorite, onToggleFavorite, onOpen, onBack, compact }: Props) {
  const { meta, content, linkMap, assets, incoming, outgoing, error } = useDocData(docId);
  const related = useRelatedDocuments(docId);
  const toast = useToast();
  const [zoom, setZoom] = useState<{ src: string; alt: string } | null>(null);
  const relPath = meta?.rel_path ?? "";
  const header = meta ? docHeaderOf(meta) : null;

  const html = useMemo(() => {
    if (content === null || header === null) return "";
    let h = renderMarkdown({
      content: preprocessWiki(stripFrontmatter(content)),
      relPath,
      linkMap,
    });
    return dedupeTitle(h, header.title);
  }, [content, relPath, linkMap, header]);

  useEffect(() => {
    if (!zoom) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setZoom(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoom]);

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const hit = handleBodyClick(e);
    if (!hit) return;
    if (hit.said === "navigate" && hit.id !== undefined) onOpen(hit.id, hit.relPath ?? "");
    else if (hit.said === "copy") {
      navigator.clipboard?.writeText(hit.text ?? "").then(
        () => {
          const btn = (e.target as HTMLElement).closest("button.code-copy");
          if (btn) {
            const prev = btn.textContent;
            btn.textContent = "已复制 ✓";
            setTimeout(() => (btn.textContent = prev), 1200);
          }
        },
        () => undefined
      );
    } else if (hit.said === "zoom" && hit.src) setZoom({ src: hit.src, alt: hit.alt ?? "" });
  };

  const copyFull = () => {
    if (content == null) return;
    navigator.clipboard?.writeText(content).then(() => toast("✓ 已复制全文"), () => toast("复制失败"));
  };

  const share = () => {
    const url = `${window.location.origin}/share/${docId}`;
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(url);
    window.open(url, "_blank");
  };

  return (
    <div className="flex h-full flex-col">
      {/* 文档头 */}
      <div className={compact ? "px-5 pt-5 pb-3" : "px-5 pt-4 pb-3"}>
        {(onBack || compact) && (
          <div className="mb-2 flex items-center justify-between text-sm text-zinc-500 dark:text-zinc-400">
            {onBack ? (
              <button onClick={onBack} className="rounded-md px-2 py-1 -ml-2 transition-colors hover:bg-zinc-200/70 hover:text-zinc-800 dark:hover:bg-zinc-800 dark:hover:text-zinc-100">
                ← 返回
              </button>
            ) : (
              <span className="text-xs text-zinc-400">只读分享</span>
            )}
            <div className="flex items-center gap-1">
              <IconBtn title="复制原文" onClick={copyFull}>
                <Copy className="h-3.5 w-3.5" />
              </IconBtn>
              <IconBtn title="分享" onClick={share}>
                <Share2 className="h-3.5 w-3.5" />
              </IconBtn>
              <IconBtn title="收藏" onClick={() => onToggleFavorite(docId)} active={favorite}>
                <Star className={`h-3.5 w-3.5 ${favorite ? "fill-amber-400 text-amber-400" : ""}`} />
              </IconBtn>
              {!compact && (
                <a href={`/share/${docId}`} className="rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-zinc-200/70 hover:text-zinc-800 dark:hover:bg-zinc-800 dark:hover:text-zinc-100" title="新窗口打开">
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
              )}
            </div>
          </div>
        )}
        <h1 className="text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">{header?.title}</h1>
        <p className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[13px] text-zinc-500 dark:text-zinc-400">
          <span>{header?.category}</span>
          <span className="text-zinc-300 dark:text-zinc-600">·</span>
          <span>{header?.created ?? header?.modifiedAt}</span>
          {header?.knowledge && (
            <span className="rounded-full bg-emerald-500/10 px-2 py-px text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
              {header.knowledge}
            </span>
          )}
          {header && header.tags.length > 0 && (
            <span className="flex flex-wrap gap-x-2 gap-y-1">
              {header.tags.slice(0, 5).map((t) => (
                <span key={t} className="text-zinc-400 dark:text-zinc-500">
                  #{t}
                </span>
              ))}
            </span>
          )}
        </p>
        <details className="mt-2 text-[12px] text-zinc-400 dark:text-zinc-500">
          <summary className="cursor-pointer select-none text-[11px] uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
            更多信息
          </summary>
          <dl className="mt-1.5 grid grid-cols-[72px_1fr] gap-x-3 gap-y-1 font-mono text-[12px]">
            <dt className="text-zinc-400 dark:text-zinc-500">ID</dt>
            <dd className="break-all">{meta?.id}</dd>
            <dt className="text-zinc-400 dark:text-zinc-500">路径</dt>
            <dd className="break-all">{header?.relPath}</dd>
            <dt className="text-zinc-400 dark:text-zinc-500">状态</dt>
            <dd>{meta?.status}</dd>
            <dt className="text-zinc-400 dark:text-zinc-500">sha256</dt>
            <dd className="break-all">{meta?.sha256}</dd>
          </dl>
        </details>
      </div>

      {/* 正文 */}
      {error ? (
        <div className="px-5 py-12 text-center text-sm text-zinc-400">读取失败：{error}</div>
      ) : content === null ? (
        <SkeletonDoc />
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-16">
          <div
            className="prose-md markdown-body"
            dangerouslySetInnerHTML={{ __html: html }}
            onClick={handleClick}
          />
          {assets.length > 0 && <AssetPanel assets={assets} />}
          {(outgoing.length > 0 || incoming.length > 0) && (
            <LinkPanels outgoing={outgoing} incoming={incoming} onOpen={onOpen} />
          )}
          <RelatedDocs items={related.items} loading={related.loading} error={related.error} onOpen={onOpen} />
        </div>
      )}

      {zoom && (
        <div className="lightbox" onClick={() => setZoom(null)}>
          <img src={zoom.src} alt={zoom.alt} />
          {zoom.alt && <div className="lightbox-caption">{zoom.alt}</div>}
        </div>
      )}
    </div>
  );
}

function IconBtn({
  title,
  onClick,
  active,
  children,
}: {
  title: string;
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      className={`rounded-md p-1.5 transition-colors hover:bg-zinc-200/70 hover:text-zinc-800 dark:hover:bg-zinc-800 dark:hover:text-zinc-100 ${
        active ? "text-amber-500" : "text-zinc-500 dark:text-zinc-400"
      }`}
    >
      {children}
    </button>
  );
}

function SkeletonDoc() {
  return (
    <div className="flex-1 space-y-4 px-6 py-4">
      {[70, 100, 85, 92, 66].map((w, i) => (
        <div key={i} className="space-y-2">
          <div className={`h-3 rounded bg-zinc-200/70 dark:bg-zinc-800`} style={{ width: `${w}%` }} />
          <div className={`h-3 rounded bg-zinc-200/50 dark:bg-zinc-800/60`} style={{ width: `${Math.min(100, w + 12)}%` }} />
        </div>
      ))}
    </div>
  );
}