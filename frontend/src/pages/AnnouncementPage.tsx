import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { fileUrl } from "../api";
import ChangeCompare from "../components/ChangeCompare";
import { Async, Avatar, Crumbs, EmptyState } from "../components/common";
import Icon from "../components/Icon";
import Pager, { usePaged } from "../components/Pager";
import { buildComparison } from "../compare";
import { bytes, dmy, dmyhm } from "../format";
import { useApi, useTitle } from "../hooks";
import { useTypeName } from "../meta";
import type { AnnouncementDetail, Rep } from "../types";

type Tab = "changes" | "info" | "reps" | "all" | "pdf";

function Dl({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="dl wide">
      {rows.map(([k, v]) => (
        <div key={k} className="dl-row">
          <dt>{k}</dt>
          <dd>{v || <span className="muted">—</span>}</dd>
        </div>
      ))}
    </dl>
  );
}

function RepCard({ r }: { r: Rep }) {
  return (
    <article className="card rep">
      <header>
        <Avatar name={r.full_name} size={44} />
        <div>
          <b>{r.full_name}</b>
          <span className="muted">{r.position || "Người đại diện theo pháp luật"}</span>
        </div>
        <span className="tag">#{r.seq}</span>
      </header>
      <Dl
        rows={[
          ["Giới tính", r.gender],
          ["Ngày sinh", dmy(r.birth_date)],
          ["Dân tộc", r.ethnicity],
          ["Quốc tịch", r.nationality],
          [r.id_doc_type || "Giấy tờ", <span className="mono" key="id">{r.id_number}</span>],
          ["Ngày cấp", dmy(r.id_issue_date)],
          ["Nơi cấp", r.id_issue_place],
          ["Địa chỉ thường trú", r.residence_address],
          ["Địa chỉ liên lạc", r.contact_address],
        ]}
      />
    </article>
  );
}

function Reps({ reps, parsed }: { reps: Rep[]; parsed: boolean }) {
  const { slice, pagerProps } = usePaged(reps, 4);
  if (!reps.length) {
    return <EmptyState icon="user" title="Không có dữ liệu người đại diện">{parsed ? "Bố cáo không có mục này." : "PDF chưa được tách nội dung."}</EmptyState>;
  }
  return (
    <>
      <div className="reps">{slice.map((r) => <RepCard key={r.seq} r={r} />)}</div>
      <Pager {...pagerProps} sizes={[4, 8, 20]} />
    </>
  );
}

function FieldGroup({ name, fields, open }: { name: string; fields: { key: string; value: string }[]; open: boolean }) {
  const { slice, pagerProps } = usePaged(fields, 25);
  return (
    <details className="card acc" open={open}>
      <summary>
        <Icon name="chevR" size={16} className="chev" />
        {name} <small>({fields.length})</small>
      </summary>
      <div className="table-wrap">
        <table className="kv">
          <tbody>
            {slice.map((f, i) => <tr key={i}><th>{f.key}</th><td className="wrap">{f.value || <span className="muted">—</span>}</td></tr>)}
          </tbody>
        </table>
      </div>
      <Pager {...pagerProps} sizes={[25, 50, 100]} />
    </details>
  );
}

const TABS: [Tab, string][] = [["changes", "Thay đổi cũ → mới"], ["info", "Thông tin chung"], ["reps", "Người đại diện"], ["all", "Toàn bộ nội dung"], ["pdf", "Bản PDF"]];

