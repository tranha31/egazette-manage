import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { get } from "./api";

export interface Resource<T> {
  data: T | null;
  error: string;
  loading: boolean;
  /** đang hiện dữ liệu của lần tải trước trong khi tải lần mới (chỉ khi keepPrevious) */
  stale: boolean;
  reload: () => void;
}

/**
 * Gọi GET khi `url` đổi (null = chưa gọi). `pollMs` > 0: tự làm mới định kỳ, giữ nguyên dữ liệu cũ nên không bị nháy.
 */
export function useApi<T>(
  url: string | null,
  poll: number | ((data: T | null) => number) = 0,
  keepPrevious = false,
): Resource<T> {
  const [state, setState] = useState<{ url: string | null; data: T | null; error: string }>({
    url: null,
    data: null,
    error: "",
  });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (url === null) return;
    const ctl = new AbortController();
    get<T>(url, ctl.signal)
      .then((data) => setState({ url, data, error: "" }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setState((s) => ({ url, data: s.url === url ? s.data : null, error: e.message }));
      });
    return () => ctl.abort();
  }, [url, tick]);

  // Dữ liệu của url cũ không được hiện cho url mới (tránh nháy kết quả trang trước khi đổi trang/bộ lọc)
  // (keepPrevious: danh sách phân trang giữ bảng cũ mờ đi cho đến khi có dữ liệu mới, không nháy khung chờ)
  const current = state.url === url;
  const stale = !current && keepPrevious && state.data !== null;
  const data = current || stale ? state.data : null;
  const error = current ? state.error : "";

  const pollMs = typeof poll === "function" ? poll(data) : poll;
  useEffect(() => {
    if (!pollMs || url === null) return;
    const id = setInterval(() => setTick((t) => t + 1), pollMs);
    return () => clearInterval(id);
  }, [pollMs, url]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading: url !== null && data === null && !error, stale, reload };
}

/**
 * Trạng thái danh sách phân trang phía server, lưu trên URL (?page=&per_page=&...bộ lọc).
 * `apply(params)` đặt bộ lọc mới (về trang 1, giữ cỡ trang); `query` là chuỗi để ghép vào đường dẫn API.
 */
export function useListQuery() {
  const [sp, setSp] = useSearchParams();
  const page = Math.max(Number(sp.get("page")) || 1, 1);
  const filters = new URLSearchParams(sp);
  filters.delete("page");
  filters.delete("per_page");
  const keep = (next: URLSearchParams) => {
    const per = sp.get("per_page");
    if (per) next.set("per_page", per);
    return next;
  };
  return {
    sp,
    page,
    query: sp.toString(),
    filters,
    filtersKey: filters.toString(),
    setFilter: (key: string, value: string) => {
      const n = keep(new URLSearchParams(filters));
      if (value) n.set(key, value);
      else n.delete(key);
      setSp(n);
    },
    apply: (params: URLSearchParams) => setSp(keep(params)),
    reset: () => setSp(keep(new URLSearchParams())),
    goPage: (p: number) => {
      const n = new URLSearchParams(sp);
      n.set("page", String(p));
      setSp(n);
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    setPerPage: (size: number) => {
      const n = new URLSearchParams(sp);
      n.set("per_page", String(size));
      n.delete("page");
      setSp(n);
    },
  };
}

type Theme = "light" | "dark";
const THEME_KEY = "egazette-theme";

/** Giao diện sáng/tối: mặc định theo hệ điều hành, người dùng đổi thì ghi nhớ trong trình duyệt. */
export function useTheme() {
  const system = () => (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const v = localStorage.getItem(THEME_KEY);
      if (v === "light" || v === "dark") return v;
    } catch {
      /* localStorage bị chặn */
    }
    return system();
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      /* bỏ qua */
    }
  };
  return { theme, toggle };
}

/** Đọc các ô của <form> thành query (bỏ ô rỗng; checkbox chỉ có khi được tích). */
export function paramsFromForm(form: HTMLFormElement): URLSearchParams {
  const out = new URLSearchParams();
  new FormData(form).forEach((v, k) => {
    if (typeof v === "string" && v.trim() !== "") out.set(k, v.trim());
  });
  return out;
}

export function useTitle(title: string) {
  useEffect(() => {
    document.title = `${title} · Egazette`;
  }, [title]);
}
