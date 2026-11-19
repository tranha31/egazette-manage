import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../api";
import { useApi, useTheme } from "../hooks";
import type { WorkerStatus } from "../types";
import Icon, { type IconName } from "./Icon";
import { useToast } from "./Toast";

const NAV: { title: string; items: [string, string, IconName][] }[] = [
  {
    title: "Dữ liệu",
    items: [
      ["/", "Tổng quan", "home"],
      ["/search", "Tìm bố cáo", "search"],
      ["/companies", "Doanh nghiệp", "building"],
    ],
  },
  {
    title: "Thu thập",
    items: [
      ["/crawl", "Crawl mới", "cloud"],
      ["/jobs", "Công việc", "list"],
    ],
  },
];

export default function Layout() {
  const worker = useApi<WorkerStatus>("/api/worker", 5000);
  const { theme, toggle } = useTheme();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const loc = useLocation();

  useEffect(() => setOpen(false), [loc.pathname]); // đóng menu mobile khi chuyển trang

  const resume = async () => {
    setBusy(true);
    try {
      await api.resumeWorker();
      toast("Đã tiếp tục hàng đợi crawl");
    } catch (e) {
      toast((e as Error).message, "bad");
    } finally {
      setBusy(false);
      worker.reload();
    }
  };

  const w = worker.data;
  return (
    <div className={`shell${open ? " menu-open" : ""}`}>
      <aside className="sidebar">
        <NavLink className="brand" to="/">
          <span className="logo"><Icon name="file" size={17} /></span>
          <span>Egazette<small>Bố cáo điện tử</small></span>
        </NavLink>
        <nav>
          {NAV.map((g) => (
            <div key={g.title} className="nav-group">
              <div className="nav-title">{g.title}</div>
              {g.items.map(([to, label, icon]) => (
                <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `nav-link${isActive ? " on" : ""}`}>
                  <Icon name={icon} />
                  {label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="side-foot">
          {w?.current_job_id ? (
            <NavLink to={`/jobs/${w.current_job_id}`} className="worker-chip run">
              <i className="dot pulse" /> Đang crawl job #{w.current_job_id}
            </NavLink>
          ) : (
            <span className={`worker-chip${w?.paused ? " paused" : ""}`}>
              <i className="dot" /> {w?.paused ? "Hàng đợi tạm dừng" : w?.alive ? "Hàng đợi sẵn sàng" : "Worker chưa bật"}
            </span>
          )}
          <button className="theme-btn" onClick={toggle} aria-label="Đổi giao diện sáng/tối">
            <Icon name={theme === "dark" ? "sun" : "moon"} />
            {theme === "dark" ? "Giao diện sáng" : "Giao diện tối"}
          </button>
        </div>
      </aside>

      <div className="content">
        <header className="topbar">
          <button className="icon-btn" aria-label="Mở menu" onClick={() => setOpen((o) => !o)}><Icon name="menu" size={20} /></button>
          <b>Egazette</b>
        </header>
        {open && <div className="scrim" onClick={() => setOpen(false)} />}

        {w?.paused && (
          <div className="alert warn banner">
            <Icon name="alert" />
            <div><b>Hàng đợi crawl đang tạm dừng.</b> {w.reason}</div>
            <button className="btn sm" disabled={busy} onClick={resume}>Tiếp tục</button>
          </div>
        )}
        <main>
          <Outlet />
        </main>
        <footer>
          Dữ liệu lấy từ bocaodientu.dkkd.gov.vn · có chứa thông tin cá nhân (CCCD, địa chỉ), hãy bảo quản cẩn thận.
        </footer>
      </div>
    </div>
  );
}
