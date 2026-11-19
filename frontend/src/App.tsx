import { Link, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { Async, EmptyState } from "./components/common";
import { useApi, useTitle } from "./hooks";
import { MetaProvider } from "./meta";
import AnnouncementPage from "./pages/AnnouncementPage";
import CompanyPage from "./pages/CompanyPage";
import CompaniesPage from "./pages/CompaniesPage";
import CrawlPage from "./pages/CrawlPage";
import JobPage from "./pages/JobPage";
import JobsPage from "./pages/JobsPage";
import OverviewPage from "./pages/OverviewPage";
import SearchPage from "./pages/SearchPage";
import type { Meta } from "./types";

function NotFound() {
  useTitle("Không tìm thấy");
  return (
    <EmptyState icon="search" title="Không tìm thấy trang">
      <Link to="/">← Về tổng quan</Link>
    </EmptyState>
  );
}

export default function App() {
  const meta = useApi<Meta>("/api/meta");
  return (
    <Async res={meta}>
      {(m) => (
        <MetaProvider meta={m}>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<OverviewPage />} />
              <Route path="crawl" element={<CrawlPage />} />
              <Route path="jobs" element={<JobsPage />} />
              <Route path="jobs/:id" element={<JobPage />} />
              <Route path="search" element={<SearchPage />} />
              <Route path="announcements/:id" element={<AnnouncementPage />} />
              <Route path="companies" element={<CompaniesPage />} />
              <Route path="companies/:tax" element={<CompanyPage />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </MetaProvider>
      )}
    </Async>
  );
}
