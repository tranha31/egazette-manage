import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import Icon from "./Icon";

type Tone = "ok" | "bad" | "info";
interface ToastItem {
  id: number;
  text: string;
  tone: Tone;
}

const ToastContext = createContext<(text: string, tone?: Tone) => void>(() => undefined);
export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>());

  const push = useCallback((text: string, tone: Tone = "ok") => {
    const id = next.current++;
    setItems((l) => [...l.slice(-3), { id, text, tone }]);
    const t = setTimeout(() => {
      setItems((l) => l.filter((x) => x.id !== id));
      timers.current.delete(t);
    }, tone === "bad" ? 7000 : 4000);
    timers.current.add(t);
  }, []);

  useEffect(() => {
    const all = timers.current;
    return () => all.forEach(clearTimeout);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.tone}`}>
            <Icon name={t.tone === "bad" ? "alert" : t.tone === "ok" ? "checkCircle" : "info"} />
            <span>{t.text}</span>
            <button className="icon-btn" aria-label="Đóng" onClick={() => setItems((l) => l.filter((x) => x.id !== t.id))}>
              <Icon name="x" size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
