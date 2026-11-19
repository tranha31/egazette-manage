import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { Async, Avatar, EmptyState, PageHeader, TableCard } from "../components/common";
import Icon from "../components/Icon";
import Pager from "../components/Pager";
import { dmyhm } from "../format";
import { paramsFromForm, useApi, useListQuery, useTitle } from "../hooks";
import type { CompanyRow, Paged } from "../types";

export default function CompaniesPage() {
  useTitle("Doanh nghiệp");
  const q = useListQuery();
  const res = useApi<Paged<CompanyRow>>(`/api/companies?${q.query}`, 0, true);
  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    q.apply(paramsFromForm(e.currentTarget));
  };

  return (
    <>
      <PageHeader title="Doanh nghiệp" subtitle="Mỗi mã số thuế một dòng, lấy thông tin từ bố cáo mới nhất" />
      <form key={q.filtersKey} className="card filters" onSubmit={onSubmit}>
        <label className="grow">
          Từ khoá
          <span className="input-icon">
            <Icon name="search" size={16} />
            <input type="search" name="q" defaultValue={q.sp.get("q") ?? ""} placeholder="tên doanh nghiệp, MST, địa chỉ, người đại diện, CCCD" />
          </span>
        </label>
        <div className="filter-opts">
          <label className="check"><input type="checkbox" name="deep" value="1" defaultChecked={q.sp.get("deep") === "1"} /> Tìm trong toàn bộ nội dung</label>
        </div>
        <div className="filter-actions">
          <button className="btn primary"><Icon name="search" size={16} />Tìm</button>
          <button type="button" className="btn" onClick={q.reset}>Xoá lọc</button>
        </div>
      </form>
      <Async res={res}>
        {(d) => (
          <TableCard footer={<Pager page={d.page} pages={d.pages} total={d.total} perPage={d.per_page} onPage={q.goPage} onPerPage={q.setPerPage} />}>
            <table>
              <thead><tr><th>Doanh nghiệp</th><th>Địa chỉ trụ sở chính</th><th>Người đại diện (mới nhất)</th><th>Số bố cáo</th><th>Bố cáo mới nhất</th><th>Thao tác</th></tr></thead>
              <tbody>
                {d.items.map((c) => (
                  <tr key={c.tax_code}>
                    <td>
                      <div className="cell-company">
                        <Avatar name={c.company_name || c.tax_code} />
                        <div>
                          <Link to={`/companies/${c.tax_code}`} className="strong">{c.company_name || c.tax_code}</Link>
                          <div className="mono sub">{c.tax_code}</div>
                        </div>
                      </div>
                    </td>
                    <td className="wrap">{c.hq_address}</td>
                    <td className="wrap">{c.reps || <span className="muted">—</span>}</td>
                    <td><span className="count-pill">{c.count}</span></td>
                    <td className="nowrap">{dmyhm(c.last_at)}</td>
                    <td>
                      <div className="row-actions">
                        <Link className="btn sm primary" to={`/search?tax_code=${encodeURIComponent(c.tax_code)}`} title={`Xem ${c.count} bố cáo của ${c.tax_code}`}>
                          <Icon name="list" size={14} />Xem bố cáo
                        </Link>
                        <Link className="btn sm" to={`/companies/${c.tax_code}`}>Chi tiết</Link>
                      </div>
                    </td>
                  </tr>
                ))}
                {!d.items.length && <tr><td colSpan={6}><EmptyState icon="building" title="Không có doanh nghiệp phù hợp" /></td></tr>}
              </tbody>
            </table>
          </TableCard>
        )}
      </Async>
    </>
  );
}
