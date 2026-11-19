import { Link } from "react-router-dom";
import { Async, EmptyState, PageHeader, StatusBadge, TableCard } from "../components/common";
import Icon from "../components/Icon";
import Pager from "../components/Pager";
import { dmyhm, range } from "../format";
import { useApi, useListQuery, useTitle } from "../hooks";
import { useMeta } from "../meta";
import type { Job, Paged } from "../types";

const ACTIVE = ["queued", "running", "paused"];

export default function JobsPage() {
  useTitle("Công việc");
  const { statuses } = useMeta();
  const q = useListQuery();
  const status = q.sp.get("status") ?? "";
  // Tự làm mới 5 giây một lần khi trang đang có việc chưa xong
  const hasActive = (d: Paged<Job> | null) => !!d?.items.some((j) => ACTIVE.includes(j.status));
  const res = useApi<Paged<Job>>(`/api/jobs?${q.query}`, (d) => (hasActive(d) ? 5000 : 0), true);

  return (
    <>
      <PageHeader
        title="Công việc crawl"
        subtitle={hasActive(res.data) ? <><i className="dot pulse inline" /> Có công việc đang chạy, trang tự làm mới mỗi 5 giây</> : "Lịch sử và hàng đợi các lần crawl"}
        actions={<Link className="btn primary" to="/crawl"><Icon name="plus" size={16} />Crawl mới</Link>}
      />
      <div className="seg" role="tablist" aria-label="Lọc theo trạng thái">
        <button className={status === "" ? "on" : ""} onClick={() => q.setFilter("status", "")}>Tất cả</button>
        {Object.entries(statuses).map(([k, v]) => (
          <button key={k} className={status === k ? "on" : ""} onClick={() => q.setFilter("status", k)}>{v.label}</button>
        ))}
      </div>
      <Async res={res}>
        {(d) => (
          <TableCard footer={<Pager page={d.page} pages={d.pages} total={d.total} perPage={d.per_page} onPage={q.goPage} onPerPage={q.setPerPage} />}>
            <table>
              <thead>
                <tr><th>#</th><th>MST</th><th>Loại</th><th>Khoảng yêu cầu</th><th>Khoảng crawl</th><th>Trạng thái</th><th>Bố cáo</th><th>Ghi chú</th><th>Tạo lúc</th></tr>
              </thead>
              <tbody>
                {d.items.map((j) => (
                  <tr key={j.id}>
                    <td><Link to={`/jobs/${j.id}`} className="strong">#{j.id}</Link></td>
                    <td className="mono">{j.tax_code}</td>
                    <td><span className="tag">{j.ann_type}</span></td>
                    <td className="nowrap">{range(j.req_from, j.req_to)}</td>
                    <td className="nowrap">{j.status === "skipped" ? "—" : range(j.crawl_from, j.crawl_to, "không lọc ngày")}</td>
                    <td><StatusBadge status={j.status} /></td>
                    <td>{j.result_count}{j.new_count > 0 && <small> (+{j.new_count})</small>}</td>
                    <td className="wrap">{j.message}</td>
                    <td className="nowrap">{dmyhm(j.created_at)}</td>
                  </tr>
                ))}
                {!d.items.length && <tr><td colSpan={9}><EmptyState icon="list" title="Không có công việc" /></td></tr>}
              </tbody>
            </table>
          </TableCard>
        )}
      </Async>
    </>
  );
}
