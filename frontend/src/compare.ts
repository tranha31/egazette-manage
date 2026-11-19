// Ghép các nhóm "[CŨ] X" và "[MỚI] X" của một bố cáo thành bảng so sánh.
// Dữ liệu vào là `groups` của /api/announcements/{id}: [{name, fields:[{key, value}]}].
export interface Field {
  key: string;
  value: string;
}
export interface Group {
  name: string;
  fields: Field[];
}

export type RowStatus = "same" | "changed" | "added" | "removed";

export interface CompareRow {
  key: string;
  oldValue: string | null; // null = bên cũ không có dòng này
  newValue: string | null;
  status: RowStatus;
}

export interface CompareSection {
  id: string;
  title: string;
  rows: CompareRow[];
  /** số dòng khác nhau (changed + added + removed) */
  changed: number;
  /** nhóm chỉ có ở một bên */
  side: "both" | "old" | "new";
}

export interface Comparison {
  general: Group[]; // các nhóm không có tiền tố [CŨ]/[MỚI] (thông tin chung, người đại diện...)
  sections: CompareSection[];
  changed: number;
  total: number;
}

const PREFIX = /^\[(CŨ|MỚI)\]\s*/;
const LIST_KEY = /^(.*\S)\s+#\d+$/;

const squash = (s: string) => s.replace(/\s+/g, " ").trim();
// "Thông tin cổ phần" (mẫu cũ) và "Thông tin về cổ phần" (mẫu mới) là cùng một mục
const sectionId = (title: string) => squash(title).toLowerCase().replace(/\bvề\s+/g, "");

/**
 * Hợp của hai danh sách, giữ thứ tự của `a`; phần tử chỉ có ở `b` được chèn ngay sau phần tử đứng trước nó trong `b`
 * (và sau các phần tử chỉ có ở `a` nằm cùng chỗ, nên "bớt" luôn hiện trước "thêm" như diff thông thường).
 */
export function orderedUnion(a: string[], b: string[]): string[] {
  const out = [...a];
  const inB = new Set(b);
  let prev = -1;
  for (const id of b) {
    const at = out.indexOf(id);
    if (at >= 0) {
      prev = at;
      continue;
    }
    let idx = prev + 1;
    while (idx < out.length && !inB.has(out[idx])) idx++;
    out.splice(idx, 0, id);
    prev = idx;
  }
  return out;
}

interface Item {
  id: string;
  label: string;
  value: string;
}

function toItems(fields: Field[], listMode: boolean): Item[] {
  const seen = new Map<string, number>();
  return fields.map((f) => {
    const base = listMode ? (LIST_KEY.exec(f.key)?.[1] ?? f.key) : f.key;
    // Danh sách: nhận diện theo mã ngành (nếu có) hoặc nội dung, không theo số thứ tự.
    // Cùng mã ngành nhưng đổi tên/diễn giải thì là "đã đổi" chứ không phải "bỏ + thêm".
    const code = listMode ? /^\s*(\d{3,5})\b/.exec(f.value)?.[1] : undefined;
    const idKey = listMode ? (code ?? squash(f.value)) : base;
    const n = seen.get(idKey) ?? 0;
    seen.set(idKey, n + 1);
    return { id: `${idKey}\u0000${n}`, label: base, value: f.value };
  });
}

function compareFields(oldF: Field[], newF: Field[]): CompareRow[] {
  const all = [...oldF, ...newF];
  // Chế độ danh sách (ngành nghề #1, #2...): thêm/bớt một ngành làm lệch số thứ tự nên phải so theo nội dung
  const listMode = all.length > 0 && all.every((f) => LIST_KEY.test(f.key));
  const o = toItems(oldF, listMode);
  const n = toItems(newF, listMode);
  const om = new Map(o.map((i) => [i.id, i]));
  const nm = new Map(n.map((i) => [i.id, i]));
  return orderedUnion(o.map((i) => i.id), n.map((i) => i.id)).map((id) => {
    const a = om.get(id);
    const b = nm.get(id);
    const label = (b ?? a)!.label;
    if (a && b) {
      return { key: label, oldValue: a.value, newValue: b.value, status: squash(a.value) === squash(b.value) ? "same" : "changed" };
    }
    return a
      ? { key: label, oldValue: a.value, newValue: null, status: "removed" }
      : { key: label, oldValue: null, newValue: b!.value, status: "added" };
  });
}

