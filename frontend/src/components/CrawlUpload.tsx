import { useRef, useState, type DragEvent } from "react";
import { api, ApiError, templateUrl } from "../api";
import { dmy } from "../format";
import { useMeta } from "../meta";
import type { CrawlResponse, ImportResponse, ImportRow, Tone } from "../types";
import Icon from "./Icon";
import Pager, { usePaged } from "./Pager";
import { useToast } from "./Toast";

type Filter = "all" | "run" | "skip" | "error";

interface RowState {
  label: string;
  tone: Tone;
  kind: Filter;
}

function rowState(r: ImportRow): RowState {
  if (r.errors.length) return { label: "Lỗi", tone: "bad", kind: "error" };
  if (r.warnings.length) return { label: "Trùng", tone: "muted", kind: "skip" };
  if (r.to_run === 0) return { label: "Đã có", tone: "muted", kind: "skip" };
  if (r.to_skip > 0) return { label: `Một phần (${r.to_run}/${r.pairs.length})`, tone: "warn", kind: "run" };
  return { label: "Cần crawl", tone: "info", kind: "run" };
}

function TypesCell({ types, total }: { types: string[]; total: number }) {
  if (types.length === total) return <span className="tag">Tất cả ({total} loại)</span>;
  return <>{types.map((t) => <span key={t} className="tag gap-r">{t}</span>)}</>;
}

