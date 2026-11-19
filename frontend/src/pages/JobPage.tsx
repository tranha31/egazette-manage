import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Async, Crumbs, PageHeader, StatusBadge } from "../components/common";
import Icon from "../components/Icon";
import { useToast } from "../components/Toast";
import { dmyhm, range } from "../format";
import { useApi, useTitle } from "../hooks";
import { useTypeName } from "../meta";
import type { Job } from "../types";

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

export default function JobPage() {
  const { id } = useParams();
  useTitle(`Job #${id}`);
  const nav = useNavigate();
  const toast = useToast();
  const typeName = useTypeName();
  const res = useApi<Job>(`/api/jobs/${id}`, (j) => (j && ["queued", "running"].includes(j.status) ? 4000 : 0));

  const act = async (fn: () => Promise<Job>, ok: string, goToResult = false) => {
    try {
      const j = await fn();
      toast(ok);
      if (goToResult) nav(`/jobs/${j.id}`);
      else res.reload();
    } catch (e) {
      toast((e as Error).message, "bad");
    }
  };

  return (
    <Async res={res}>
      {(j) => (
        <>
          <Crumbs items={[["Công việc", "/jobs"], `Job #${j.id}`]} />
          <PageHeader
            title={<>Job #{j.id} <StatusBadge status={j.status} /></>}
            subtitle={<><span className="mono">{j.tax_code}</span> · {typeName(j.ann_type)}</>}
            actions={
              <>
                {["queued", "paused", "running"].includes(j.status) && (
                  <button className="btn" onClick={() => act(() => api.cancelJob(j.id), "Đã yêu cầu huỷ")}><Icon name="x" size={16} />Huỷ</button>
                )}
                {["failed", "done_warn", "cancelled", "paused"].includes(j.status) && (
                  <button className="btn primary" onClick={() => act(() => api.retryJob(j.id), "Đã tạo job chạy lại", true)}><Icon name="refresh" size={16} />Chạy lại</button>
                )}
                <Link className="btn" to={`/search?tax_code=${j.tax_code}&ann_type=${j.ann_type}`}>Xem dữ liệu</Link>
              </>
            }
          />

          <div className="stats">
            <Stat label="Bố cáo" value={<>{j.result_count}{j.new_count > 0 && <small> (+{j.new_count} mới)</small>}</>} />
            <Stat label="PDF tải được" value={j.pdf_ok} />
            <Stat label="PDF lỗi" value={j.pdf_fail} />
            <Stat label="Crawl lại bắt buộc" value={j.force ? "Có" : "Không"} />
          </div>

          <div className="grid-2">
            <section className="card">
              <header className="card-head"><h2>Khoảng thời gian</h2></header>
              <dl className="dl">
                <dt>Người dùng nhập</dt><dd>{range(j.req_from, j.req_to)}</dd>
                <dt>Gửi lên trang</dt><dd>{j.status === "skipped" ? "— (đã có trong database)" : range(j.crawl_from, j.crawl_to, "không lọc ngày")}</dd>
                <dt>Sẽ ghi nhận đã phủ</dt><dd>{j.cover_from ? range(j.cover_from, j.cover_to) : "—"}</dd>
              </dl>
            </section>
            <section className="card">
              <header className="card-head"><h2>Tiến trình</h2></header>
              <dl className="dl">
                <dt>Tạo lúc</dt><dd>{dmyhm(j.created_at)}</dd>
                <dt>Bắt đầu</dt><dd>{dmyhm(j.started_at) || "—"}</dd>
                <dt>Kết thúc</dt><dd>{dmyhm(j.finished_at) || "—"}</dd>
                <dt>Ghi chú</dt><dd>{j.message || "—"}</dd>
              </dl>
            </section>
          </div>

          <h2 className="section-title">Nhật ký</h2>
          <pre className="log">{j.log || "(chưa có)"}</pre>
        </>
      )}
    </Async>
  );
}
