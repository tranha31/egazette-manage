import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { PageHeader, StatusBadge } from "../components/common";
import CrawlUpload from "../components/CrawlUpload";
import Icon from "../components/Icon";
import Pager, { usePaged } from "../components/Pager";
import { useToast } from "../components/Toast";
import { useTitle } from "../hooks";
import { useMeta, useTypeName } from "../meta";
import type { CrawlRequest, CrawlResponse, PreviewItem, PreviewResponse, Tone } from "../types";

const PREVIEW: Record<string, { label: string; tone: Tone }> = {
  covered: { label: "Đã có", tone: "muted" },
  partial: { label: "Có một phần", tone: "warn" },
  missing: { label: "Chưa có", tone: "info" },
  forced: { label: "Crawl lại", tone: "info" },
  future: { label: "Tương lai", tone: "muted" },
};

const EMPTY: CrawlRequest = { tax_codes: "", types: ["AMEND"], date_from: "", date_to: "", force: false };

function PreviewTable({ items }: { items: PreviewItem[] }) {
  const { slice, pagerProps } = usePaged(items, 10);
  return (
    <div className="preview">
      <div className="table-wrap">
        <table>
          <thead><tr><th>MST</th><th>Loại</th><th>Kết quả</th><th>Chi tiết</th></tr></thead>
          <tbody>
            {slice.map((p) => {
              const s = PREVIEW[p.status] ?? { label: p.status, tone: "muted" as Tone };
              return (
                <tr key={`${p.tax_code}-${p.ann_type}`}>
                  <td className="mono">{p.tax_code}</td>
                  <td><span className="tag">{p.ann_type}</span></td>
                  <td><span className={`badge ${s.tone}`}><i className="dot" />{s.label}</span></td>
                  <td className="wrap">{p.message}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Pager {...pagerProps} />
    </div>
  );
}

function ResultTable({ result }: { result: CrawlResponse }) {
  const typeName = useTypeName();
  const { slice, pagerProps } = usePaged(result.results, 10);
  return (
    <>
      <div className="card table-card">
        <div className="table-wrap">
          <table>
            <thead><tr><th>MST</th><th>Loại công bố</th><th>Kết quả</th><th>Chi tiết</th></tr></thead>
            <tbody>
              {slice.map((r) => (
                <tr key={r.job.id}>
                  <td className="mono">{r.tax_code}</td>
                  <td>{typeName(r.ann_type)}</td>
                  <td><StatusBadge status={r.job.status} /></td>
                  <td className="wrap">
                    {r.job.message}
                    {r.needs_crawl && <> · <Link to={`/jobs/${r.job.id}`}>Job #{r.job.id}</Link></>}
                    {!r.needs_crawl && r.plan_status === "covered" && (
                      <> · <Link to={`/search?tax_code=${r.tax_code}&ann_type=${r.ann_type}`}>Xem dữ liệu</Link></>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pager {...pagerProps} />
      </div>
    </>
  );
}

export default function CrawlPage() {
  useTitle("Crawl mới");
  const { types } = useMeta();
  const toast = useToast();
  const [form, setForm] = useState<CrawlRequest>(EMPTY);
  const [errors, setErrors] = useState<string[]>([]);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [result, setResult] = useState<CrawlResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [sp, setSp] = useSearchParams();
  const mode = sp.get("mode") === "file" ? "file" : "manual";

  const set = <K extends keyof CrawlRequest>(k: K, v: CrawlRequest[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
    setPreview(null);
  };
  const toggleType = (code: string, on: boolean) =>
    set("types", on ? [...form.types, code] : form.types.filter((t) => t !== code));
  const codes = form.tax_codes.split(/[\s,;]+/).filter(Boolean).length;

  const run = async (kind: "preview" | "submit") => {
    setBusy(true);
    setErrors([]);
    try {
      if (kind === "preview") {
        const r = await api.preview(form);
        setPreview(r);
        const notes: string[] = [];
        if (r.invalid.length) notes.push(`Mã số thuế không hợp lệ (bị bỏ qua): ${r.invalid.join(", ")}`);
        if (r.truncated) notes.push("Chỉ xem trước 50 mã đầu tiên.");
        if (!r.items.length) notes.push("Hãy nhập mã số thuế hợp lệ và chọn loại công bố.");
        setErrors(notes);
      } else {
        const r = await api.crawl(form);
        setResult(r);
        toast(r.queued ? `Đã đưa ${r.queued} công việc vào hàng đợi` : "Tất cả đã có trong database, không cần crawl", r.queued ? "ok" : "info");
      }
    } catch (e) {
      setErrors(e instanceof ApiError ? e.errors : [(e as Error).message]);
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void run("submit");
  };

  if (result) {
    return (
      <>
        <PageHeader
          title="Kết quả kiểm tra"
          subtitle={<>{result.results.length} yêu cầu: <b>{result.queued}</b> vào hàng đợi · <b>{result.skipped}</b> bỏ qua vì đã có</>}
          actions={
            <>
              <button className="btn" onClick={() => { setResult(null); setForm(EMPTY); setPreview(null); }}>Nhập yêu cầu khác</button>
              <Link className="btn primary" to="/jobs">Xem hàng đợi <Icon name="arrowRight" size={15} /></Link>
            </>
          }
        />
        <ResultTable result={result} />
      </>
    );
  }

  return (
    <>
      <PageHeader title="Crawl mới" subtitle="Nhập mã số thuế, loại công bố và khoảng thời gian. Hệ thống chỉ crawl phần chưa có trong database." />
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={mode === "manual"} className={mode === "manual" ? "on" : ""} onClick={() => setSp({}, { replace: true })}>
          <Icon name="list" size={16} />Nhập thủ công
        </button>
        <button role="tab" aria-selected={mode === "file"} className={mode === "file" ? "on" : ""} onClick={() => setSp({ mode: "file" }, { replace: true })}>
          <Icon name="download" size={16} />Crawl hàng loạt từ file Excel
        </button>
      </div>
      {mode === "file" ? (
        <CrawlUpload onResult={setResult} />
      ) : (
      <div className="crawl-layout">
        <form className="card form" onSubmit={submit}>
          {errors.map((e, i) => <div key={i} className="alert bad"><Icon name="alert" /><div>{e}</div></div>)}

          <div className="field">
            <label htmlFor="tax">Mã số thuế <small>({codes} mã · mỗi mã một dòng, hoặc cách nhau bằng dấu cách / phẩy)</small></label>
            <textarea id="tax" rows={5} value={form.tax_codes} placeholder={"0101243150\n0100109106"} onChange={(e) => set("tax_codes", e.target.value)} />
          </div>

          <fieldset className="field">
            <legend>Loại công bố</legend>
            <div className="chips">
              <label className={`chip${form.types.includes("ALL") ? " on" : ""}`}>
                <input type="checkbox" checked={form.types.includes("ALL")} onChange={(e) => toggleType("ALL", e.target.checked)} />
                Tất cả các loại
              </label>
              {types.map((t) => (
                <label key={t.code} className={`chip${form.types.includes(t.code) ? " on" : ""}`} title={t.code}>
                  <input type="checkbox" checked={form.types.includes(t.code)} onChange={(e) => toggleType(t.code, e.target.checked)} />
                  {t.name}
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="field">
            <legend>Khoảng thời gian đăng bố cáo <small>(bỏ trống = tất cả từ trước đến nay)</small></legend>
            <div className="date-row">
              <label>Từ ngày <input type="date" value={form.date_from} onChange={(e) => set("date_from", e.target.value)} /></label>
              <Icon name="arrowRight" size={16} className="muted" />
              <label>Đến ngày <input type="date" value={form.date_to} onChange={(e) => set("date_to", e.target.value)} /></label>
            </div>
          </fieldset>

          <label className="switch">
            <input type="checkbox" checked={form.force} onChange={(e) => set("force", e.target.checked)} />
            <span className="track" />
            Bắt buộc crawl lại (bỏ qua kiểm tra database)
          </label>

          <div className="form-actions">
            <button type="button" className="btn" disabled={busy} onClick={() => run("preview")}>
              <Icon name="search" size={16} />Kiểm tra trước (không crawl)
            </button>
            <button type="submit" className="btn primary" disabled={busy}>
              <Icon name="cloud" size={16} />Kiểm tra &amp; crawl
            </button>
          </div>
          {preview && preview.items.length > 0 && <PreviewTable items={preview.items} />}
        </form>

        <aside className="card how">
          <h2>Cách hệ thống quyết định</h2>
          <ol>
            <li><b>Đã có trọn khoảng</b> → bỏ qua, không tốn captcha.</li>
            <li><b>Có một phần</b> → chỉ crawl phần còn thiếu.</li>
            <li><b>Hôm nay</b> chưa kết thúc nên chỉ được tính là đủ nếu vừa crawl trong vòng 60 phút.</li>
            <li>Chỉ ghi nhận “đã crawl” khi trang trả về bảng kết quả hợp lệ.</li>
          </ol>
          <p className="muted">Mỗi lần crawl tốn một lượt giải captcha trên 2captcha.</p>
        </aside>
      </div>
      )}
    </>
  );
}
