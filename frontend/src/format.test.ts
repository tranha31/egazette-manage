import { describe, expect, it } from "vitest";
import { bytes, dmy, dmyhm, qs, range } from "./format";

describe("format", () => {
  it("định dạng ngày và ngày giờ", () => {
    expect(dmy("2026-05-12")).toBe("12/05/2026");
    expect(dmy(null)).toBe("");
    expect(dmyhm("2026-05-12T17:06:00")).toBe("12/05/2026 17:06:00");
    expect(dmyhm("2026-05-12T17:06")).toBe("12/05/2026 17:06:00");
    expect(dmyhm(undefined)).toBe("");
  });
  it("dung lượng file", () => {
    expect(bytes(0)).toBe("");
    expect(bytes(null)).toBe("");
    expect(bytes(512)).toBe("512 B");
    expect(bytes(333658)).toBe("325,8 KB");
    expect(bytes(5 * 1024 * 1024)).toBe("5,0 MB");
  });
  it("khoảng ngày", () => {
    expect(range(null, null)).toBe("tất cả");
    expect(range("2024-01-01", "2024-12-31")).toBe("01/01/2024 → 31/12/2024");
    expect(range("2024-01-01", null)).toBe("01/01/2024 → …");
  });
  it("query string bỏ giá trị rỗng", () => {
    expect(qs({ q: "lữ", page: 2, deep: true, pdf_only: false, tax: "" })).toBe("?q=l%E1%BB%AF&page=2&deep=1");
    expect(qs({})).toBe("");
  });
});
