// Định dạng hiển thị. Tự cắt chuỗi ISO, không dùng Date để tránh lệch múi giờ.
export function dmy(iso?: string | null): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? "");
  return m ? `${m[3]}/${m[2]}/${m[1]}` : "";
}

export function dmyhm(iso?: string | null): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):?(\d{2})?/.exec(iso ?? "");
  return m ? `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}:${m[6] ?? "00"}` : "";
}

export function range(from?: string | null, to?: string | null, empty = "tất cả"): string {
  if (!from && !to) return empty;
  return `${from ? dmy(from) : "…"} → ${to ? dmy(to) : "…"}`;
}

/** 333658 -> "325,8 KB" */
export function bytes(n?: number | null): string {
  if (!n || n < 0) return "";
  const units = ["B", "KB", "MB", "GB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${i === 0 ? v : v.toFixed(1).replace(".", ",")} ${units[i]}`;
}

/** Ghép query string, bỏ giá trị rỗng / false. */
export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    u.set(k, v === true ? "1" : String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}
