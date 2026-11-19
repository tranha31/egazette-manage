import { describe, expect, it } from "vitest";
import { pageWindow } from "./Pager";

describe("pageWindow", () => {
  it("ít trang thì hiện hết", () => {
    expect(pageWindow(1, 1)).toEqual([1]);
    expect(pageWindow(3, 7)).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });
  it("rút gọn bằng dấu … ở giữa", () => {
    expect(pageWindow(10, 20)).toEqual([1, 2, "…", 9, 10, 11, "…", 19, 20]);
  });
  it("gần đầu / gần cuối thì chỉ có một dấu …", () => {
    expect(pageWindow(1, 20)).toEqual([1, 2, 3, 4, 5, "…", 19, 20]);
    expect(pageWindow(20, 20)).toEqual([1, 2, "…", 16, 17, 18, 19, 20]);
  });
  it("luôn chứa trang hiện tại và không lặp", () => {
    for (let pages = 1; pages <= 30; pages++) {
      for (let p = 1; p <= pages; p++) {
        const w = pageWindow(p, pages);
        expect(w).toContain(p);
        const nums = w.filter((x): x is number => x !== "…");
        expect(new Set(nums).size).toBe(nums.length);
        expect(nums).toEqual([...nums].sort((a, b) => a - b));
      }
    }
  });
});
