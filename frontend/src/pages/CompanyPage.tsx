import { Link, useParams, useSearchParams } from "react-router-dom";
import { fileUrl } from "../api";
import { Async, Avatar, Crumbs, EmptyState, Names, PdfLink } from "../components/common";
import Icon from "../components/Icon";
import Pager, { usePaged } from "../components/Pager";
import { dmy, dmyhm } from "../format";
import { useApi, useTitle } from "../hooks";
import { useTypeName } from "../meta";
import type { AnnouncementSummary, CompanyDetail, CoverageRow } from "../types";

function Announcements({ items }: { items: AnnouncementSummary[] }) {
  const typeName = useTypeName();
  const { slice, pagerProps } = usePaged(items, 10);
  return (
    <div className="card table-card">
      <div className="table-wrap">
        <table>
          <thead><tr><th>Ngày giờ đăng</th><th>Loại</th><th>Người đại diện</th><th>Vốn điều lệ</th><th>PDF</th><th /></tr></thead>
          <tbody>
            {slice.map((a) => (
              <tr key={a.id}>
                <td className="nowrap"><Link to={`/announcements/${a.id}`} className="strong">{dmyhm(a.posted_at)}</Link></td>
                <td><span className="tag">{typeName(a.ann_type)}</span></td>
                <td className="wrap"><Names reps={a.reps} /></td>
                <td className="nowrap">{a.charter_capital}</td>
                <td>{a.has_pdf ? <PdfLink href={fileUrl(a.id)} /> : <span className="muted">—</span>}</td>
                <td><Link to={`/announcements/${a.id}`} className="more">Chi tiết <Icon name="arrowRight" size={14} /></Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pager {...pagerProps} />
    </div>
  );
}

function Coverage({ rows }: { rows: CoverageRow[] }) {
  const { slice, pagerProps } = usePaged(rows, 10);
  if (!rows.length) return <EmptyState icon="calendar" title="Chưa có lần crawl nào được ghi nhận" />;
  return (
    <div className="card table-card">
      <div className="table-wrap">
        <table>
          <thead><tr><th>Loại</th><th>Khoảng đã crawl</th><th>Hiệu lực</th><th>Crawl lúc</th><th>Bố cáo</th></tr></thead>
          <tbody>
            {slice.map((c, i) => (
              <tr key={i}>
                <td><span className="tag">{c.ann_type}</span></td>
                <td className="nowrap">{dmy(c.date_from)} → {dmy(c.date_to)}</td>
                <td className="nowrap">
                  {c.effective ? <span className="badge ok"><i className="dot" />{dmy(c.effective.start)} → {dmy(c.effective.end)}</span> : <span className="muted">chưa đủ ngày nào</span>}
                </td>
                <td className="nowrap">{dmyhm(c.crawled_at)}</td>
                <td>{c.result_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pager {...pagerProps} />
    </div>
  );
}

export default function CompanyPage() {
  const { tax } = useParams();
  const [sp, setSp] = useSearchParams();
  const res = useApi<CompanyDetail>(`/api/companies/${tax}`);
  useTitle(res.data?.latest.company_name || tax || "Doanh nghiệp");
  const tab = sp.get("tab") === "coverage" ? "coverage" : "ann";

  return (
    <Async res={res}>
      {({ tax_code, latest, announcements, coverage }) => (
        <>
          <Crumbs items={[["Doanh nghiệp", "/companies"], tax_code]} />
          <header className="card hero">
            <Avatar name={latest.company_name || tax_code} size={56} square />
            <div className="hero-main">
              <h1>{latest.company_name || tax_code}</h1>
              <div className="hero-meta">
                <span className="mono">MST {tax_code}</span>
                {latest.established_date && <span><Icon name="calendar" size={14} />Thành lập {dmy(latest.established_date)}</span>}
                {latest.charter_capital && <span>Vốn điều lệ {latest.charter_capital}</span>}
              </div>
              {latest.hq_address && <p className="muted"><Icon name="map" size={14} /> {latest.hq_address}</p>}
            </div>
            <div className="hero-actions">
              <Link className="btn primary" to="/crawl"><Icon name="cloud" size={16} />Crawl bổ sung</Link>
            </div>
          </header>

          {latest.reps.length > 0 && (
            <section className="card pad">
              <h2 className="card-title">Người đại diện (mới nhất)</h2>
              <div className="people-row">
                {latest.reps.map((r, i) => (
                  <div key={i} className="person">
                    <Avatar name={r.full_name} size={40} />
                    <div>
                      <b>{r.full_name}</b>
                      <span className="muted">{r.position || "Người đại diện"}{r.id_number && <> · <span className="mono">{r.id_number}</span></>}</span>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          <div className="tabs" role="tablist">
            <button role="tab" aria-selected={tab === "ann"} className={tab === "ann" ? "on" : ""} onClick={() => setSp({}, { replace: true })}>
              Các bố cáo <span className="count">{announcements.length}</span>
            </button>
            <button role="tab" aria-selected={tab === "coverage"} className={tab === "coverage" ? "on" : ""} onClick={() => setSp({ tab: "coverage" }, { replace: true })}>
              Khoảng thời gian đã crawl <span className="count">{coverage.length}</span>
            </button>
          </div>

          {tab === "ann" ? (
            <Announcements items={announcements} />
          ) : (
            <>
              <p className="muted note">
                Dùng để quyết định có cần crawl lại hay không. “Hiệu lực” là khoảng được coi là đã đủ dữ liệu
                (ngày crawl chưa kết thúc nên chưa tính, trừ khi vừa crawl trong vòng vài chục phút).
              </p>
              <Coverage rows={coverage} />
            </>
          )}
        </>
      )}
    </Async>
  );
}
