import { createContext, useContext, type ReactNode } from "react";
import type { Meta, Tone } from "./types";

const MetaContext = createContext<Meta | null>(null);

export function MetaProvider({ meta, children }: { meta: Meta; children: ReactNode }) {
  return <MetaContext.Provider value={meta}>{children}</MetaContext.Provider>;
}

export function useMeta(): Meta {
  const m = useContext(MetaContext);
  if (!m) throw new Error("useMeta phải nằm trong MetaProvider");
  return m;
}

/** Tên loại công bố từ mã (NEW -> "Đăng ký mới"). */
export function useTypeName() {
  const { types } = useMeta();
  return (code: string) => types.find((t) => t.code === code)?.name ?? code;
}

export function useStatus() {
  const { statuses } = useMeta();
  return (status: string): { label: string; tone: Tone } => statuses[status] ?? { label: status, tone: "muted" };
}
