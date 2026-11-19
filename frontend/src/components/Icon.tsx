import type { ReactNode } from "react";

// Bộ icon nét mảnh (kiểu Feather), vẽ inline nên không cần thư viện hay CDN.
const P = (d: string, k?: string | number) => <path key={k ?? d} d={d} />;

const ICONS: Record<string, ReactNode> = {
  home: [P("M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"), P("M9 22V12h6v10")],
  search: [<circle key="c" cx="11" cy="11" r="8" />, P("M21 21l-4.35-4.35")],
  cloud: [P("M8 17l4 4 4-4"), P("M12 12v9"), P("M20.88 18.09A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.29")],
  building: [<rect key="r" x="4" y="2" width="16" height="20" rx="2" />, P("M9 22v-4h6v4"), P("M8 6h.01"), P("M16 6h.01"), P("M12 6h.01"), P("M12 10h.01"), P("M12 14h.01"), P("M16 10h.01"), P("M16 14h.01"), P("M8 10h.01"), P("M8 14h.01")],
  users: [P("M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"), <circle key="c" cx="9" cy="7" r="4" />, P("M23 21v-2a4 4 0 0 0-3-3.87"), P("M16 3.13a4 4 0 0 1 0 7.75")],
  list: [P("M8 6h13"), P("M8 12h13"), P("M8 18h13"), P("M3 6h.01"), P("M3 12h.01"), P("M3 18h.01")],
  file: [P("M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"), P("M14 2v6h6"), P("M16 13H8"), P("M16 17H8"), P("M10 9H8")],
  sun: [<circle key="c" cx="12" cy="12" r="5" />, P("M12 1v2"), P("M12 21v2"), P("M4.22 4.22l1.42 1.42"), P("M18.36 18.36l1.42 1.42"), P("M1 12h2"), P("M21 12h2"), P("M4.22 19.78l1.42-1.42"), P("M18.36 5.64l1.42-1.42")],
  moon: [P("M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z")],
  check: [P("M20 6L9 17l-5-5")],
  checkCircle: [P("M22 11.08V12a10 10 0 1 1-5.93-9.14"), P("M22 4L12 14.01l-3-3")],
  alert: [P("M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"), P("M12 9v4"), P("M12 17h.01")],
  info: [<circle key="c" cx="12" cy="12" r="10" />, P("M12 16v-4"), P("M12 8h.01")],
  chevL: [P("M15 18l-6-6 6-6")],
  chevR: [P("M9 18l6-6-6-6")],
  chevsL: [P("M11 17l-5-5 5-5"), P("M18 17l-5-5 5-5")],
  chevsR: [P("M13 17l5-5-5-5"), P("M6 17l5-5-5-5")],
  chevD: [P("M6 9l6 6 6-6")],
  external: [P("M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"), P("M15 3h6v6"), P("M10 14L21 3")],
  x: [P("M18 6L6 18"), P("M6 6l12 12")],
  refresh: [P("M23 4v6h-6"), P("M1 20v-6h6"), P("M3.51 9a9 9 0 0 1 14.85-3.36L23 10"), P("M1 14l4.64 4.36A9 9 0 0 0 20.49 15")],
  plus: [P("M12 5v14"), P("M5 12h14")],
  download: [P("M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"), P("M7 10l5 5 5-5"), P("M12 15V3")],
  menu: [P("M3 12h18"), P("M3 6h18"), P("M3 18h18")],
  play: [<polygon key="p" points="5 3 19 12 5 21 5 3" />],
  clock: [<circle key="c" cx="12" cy="12" r="10" />, P("M12 6v6l4 2")],
  arrowLeft: [P("M19 12H5"), P("M12 19l-7-7 7-7")],
  arrowRight: [P("M5 12h14"), P("M12 5l7 7-7 7")],
  calendar: [<rect key="r" x="3" y="4" width="18" height="18" rx="2" />, P("M16 2v4"), P("M8 2v4"), P("M3 10h18")],
  inbox: [P("M22 12h-6l-2 3h-4l-2-3H2"), P("M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z")],
  map: [P("M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"), <circle key="c" cx="12" cy="10" r="3" />],
  user: [P("M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"), <circle key="c" cx="12" cy="7" r="4" />],
  trending: [P("M23 6l-9.5 9.5-5-5L1 18"), P("M17 6h6v6")],
};

export type IconName = keyof typeof ICONS;

export default function Icon({ name, size = 18, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      className={`icon${className ? ` ${className}` : ""}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICONS[name]}
    </svg>
  );
}
