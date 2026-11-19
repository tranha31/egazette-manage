import { useEffect, useMemo, useState } from "react";
import Icon from "./Icon";

export const PAGE_SIZES = [10, 25, 50, 100];

/** Dãy số trang rút gọn: 1 … 4 5 [6] 7 8 … 20 */
export function pageWindow(page: number, pages: number): (number | "…")[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);
  const set = new Set([1, 2, pages - 1, pages, page - 1, page, page + 1]);
  if (page <= 4) [3, 4, 5].forEach((n) => set.add(n));
  if (page >= pages - 3) [pages - 2, pages - 3, pages - 4].forEach((n) => set.add(n));
  const nums = [...set].filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b);
  const out: (number | "…")[] = [];
  nums.forEach((n, i) => {
    if (i > 0 && n - nums[i - 1] > 1) out.push("…");
    out.push(n);
  });
  return out;
}

interface PagerProps {
  page: number;
  pages: number;
  total: number;
  perPage: number;
  onPage: (p: number) => void;
  onPerPage?: (n: number) => void;
  sizes?: number[];
  /** ẩn khi chỉ có một trang và không cho đổi cỡ trang (dùng cho bảng nhỏ phân trang phía client) */
  hideWhenSingle?: boolean;
}

export default function Pager({ page, pages, total, perPage, onPage, onPerPage, sizes = PAGE_SIZES, hideWhenSingle }: PagerProps) {
  if (hideWhenSingle && pages <= 1 && total <= Math.min(...sizes)) return null;
  const from = total === 0 ? 0 : (page - 1) * perPage + 1;
  const to = Math.min(page * perPage, total);
  const sizeOptions = sizes.includes(perPage) ? sizes : [...sizes, perPage].sort((a, b) => a - b);
  const go = (p: number) => onPage(Math.min(Math.max(p, 1), pages));

  return (
    <nav className="pager" aria-label="Phân trang">
      <span className="pager-info">
        {total === 0 ? "Không có dòng nào" : <>Hiển thị <b>{from}–{to}</b> / <b>{total}</b></>}
      </span>
      {pages > 1 && (
        <div className="pager-pages">
          <button className="pg" onClick={() => go(1)} disabled={page <= 1} aria-label="Trang đầu"><Icon name="chevsL" size={15} /></button>
          <button className="pg" onClick={() => go(page - 1)} disabled={page <= 1} aria-label="Trang trước"><Icon name="chevL" size={15} /></button>
          {pageWindow(page, pages).map((n, i) =>
            n === "…" ? (
              <span key={`e${i}`} className="pg gap">…</span>
            ) : (
              <button key={n} className={`pg${n === page ? " on" : ""}`} onClick={() => go(n)} aria-current={n === page ? "page" : undefined}>{n}</button>
            ),
          )}
          <button className="pg" onClick={() => go(page + 1)} disabled={page >= pages} aria-label="Trang sau"><Icon name="chevR" size={15} /></button>
          <button className="pg" onClick={() => go(pages)} disabled={page >= pages} aria-label="Trang cuối"><Icon name="chevsR" size={15} /></button>
        </div>
      )}
      {onPerPage && (
        <label className="pager-size">
          Mỗi trang
          <select value={perPage} onChange={(e) => onPerPage(Number(e.target.value))}>
            {sizeOptions.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      )}
    </nav>
  );
}

/** Phân trang phía client cho bảng đã có đủ dữ liệu trong bộ nhớ. */
export function usePaged<T>(items: T[], initialSize = 10) {
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(initialSize);
  const pages = Math.max(Math.ceil(items.length / size), 1);

  // đổi bộ lọc/dữ liệu làm số trang co lại: kéo về trang hợp lệ
  useEffect(() => {
    if (page > pages) setPage(pages);
  }, [page, pages]);

  const slice = useMemo(() => items.slice((page - 1) * size, page * size), [items, page, size]);
  const pagerProps = {
    page: Math.min(page, pages),
    pages,
    total: items.length,
    perPage: size,
    onPage: setPage,
    onPerPage: (n: number) => {
      setSize(n);
      setPage(1);
    },
    hideWhenSingle: true,
  };
  return { slice, pagerProps };
}
