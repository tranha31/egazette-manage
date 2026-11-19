import type { BatchRow, CrawlRequest, CrawlResponse, ImportResponse, Job, PreviewResponse, WorkerStatus } from "./types";

/** Để trống = cùng origin (dev: Vite chuyển tiếp /api; chạy thật: backend phục vụ luôn dist). */
export const API_BASE = ((import.meta.env.VITE_API_URL as string | undefined) ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  errors: string[];
  constructor(message: string, status: number, errors: string[] = []) {
    super(message);
    this.status = status;
    this.errors = errors.length ? errors : [message];
  }
}

async function request<T>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" };
  // FormData (upload file) để trình duyệt tự đặt Content-Type kèm boundary
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(API_BASE + path, {
      ...init,
      headers,
      signal,
      credentials: API_BASE ? "include" : "same-origin",
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("Không kết nối được tới máy chủ. Backend đã chạy chưa?", 0);
  }
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    /* phản hồi không phải JSON (vd lỗi từ proxy) */
  }
  if (!res.ok) {
    const d = (data ?? {}) as { error?: string; errors?: string[] };
    throw new ApiError(d.error || `Lỗi ${res.status}`, res.status, d.errors);
  }
  return data as T;
}

export const get = <T>(path: string, signal?: AbortSignal) => request<T>(path, {}, signal);
export const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

const upload = <T>(path: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return request<T>(path, { method: "POST", body: form });
};

export const api = {
  importFile: (file: File) => upload<ImportResponse>("/api/crawl/import", file),
  batch: (rows: BatchRow[]) => post<CrawlResponse>("/api/crawl/batch", { rows }),
  crawl: (b: CrawlRequest) => post<CrawlResponse>("/api/crawl", b),
  preview: (b: CrawlRequest) => post<PreviewResponse>("/api/crawl/preview", b),
  cancelJob: (id: number) => post<Job>(`/api/jobs/${id}/cancel`),
  retryJob: (id: number) => post<Job>(`/api/jobs/${id}/retry`),
  resumeWorker: () => post<WorkerStatus>("/api/worker/resume"),
};

/** Đường dẫn tới file PDF / file Excel (mở bằng thẻ <a>, <iframe> nên phải là URL đầy đủ). */
export const fileUrl = (annId: number, download = false) =>
  `${API_BASE}/api/files/${annId}${download ? "?download=1" : ""}`;
export const exportUrl = (query: string) => `${API_BASE}/api/search/export.xlsx${query}`;
export const templateUrl = `${API_BASE}/api/crawl/template.xlsx`;
