import { useMemo, useState } from "react";
import { buildComparison, diffWords, type CompareRow, type CompareSection, type Group, type Part } from "../compare";
import { EmptyState } from "./common";
import Icon from "./Icon";
import Pager, { usePaged } from "./Pager";

function Marked({ parts }: { parts: Part[] }) {
  return <>{parts.map((p, i) => (p.mark ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}</>;
}

function Cell({ row, side }: { row: CompareRow; side: "old" | "new" }) {
  const value = side === "old" ? row.oldValue : row.newValue;
  if (value === null) return <td className="cmp-cell none"><span className="muted">— không có —</span></td>;
  if (row.status === "changed" && row.oldValue !== null && row.newValue !== null) {
    const d = diffWords(row.oldValue, row.newValue);
    return <td className={`cmp-cell ${side}`}><Marked parts={side === "old" ? d.old : d.new} /></td>;
  }
  const cls = row.status === "removed" && side === "old" ? "old" : row.status === "added" && side === "new" ? "new" : "same";
  return <td className={`cmp-cell ${cls}`}>{value || <span className="muted">(trống)</span>}</td>;
}

const MARK: Record<string, { icon: string; label: string }> = {
  changed: { icon: "~", label: "Đã thay đổi" },
  added: { icon: "+", label: "Thêm mới" },
  removed: { icon: "−", label: "Đã bỏ" },
  same: { icon: "", label: "Không đổi" },
};

function SectionTable({ rows }: { rows: CompareRow[] }) {
  const { slice, pagerProps } = usePaged(rows, 10);
  return (
    <>
      <div className="table-wrap">
        <table className="cmp">
          <colgroup><col className="c-key" /><col /><col /></colgroup>
          <thead>
            <tr><th>Chỉ tiêu</th><th>Nội dung cũ</th><th>Nội dung mới</th></tr>
          </thead>
          <tbody>
            {slice.map((r, i) => (
              <tr key={i} className={`cmp-row ${r.status}`}>
                <th scope="row">
                  <span className={`cmp-mark ${r.status}`} title={MARK[r.status].label}>{MARK[r.status].icon}</span>
                  {r.key}
                </th>
                <Cell row={r} side="old" />
                <Cell row={r} side="new" />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pager {...pagerProps} sizes={[10, 25, 50]} />
    </>
  );
}

function Section({ s, onlyChanged }: { s: CompareSection; onlyChanged: boolean }) {
  const [open, setOpen] = useState(false);
  const unchanged = s.changed === 0;
  const rows = onlyChanged && !open ? s.rows.filter((r) => r.status !== "same") : s.rows;
  const collapsed = onlyChanged && unchanged && !open;
  const sameCount = s.rows.length - s.changed;

  return (
    <section className={`card cmp-section${unchanged ? " unchanged" : ""}`}>
      <header className="cmp-head">
        <h3>{s.title}</h3>
        <div className="cmp-tags">
          {s.side === "old" && <span className="badge bad"><i className="dot" />Chỉ có ở bản cũ</span>}
          {s.side === "new" && <span className="badge ok"><i className="dot" />Chỉ có ở bản mới</span>}
          {unchanged ? (
            <span className="badge muted">Không thay đổi</span>
          ) : (
            <span className="badge warn"><i className="dot" />{s.changed} thay đổi</span>
          )}
          {sameCount > 0 && !unchanged && onlyChanged && (
            <button className="link-btn" onClick={() => setOpen((o) => !o)}>
              {open ? "Ẩn dòng không đổi" : `Hiện ${sameCount} dòng không đổi`}
            </button>
          )}
          {collapsed && s.rows.length > 0 && (
            <button className="link-btn" onClick={() => setOpen(true)}>Xem {s.rows.length} dòng <Icon name="chevD" size={14} /></button>
          )}
        </div>
      </header>
      {!collapsed && rows.length > 0 && <SectionTable rows={rows} />}
    </section>
  );
}

export default function ChangeCompare({ groups }: { groups: Group[] }) {
  const cmp = useMemo(() => buildComparison(groups), [groups]);
  const [onlyChanged, setOnlyChanged] = useState(true);

  if (!cmp.sections.length) {
    return (
      <EmptyState icon="info" title="Bố cáo này không có phần so sánh cũ / mới">
        Thường gặp ở bố cáo đăng ký mới hoặc khi PDF chưa được tách nội dung. Xem tab “Thông tin chung” để đọc toàn bộ nội dung.
      </EmptyState>
    );
  }
  return (
    <div className="cmp-wrap">
      <div className="cmp-toolbar card">
        <div className="cmp-stats">
          <b>{cmp.changed}</b> thay đổi trong <b>{cmp.sections.filter((s) => s.changed > 0).length}</b>/{cmp.sections.length} mục
        </div>
        <div className="legend">
          <span><i className="lg changed" />Đã đổi</span>
          <span><i className="lg added" />Thêm mới</span>
          <span><i className="lg removed" />Đã bỏ</span>
        </div>
        <label className="switch">
          <input type="checkbox" checked={onlyChanged} onChange={(e) => setOnlyChanged(e.target.checked)} />
          <span className="track" />
          Chỉ hiện dòng thay đổi
        </label>
      </div>
      {cmp.sections.map((s) => <Section key={s.id} s={s} onlyChanged={onlyChanged} />)}
    </div>
  );
}
