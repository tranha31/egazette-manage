import { Link } from "react-router-dom";
import { Async, Avatar, EmptyState, PageHeader, StatusBadge } from "../components/common";
import Icon, { type IconName } from "../components/Icon";
import { dmyhm } from "../format";
import { useApi, useTitle } from "../hooks";
import { useTypeName } from "../meta";
import type { Overview } from "../types";

function Kpi({ to, icon, tone, value, label }: { to?: string; icon: IconName; tone: string; value: number; label: string }) {
  const body = (
    <>
      <span className={`kpi-icon ${tone}`}><Icon name={icon} size={20} /></span>
      <div>
        <b>{value.toLocaleString("vi-VN")}</b>
        <span>{label}</span>
      </div>
    </>
  );
  return to ? <Link className="card kpi" to={to}>{body}</Link> : <div className="card kpi">{body}</div>;
}

export default function OverviewPage() {
  useTitle("Tổng quan");
  const typeName = useTypeName();
  const res = useApi<Overview>("/api/overview", 10000);
  return (
    <>
      <PageHeader
        title="Tổng quan"
        subtitle="Tình hình dữ liệu bố cáo đã thu thập"
        actions={<Link className="btn primary" to="/crawl"><Icon name="plus" size={16} />Crawl mới</Link>}
      />
      <Async res={res} rows={4}>
        {({ stats, jobs, latest }) => (
          <>
            <div className="kpis">
              <Kpi to="/search" icon="file" tone="indigo" value={stats.announcements} label="Bố cáo trong database" />
              <Kpi to="/companies" icon="building" tone="teal" value={stats.companies} label="Doanh nghiệp" />
              <Kpi icon="download" tone="amber" value={stats.pdf_ok} label="File PDF đã tải" />
              <Kpi to="/jobs" icon="clock" tone="rose" value={stats.queued} label="Công việc đang chờ / chạy" />
            </div>

            <div className="grid-2">
              <section className="card">
                <header className="card-head">
                  <h2>Bố cáo mới nhất</h2>
                  <Link to="/search" className="more">Xem tất cả <Icon name="arrowRight" size={14} /></Link>
                </header>
                {latest.length ? (
                  <ul className="rows">
                    {latest.map((a) => (
                      <li key={a.id}>
                        <Link to={`/announcements/${a.id}`} className="row-link">
                          <Avatar name={a.company_name || a.tax_code} />
                          <div className="row-main">
                            <b>{a.company_name || a.tax_code}</b>
                            <span className="muted"><span className="mono">{a.tax_code}</span> · {typeName(a.ann_type)}</span>
                          </div>
                          <time>{dmyhm(a.posted_at)}</time>
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState title="Chưa có bố cáo">Vào “Crawl mới” để lấy dữ liệu.</EmptyState>
                )}
              </section>

              <section className="card">
                <header className="card-head">
                  <h2>Công việc gần đây</h2>
                  <Link to="/jobs" className="more">Xem tất cả <Icon name="arrowRight" size={14} /></Link>
                </header>
                {jobs.length ? (
                  <ul className="rows">
                    {jobs.map((j) => (
                      <li key={j.id}>
                        <Link to={`/jobs/${j.id}`} className="row-link">
                          <span className="job-no">#{j.id}</span>
                          <div className="row-main">
                            <b className="mono">{j.tax_code}</b>
                            <span className="muted clamp">{j.message || j.ann_type}</span>
                          </div>
                          <StatusBadge status={j.status} />
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState icon="list" title="Chưa có công việc" />
                )}
              </section>
            </div>
          </>
        )}
      </Async>
    </>
  );
}
