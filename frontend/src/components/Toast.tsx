/** 极简 Toast：顶部浮层提示（复制/收藏等操作的轻反馈）。 */

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";

const ToastCtx = createContext<(msg: string) => void>(() => {});

export function useToast() {
  return useContext(ToastCtx);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<{ id: number; msg: string }[]>([]);
  const seq = useRef(0);

  const push = useCallback((msg: string) => {
    const id = ++seq.current;
    setItems((prev) => [...prev, { id, msg }].slice(-3));
    setTimeout(() => setItems((prev) => prev.filter((i) => i.id !== id)), 2200);
  }, []);

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-6 left-1/2 z-[200] flex -translate-x-1/2 flex-col items-center gap-2">
        {items.map((i) => (
          <div
            key={i.id}
            className="fade-in rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 shadow-lg dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
          >
            {i.msg}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}