export default function AnnouncementPage() {
  const { id } = useParams();
  const typeName = useTypeName();
  const [sp, setSp] = useSearchParams();
  const res = useApi<AnnouncementDetail>(`/api/announcements/${id}`);
  useTitle(res.data?.company_name || `Bố cáo #${id}`);
  const cmp = useMemo(() => (res.data ? buildComparison(res.data.groups) : null), [res.data]);

  return (
    <Async res={res}>
      {(a) => {
        const hasChanges = !!cmp && cmp.sections.length > 0;
        const tabs = TABS.filter(([t]) => (t !== "pdf" || a.has_pdf) && (t !== "changes" || hasChanges));
        const wanted = sp.get("tab") as Tab | null;
        const tab: Tab = tabs.some(([t]) => t === wanted) ? (wanted as Tab) : tabs[0][0];

        return (
          <>
            <Crumbs items={[["Tìm bố cáo", "/search"], [a.tax_code, `/companies/${a.tax_code}`], dmyhm(a.posted_at)]} />
            <header className="card hero">
              <Avatar name={a.company_name || a.tax_code} size={56} square />
              <div className="hero-main">
                <h1>{a.company_name || "(chưa tách được tên)"}</h1>
                <div className="hero-meta">
                  <span className="tag strong">{typeName(a.ann_type)}</span>
                  <span><Icon name="calendar" size={14} />{dmyhm(a.posted_at)}</span>
                  <span className="mono">MST {a.tax_code}</span>
                  {a.hq_address && <span className="clamp"><Icon name="map" size={14} />{a.hq_address}</span>}
                </div>
                {a.title && a.title !== typeName(a.ann_type) && <p className="muted">{a.title}</p>}
              </div>
              <div className="hero-actions">
                {a.has_pdf ? (
                  <>
                    <a className="btn primary" href={fileUrl(a.id)} target="_blank" rel="noreferrer"><Icon name="external" size={16} />Mở PDF</a>
                    <a className="btn" href={fileUrl(a.id, true)}><Icon name="download" size={16} />Tải PDF</a>
                  </>
                ) : <span className="badge warn"><i className="dot" />PDF: {a.pdf_status || "chưa có"}</span>}
              </div>
            </header>

            <div className="tabs" role="tablist">
              {tabs.map(([t, label]) => (
                <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""} onClick={() => setSp(t === tabs[0][0] ? {} : { tab: t }, { replace: true })}>
                  {label}
                  {t === "changes" && cmp && cmp.changed > 0 && <span className="count">{cmp.changed}</span>}
                  {t === "reps" && <span className="count">{a.reps.length}</span>}
                </button>
              ))}
            </div>

            {tab === "changes" && <ChangeCompare groups={a.groups} />}

            {tab === "info" && (
              <section className="card pad">
                <Dl
                  rows={[
                    ["MST dùng để tra cứu", <span className="mono" key="a">{a.tax_code}</span>],
                    ["MST trên bố cáo", <span className="mono" key="b">{a.doc_tax_code}</span>],
                    ["Ngày giờ đăng", <>{dmyhm(a.posted_at)} <small>(hiển thị trên trang từ {a.start_at} đến {a.end_at})</small></>],
                    ["Ngày thành lập", dmy(a.established_date)],
                    ["Địa chỉ trụ sở chính", a.hq_address],
                    ["Vốn điều lệ", a.charter_capital],
                    ["Ngày cấp đăng ký thay đổi", dmy(a.reg_change_date)],
                    ["Nơi đăng ký", a.reg_place],
                    ["Nơi đặt trụ sở (theo trang)", a.place],
                    ["Nội dung thay đổi (theo trang)", a.change_type],
                    ["Trạng thái tách PDF", a.parse_status],
                    [
                      "File PDF trên MinIO",
                      a.pdf_location && (
                        <span key="loc">
                          <span className="mono wrap-any">{a.pdf_location}</span>
                          {a.pdf_size > 0 && <small> ({bytes(a.pdf_size)})</small>}
                        </span>
                      ),
                    ],
                  ]}
                />
              </section>
            )}

            {tab === "reps" && <Reps reps={a.reps} parsed={a.parse_status === "ok"} />}

            {tab === "all" && (
              a.groups.length ? (
                <div className="accs">
                  {a.groups.map((g, i) => <FieldGroup key={g.name} name={g.name} fields={g.fields} open={i < 2} />)}
                </div>
              ) : <EmptyState title="Chưa có nội dung tách từ PDF" />
            )}

            {tab === "pdf" && <iframe className="pdf" src={fileUrl(a.id)} title="PDF bố cáo" />}

            <p className="back"><Link to="/search"><Icon name="arrowLeft" size={14} /> Về danh sách</Link></p>
          </>
        );
      }}
    </Async>
  );
}
