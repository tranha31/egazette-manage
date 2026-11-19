// Kiểu dữ liệu trả về từ API (backend/app/serializers.py). Ngày: "YYYY-MM-DD", ngày giờ: "YYYY-MM-DDTHH:MM:SS".
export type Tone = "ok" | "warn" | "bad" | "info" | "muted";

export interface Meta {
  types: { code: string; name: string }[];
  statuses: Record<string, { label: string; tone: Tone }>;
  per_page: number;
  auth: boolean;
}

export interface WorkerStatus {
  paused: boolean;
  reason: string;
  current_job_id: number | null;
  alive: boolean;
}

export interface Job {
  id: number;
  tax_code: string;
  ann_type: string;
  ann_type_name: string;
  req_from: string | null;
  req_to: string | null;
  crawl_from: string | null;
  crawl_to: string | null;
  cover_from: string | null;
  cover_to: string | null;
  force: boolean;
  status: string;
  message: string;
  result_count: number;
  new_count: number;
  pdf_ok: number;
  pdf_fail: number;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  log?: string;
}

export interface RepBrief {
  full_name: string;
  position: string;
  id_number: string;
}

export interface AnnouncementSummary {
  id: number;
  tax_code: string;
  ann_type: string;
  ann_type_name: string;
  posted_at: string;
  title: string;
  company_name: string;
  doc_tax_code: string;
  established_date: string | null;
  hq_address: string;
  charter_capital: string;
  reg_change_date: string | null;
  reg_place: string;
  has_pdf: boolean;
  pdf_status: string;
  parse_status: string;
  reps: RepBrief[];
}

export interface Rep {
  seq: number;
  full_name: string;
  gender: string;
  position: string;
  birth_date: string | null;
  ethnicity: string;
  nationality: string;
  id_doc_type: string;
  id_number: string;
  id_issue_date: string | null;
  id_issue_place: string;
  residence_address: string;
  contact_address: string;
}

export interface AnnouncementDetail extends Omit<AnnouncementSummary, "reps"> {
  /** File PDF trên MinIO (rỗng nếu chưa có) */
  pdf_bucket: string;
  pdf_key: string;
  pdf_location: string; // s3://bucket/key
  pdf_size: number;
  start_at: string;
  end_at: string;
  place: string;
  change_type: string;
  reps: Rep[];
  groups: { name: string; fields: { key: string; value: string }[] }[];
}

export interface CompanyRow {
  tax_code: string;
  count: number;
  last_at: string | null;
  company_name: string;
  hq_address: string;
  reps: string;
}

export interface CoverageRow {
  ann_type: string;
  date_from: string;
  date_to: string;
  crawled_at: string;
  result_count: number;
  effective: { start: string; end: string } | null;
}

export interface CompanyDetail {
  tax_code: string;
  latest: AnnouncementSummary;
  announcements: AnnouncementSummary[];
  coverage: CoverageRow[];
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface Overview {
  stats: { announcements: number; companies: number; pdf_ok: number; queued: number };
  jobs: Job[];
  latest: AnnouncementSummary[];
}

export interface Submission {
  tax_code: string;
  ann_type: string;
  skipped: boolean;
  plan_status: string;
  needs_crawl: boolean;
  job: Job;
}

export interface CrawlResponse {
  results: Submission[];
  queued: number;
  skipped: number;
}

export interface PreviewItem {
  tax_code: string;
  ann_type: string;
  status: string;
  needs_crawl: boolean;
  message: string;
}

/** Crawl hàng loạt từ file Excel */
export interface ImportPair {
  ann_type: string;
  status: string;
  needs_crawl: boolean;
  message: string;
}

export interface ImportRow {
  line: number;
  tax_code: string;
  types: string[];
  date_from: string | null;
  date_to: string | null;
  force: boolean;
  errors: string[];
  warnings: string[];
  pairs: ImportPair[];
  to_run: number;
  to_skip: number;
}

export interface ImportResponse {
  filename: string;
  rows: ImportRow[];
  totals: { rows: number; valid: number; invalid: number; to_run: number; to_skip: number };
}

export interface BatchRow {
  tax_code: string;
  types: string[];
  date_from: string | null;
  date_to: string | null;
  force: boolean;
}

export interface PreviewResponse {
  items: PreviewItem[];
  invalid: string[];
  truncated: boolean;
}

export interface CrawlRequest {
  tax_codes: string;
  types: string[];
  date_from: string;
  date_to: string;
  force: boolean;
}