export function buildComparison(groups: Group[]): Comparison {
  const general: Group[] = [];
  const order: string[] = [];
  const bucket = new Map<string, { title: string; old: Field[]; new: Field[]; hasOld: boolean; hasNew: boolean }>();

  for (const g of groups) {
    const m = PREFIX.exec(g.name);
    if (!m) {
      general.push(g);
      continue;
    }
    const title = g.name.replace(PREFIX, "");
    const id = sectionId(title);
    let b = bucket.get(id);
    if (!b) {
      b = { title, old: [], new: [], hasOld: false, hasNew: false };
      bucket.set(id, b);
      order.push(id);
    }
    if (m[1] === "CŨ") {
      b.old.push(...g.fields);
      b.hasOld = true;
    } else {
      b.new.push(...g.fields);
      b.hasNew = true;
      b.title = title; // ưu tiên tên của bản mới
    }
  }

  const sections: CompareSection[] = order.map((id) => {
    const b = bucket.get(id)!;
    const rows = compareFields(b.old, b.new);
    return {
      id,
      title: b.title,
      rows,
      changed: rows.filter((r) => r.status !== "same").length,
      side: b.hasOld && b.hasNew ? "both" : b.hasOld ? "old" : "new",
    };
  });
  return {
    general,
    sections,
    changed: sections.reduce((s, x) => s + x.changed, 0),
    total: sections.reduce((s, x) => s + x.rows.length, 0),
  };
}

export interface Part {
  text: string;
  mark: boolean;
}

const MAX_LCS_CELLS = 90_000;

/** Gộp các token liên tiếp cùng trạng thái thành các đoạn; khoảng trắng chỉ được đánh dấu khi nằm giữa hai từ cùng bị đánh dấu. */
function toParts(tokens: string[], marked: boolean[]): Part[] {
  const m = marked.map((x, k) => (/^\s+$/.test(tokens[k]) ? k > 0 && k < tokens.length - 1 && marked[k - 1] && marked[k + 1] : x));
  const parts: Part[] = [];
  tokens.forEach((t, k) => {
    const last = parts[parts.length - 1];
    if (last && last.mark === m[k]) last.text += t;
    else parts.push({ text: t, mark: m[k] });
  });
  return parts;
}

/**
 * Làm nổi các từ khác nhau giữa hai chuỗi (so theo từ, dùng dãy con chung dài nhất).
 * Chuỗi quá dài thì chỉ bỏ phần đầu/cuối giống nhau và đánh dấu phần giữa.
 */
export function diffWords(a: string, b: string): { old: Part[]; new: Part[] } {
  const ta = a.split(/(\s+)/).filter((x) => x !== "");
  const tb = b.split(/(\s+)/).filter((x) => x !== "");
  const n = ta.length;
  const m = tb.length;
  const markA = new Array<boolean>(n).fill(true);
  const markB = new Array<boolean>(m).fill(true);

  if (n * m > MAX_LCS_CELLS) {
    let p = 0;
    while (p < n && p < m && ta[p] === tb[p]) p++;
    let s = 0;
    while (s < n - p && s < m - p && ta[n - 1 - s] === tb[m - 1 - s]) s++;
    for (let i = 0; i < p; i++) markA[i] = markB[i] = false;
    for (let i = 0; i < s; i++) {
      markA[n - 1 - i] = false;
      markB[m - 1 - i] = false;
    }
  } else {
    const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i--) {
      for (let j = m - 1; j >= 0; j--) {
        dp[i][j] = ta[i] === tb[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
    let i = 0;
    let j = 0;
    while (i < n && j < m) {
      if (ta[i] === tb[j]) {
        markA[i] = markB[j] = false;
        i++;
        j++;
      } else if (dp[i + 1][j] >= dp[i][j + 1]) i++;
      else j++;
    }
  }
  return { old: toParts(ta, markA), new: toParts(tb, markB) };
}
