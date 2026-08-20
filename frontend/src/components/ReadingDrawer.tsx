/** 右侧阅读抽屉：从 Feed 卡片滑出，专注阅读。 */

import { ReaderContent } from "./ReaderContent";

interface Props {
  docId: number;
  favorite: boolean;
  onToggleFavorite: (id: number) => void;
  onOpen: (id: number, relPath: string) => void;
  onClose: () => void;
}

export function ReadingDrawer({ docId, favorite, onToggleFavorite, onOpen, onClose }: Props) {
  return (
    <div className="fixed inset-0 z-50">
      <div className="fade-in absolute inset-0 bg-zinc-950/40 backdrop-blur-[1px]" onClick={onClose} />
      <div className="drawer-panel absolute right-0 top-0 flex h-full w-full max-w-[780px] flex-col border-l border-zinc-200/80 bg-zinc-50 shadow-2xl dark:border-zinc-800 dark:bg-zinc-950">
        <ReaderContent
          docId={docId}
          favorite={favorite}
          onToggleFavorite={onToggleFavorite}
          onOpen={onOpen}
          onBack={onClose}
        />
      </div>
    </div>
  );
}