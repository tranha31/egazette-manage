import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Resource } from "../hooks";
import { useStatus } from "../meta";
import Icon, { type IconName } from "./Icon";

export function StatusBadge({ status }: { status: string }) {
  const s = useStatus()(status);
  return (
    <span className={`badge ${s.tone}`}>
      <i className={`dot${status === "running" ? " pulse" : ""}`} />
      {s.label}
    </span>
  );
}

export function Skeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="card skeleton" aria-busy="true" aria-label="Đang tải">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="sk-row">
          <span className="sk" style={{ width: `${18 + ((i * 17) % 24)}%` }} />
          <span className="sk" style={{ width: `${30 + ((i * 29) % 40)}%` }} />
          <span className="sk" style={{ width: `${10 + ((i * 13) % 20)}%` }} />
        </div>
      ))}
    </div>
  );
}

/** Hiện khung chờ / lỗi, có dữ liệu thì render children. */
export function Async<T>({ res, children, rows }: { res: Resource<T>; children: (data: T) => ReactNode; rows?: number }) {
  if (res.error && !res.data) {
    return (
      <div className="alert bad">
        <Icon name="alert" />
        <div>{res.error}</div>
        <button className="btn sm" onClick={res.reload}>Thử lại</button>
      </div>
    );
  }
  if (!res.data) return <Skeleton rows={rows} />;
  return <div className={res.stale ? "stale" : undefined}>{children(res.data)}</div>;
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function EmptyState({ icon = "inbox", title, children }: { icon?: IconName; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-icon"><Icon name={icon} size={26} /></div>
      <b>{title}</b>
      {children && <p>{children}</p>}
    </div>
  );
}

export function Crumbs({ items }: { items: (string | [string, string])[] }) {
  return (
    <nav className="crumbs" aria-label="Đường dẫn">
      {items.map((it, i) => (
        <span key={i}>
          {i > 0 && <Icon name="chevR" size={13} />}
          {Array.isArray(it) ? <Link to={it[1]}>{it[0]}</Link> : <span className="cur">{it}</span>}
        </span>
      ))}
    </nav>
  );
}

const HUES = [248, 200, 160, 28, 330, 270, 190, 10];
/** Ảnh đại diện chữ cái đầu, màu cố định theo tên. */
export function Avatar({ name, size = 36, square }: { name: string; size?: number; square?: boolean }) {
  const words = name.replace(/^(công ty|cty)\s+(cổ phần|tnhh|trách nhiệm hữu hạn)?\s*/i, "").trim().split(/\s+/).filter(Boolean);
  const initials = ((words[0]?.[0] ?? "?") + (words.length > 1 ? words[words.length - 1][0] : "")).toUpperCase();
  const hue = HUES[[...name].reduce((s, c) => s + c.charCodeAt(0), 0) % HUES.length];
  return (
    <span
      className={`avatar${square ? " sq" : ""}`}
      style={{ width: size, height: size, fontSize: size * 0.38, ["--h" as string]: hue }}
      aria-hidden="true"
    >
      {initials}
    </span>
  );
}

export function Names({ reps }: { reps: { full_name: string }[] }) {
  if (!reps.length) return <span className="muted">—</span>;
  return <>{reps.map((r) => r.full_name).join(", ")}</>;
}

export function PdfLink({ href, children = "PDF" }: { href: string; children?: ReactNode }) {
  return (
    <a className="chip-link" href={href} target="_blank" rel="noreferrer">
      <Icon name="file" size={14} />
      {children}
    </a>
  );
}

/** Bảng trong thẻ, cuộn ngang khi hẹp. */
export function TableCard({ children, footer }: { children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="card table-card">
      <div className="table-wrap">{children}</div>
      {footer}
    </div>
  );
}