function Detail({ r }: { r: ImportRow }) {
  const [open, setOpen] = useState(false);
  if (r.errors.length) return <ul className="msg-list bad">{r.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>;
  return (
    <>
      {r.warnings.map((w, i) => <div key={i} className="msg warn"><Icon name="alert" size={14} />{w}</div>)}
      {r.pairs.length === 0 ? null : r.pairs.length === 1 ? (
        <span>{r.pairs[0].message}</span>
      ) : (
        <>
          <span>{r.to_run}/{r.pairs.length} loại cần crawl</span>{" "}
          <button type="button" className="link-btn" onClick={() => setOpen((o) => !o)}>{open ? "Ẩn" : "Chi tiết"}</button>
          {open && (
            <ul className="msg-list">
              {r.pairs.map((p) => (
                <li key={p.ann_type}><span className="tag gap-r">{p.ann_type}</span>{p.message}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </>
  );
}

export default function CrawlUpload({ onResult }: { onResult: (r: CrawlResponse) => void }) {
  const { types } = useMeta();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [data, setData] = useState<ImportResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");

  const rows = data?.rows ?? [];
  const shown = rows.filter((r) => filter === "all" || rowState(r).kind === filter);
  const { slice, pagerProps } = usePaged(shown, 10);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setError("");
    if (!/\.xlsx$/i.test(file.name)) {
      setError("Chỉ nhận file Excel .xlsx. Hãy tải file mẫu ở bước 1 và điền vào đó.");
      return;
    }
    setBusy(true);
    try {
      setData(await api.importFile(file));
      setFilter("all");
    } catch (e) {
      setData(null);
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";    // cho phép chọn lại đúng file đó sau khi sửa
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    void pick(e.dataTransfer.files[0]);
  };

  const submit = async () => {
    if (!data) return;
    setBusy(true);
    setError("");
    try {
      // Chỉ gửi dòng hợp lệ và không trùng; server kiểm tra lại toàn bộ
      const send = data.rows
        .filter((r) => !r.errors.length && !r.warnings.length)
        .map((r) => ({ tax_code: r.tax_code, types: r.types, date_from: r.date_from, date_to: r.date_to, force: r.force }));
      const res = await api.batch(send);
      toast(res.queued ? `Đã đưa ${res.queued} công việc vào hàng đợi` : "Tất cả đã có trong database, không cần crawl", res.queued ? "ok" : "info");
      onResult(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.errors.join(" ") : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const t = data?.totals;
  const dupes = rows.filter((r) => !r.errors.length && r.warnings.length).length;
  const counts: Record<Filter, number> = {
    all: rows.length,
    run: rows.filter((r) => rowState(r).kind === "run").length,
    skip: rows.filter((r) => rowState(r).kind === "skip").length,
    error: rows.filter((r) => rowState(r).kind === "error").length,
  };

  return (
    <div className="upload">
      <ol className="steps">
        <li className="card step">
          <span className="step-no">1</span>
          <div className="step-body">
            <h2>Tải file mẫu</h2>
            <p className="muted">File Excel gồm các cột <b>Mã số thuế</b>, <b>Loại công bố</b>, <b>Từ ngày</b>, <b>Đến ngày</b>, <b>Crawl lại</b>, kèm sheet hướng dẫn.</p>
            <a className="btn" href={templateUrl} download><Icon name="download" size={16} />Tải file mẫu (.xlsx)</a>
          </div>
        </li>
        <li className="card step">
          <span className="step-no">2</span>
          <div className="step-body">
            <h2>Tải file đã điền lên</h2>
            <p className="muted">Hệ thống kiểm tra từng dòng và cho xem trước dòng nào cần crawl, dòng nào đã có trong database. Chưa crawl gì cho đến khi bạn xác nhận.</p>
            <label
              className={`dropzone${drag ? " over" : ""}${busy ? " busy" : ""}`}
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)}
              onDrop={onDrop}
            >
              <input ref={input} type="file" accept=".xlsx" disabled={busy} onChange={(e) => void pick(e.target.files?.[0])} />
              <Icon name="cloud" size={26} />
              <b>{busy ? "Đang đọc file…" : "Kéo thả file vào đây hoặc bấm để chọn"}</b>
              <small>Chỉ nhận .xlsx, tối đa 5 MB, 500 dòng</small>
            </label>
          </div>
        </li>
      </ol>

      {error && <div className="alert bad"><Icon name="alert" /><div>{error}</div></div>}

      {data && t && (
        <section className="import-result">
          <header className="import-head">
            <div>
              <h2>Xem trước: {data.filename}</h2>
              <div className="stats mini">
                <div className="stat"><span>Dòng trong file</span><b>{t.rows}</b></div>
                <div className="stat"><span>Hợp lệ</span><b className="ok">{t.valid}</b></div>
                <div className="stat"><span>Dòng lỗi</span><b className={t.invalid ? "bad" : ""}>{t.invalid}</b></div>
                <div className="stat"><span>Sẽ crawl</span><b className="info">{t.to_run}</b><small> cặp MST × loại</small></div>
                <div className="stat"><span>Đã có, bỏ qua</span><b>{t.to_skip}</b></div>
              </div>
            </div>
          </header>

          {t.invalid > 0 && (
            <div className="alert warn"><Icon name="alert" /><div><b>{t.invalid} dòng lỗi sẽ bị bỏ qua.</b> Sửa trong file rồi tải lại, hoặc cứ crawl các dòng hợp lệ.</div></div>
          )}
          {dupes > 0 && (
            <div className="alert warn"><Icon name="alert" /><div>{dupes} dòng trùng dòng khác trong file, chỉ gửi một lần.</div></div>
          )}

          <div className="seg" role="tablist" aria-label="Lọc dòng">
            {([["all", "Tất cả"], ["run", "Cần crawl"], ["skip", "Đã có"], ["error", "Lỗi"]] as [Filter, string][]).map(([k, label]) => (
              <button key={k} className={filter === k ? "on" : ""} onClick={() => setFilter(k)}>{label} <span className="count">{counts[k]}</span></button>
            ))}
          </div>

          <div className="card table-card">
            <div className="table-wrap">
              <table>
                <thead><tr><th>Dòng</th><th>MST</th><th>Loại công bố</th><th>Khoảng ngày</th><th>Crawl lại</th><th>Trạng thái</th><th>Chi tiết</th></tr></thead>
                <tbody>
                  {slice.map((r) => {
                    const s = rowState(r);
                    return (
                      <tr key={r.line} className={r.errors.length ? "row-error" : undefined}>
                        <td className="muted">{r.line}</td>
                        <td className="mono">{r.tax_code || <span className="muted">—</span>}</td>
                        <td>{r.types.length ? <TypesCell types={r.types} total={types.length} /> : <span className="muted">—</span>}</td>
                        <td className="nowrap">
                          {r.date_from || r.date_to ? `${r.date_from ? dmy(r.date_from) : "…"} → ${r.date_to ? dmy(r.date_to) : "…"}` : "tất cả"}
                        </td>
                        <td>{r.force ? "Có" : <span className="muted">Không</span>}</td>
                        <td><span className={`badge ${s.tone}`}><i className="dot" />{s.label}</span></td>
                        <td className="wrap"><Detail r={r} /></td>
                      </tr>
                    );
                  })}
                  {!slice.length && <tr><td colSpan={7} className="muted center">Không có dòng nào.</td></tr>}
                </tbody>
              </table>
            </div>
            <Pager {...pagerProps} />
          </div>

          <div className="form-actions">
            <button className="btn" disabled={busy} onClick={() => { setData(null); setError(""); input.current?.click(); }}>
              <Icon name="refresh" size={16} />Chọn file khác
            </button>
            <button className="btn primary" disabled={busy || t.valid === 0 || t.to_run === 0} onClick={submit}
                    title={t.to_run === 0 ? "Tất cả đã có trong database, không có gì để crawl" : undefined}>
              <Icon name="cloud" size={16} />
              {t.to_run === 0 ? "Không có gì cần crawl" : `Crawl ${t.to_run} cặp (${t.valid - dupes} dòng)`}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
