import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { exportUrl, fileUrl } from "../api";
import { Async, Avatar, EmptyState, Names, PageHeader, PdfLink, TableCard } from "../components/common";
import Icon from "../components/Icon";
import Pager from "../components/Pager";
import { dmyhm } from "../format";
import { paramsFromForm, useApi, useListQuery, useTitle } from "../hooks";
import { useMeta, useTypeName } from "../meta";
import type { AnnouncementSummary, Paged } from "../types";

export default function SearchPage() {
  useTitle("Tìm bố cáo");
  const { types } = useMeta();
  const typeName = useTypeName();
  const q = useListQuery();
  const res = useApi<Paged<AnnouncementSummary>>(`/api/search?${q.query}`, 0, true);
  const sp = q.sp;

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    q.apply(paramsFromForm(e.currentTarget));
  };
  const exportQuery = q.filtersKey ? `?${q.filtersKey}` : "";

  return (
    <>
      <PageHeader title="Tìm bố cáo" subtitle="Tra cứu theo tên doanh nghiệp, mã số thuế, địa chỉ, người đại diện hoặc số CCCD" />
      <form key={q.filtersKey} className="card filters" onSubmit={onSubmit}>
        <label className="grow">
          Từ khoá
          <span className="input-icon">
            <Icon name="search" size={16} />
            <input type="search" name="q" defaultValue={sp.get("q") ?? ""} placeholder="vd: A, 9999999999, Nguyễn Văn A" />
          </span>
        </label>
        <label>MST <input name="tax_code" defaultValue={sp.get("tax_code") ?? ""} className="w-mst" /></label>
        <label>
          Loại công bố
          <select name="ann_type" defaultValue={sp.get("ann_type") ?? ""}>
            <option value="">Tất cả</option>
            {types.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
          </select>
        </label>
        <label>Đăng từ <input type="date" name="date_from" defaultValue={sp.get("date_from") ?? ""} /></label>
        <label>đến <input type="date" name="date_to" defaultValue={sp.get("date_to") ?? ""} /></label>
        <div className="filter-opts">
          <label className="check"><input type="checkbox" name="deep" value="1" defaultChecked={sp.get("deep") === "1"} /> Tìm trong toàn bộ nội dung</label>
          <label className="check"><input type="checkbox" name="pdf_only" value="1" defaultChecked={sp.get("pdf_only") === "1"} /> Chỉ bố cáo có PDF</label>
        </div>
        <div className="filter-actions">
          <button className="btn primary"><Icon name="search" size={16} />Tìm</button>
          <button type="button" className="btn" onClick={q.reset}>Xoá lọc</button>
          <a className="btn" href={exportUrl(exportQuery)}><Icon name="download" size={16} />Xuất Excel</a>
        </div>
      </form>

      <Async res={res}>
        {(d) => (
          <TableCard footer={<Pager page={d.page} pages={d.pages} total={d.total} perPage={d.per_page} onPage={q.goPage} onPerPage={q.setPerPage} />}>
            <table>
              <thead><tr><th>Doanh nghiệp</th><th>Ngày giờ đăng</th><th>Loại</th><th>Người đại diện</th><th>PDF</th><th /></tr></thead>
              <tbody>
                {d.items.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <div className="cell-company">
                        <Avatar name={a.company_name || a.tax_code} />
                        <div>
                          <Link to={`/announcements/${a.id}`} className="strong">{a.company_name || "(chưa tách được tên)"}</Link>
                          <div><Link to={`/companies/${a.tax_code}`} className="mono sub">{a.tax_code}</Link></div>
                        </div>
                      </div>
                    </td>
                    <td className="nowrap">{dmyhm(a.posted_at)}</td>
                    <td><span className="tag">{typeName(a.ann_type)}</span></td>
                    <td className="wrap"><Names reps={a.reps} /></td>
                    <td>{a.has_pdf ? <PdfLink href={fileUrl(a.id)} /> : <span className="muted">—</span>}</td>
                    <td><Link to={`/announcements/${a.id}`} className="more">Chi tiết <Icon name="arrowRight" size={14} /></Link></td>
                  </tr>
                ))}
                {!d.items.length && (
                  <tr><td colSpan={6}><EmptyState icon="search" title="Không có bố cáo phù hợp">Thử bỏ bớt bộ lọc hoặc bật “Tìm trong toàn bộ nội dung”.</EmptyState></td></tr>
                )}
              </tbody>
            </table>
          </TableCard>
        )}
      </Async>
    </>
  );
}
