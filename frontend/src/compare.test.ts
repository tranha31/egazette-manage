import { describe, expect, it } from "vitest";
import { buildComparison, diffWords, orderedUnion } from "./compare";

const g = (name: string, ...kv: [string, string][]) => ({ name, fields: kv.map(([key, value]) => ({ key, value })) });

describe("buildComparison", () => {
  it("giữ nguyên các nhóm không có tiền tố", () => {
    const c = buildComparison([g("Thông tin chung", ["Tên", "A"]), g("Người đại diện theo pháp luật #1", ["Họ và tên", "B"])]);
    expect(c.general.map((x) => x.name)).toEqual(["Thông tin chung", "Người đại diện theo pháp luật #1"]);
    expect(c.sections).toEqual([]);
  });

  it("nhận biết dòng giống, đổi, thêm, bớt", () => {
    const c = buildComparison([
      g("[CŨ] Thông tin về vốn", ["Vốn điều lệ", "100"], ["Số cổ phần", "10"], ["Chỉ có cũ", "x"]),
      g("[MỚI] Thông tin về vốn", ["Vốn điều lệ", "200"], ["Số cổ phần", "10"], ["Chỉ có mới", "y"]),
    ]);
    expect(c.sections).toHaveLength(1);
    const s = c.sections[0];
    expect(s.side).toBe("both");
    expect(s.rows.map((r) => [r.key, r.status])).toEqual([
      ["Vốn điều lệ", "changed"],
      ["Số cổ phần", "same"],
      ["Chỉ có cũ", "removed"], // "bớt" luôn đứng trước "thêm" tại cùng vị trí
      ["Chỉ có mới", "added"],
    ]);
    expect(s.rows[0]).toMatchObject({ oldValue: "100", newValue: "200" });
    expect(s.changed).toBe(3);
    expect(c.changed).toBe(3);
    expect(c.total).toBe(4);
  });

  it("coi 'Thông tin cổ phần' và 'Thông tin về cổ phần' là một mục", () => {
    const c = buildComparison([g("[CŨ] Thông tin cổ phần", ["Mệnh giá", "10.000"]), g("[MỚI] Thông tin về cổ phần", ["Mệnh giá", "10.000"])]);
    expect(c.sections).toHaveLength(1);
    expect(c.sections[0]).toMatchObject({ side: "both", changed: 0, title: "Thông tin về cổ phần" });
  });

  it("mục chỉ có ở một bên: toàn bộ dòng là thêm hoặc bớt", () => {
    const c = buildComparison([g("[MỚI] Thông tin về thuế", ["Email", "a@b.c"]), g("[CŨ] Chi nhánh", ["Tên", "CN1"])]);
    const tax = c.sections.find((s) => s.title.includes("thuế"))!;
    const branch = c.sections.find((s) => s.title === "Chi nhánh")!;
    expect(tax.side).toBe("new");
    expect(tax.rows[0].status).toBe("added");
    expect(branch.side).toBe("old");
    expect(branch.rows[0].status).toBe("removed");
  });

  it("danh sách ngành nghề so theo nội dung, không theo số thứ tự", () => {
    const c = buildComparison([
      g("[CŨ] Ngành, nghề kinh doanh", ["Ngành nghề #1", "6201 - Lập trình"], ["Ngành nghề #2", "6202 - Tư vấn"]),
      // thêm một ngành vào đầu làm lệch số thứ tự của hai ngành cũ
      g("[MỚI] Ngành, nghề kinh doanh", ["Ngành nghề #1", "4651 - Bán buôn"], ["Ngành nghề #2", "6201 - Lập trình"], ["Ngành nghề #3", "6202 - Tư vấn"]),
    ]);
    const rows = c.sections[0].rows;
    expect(rows.map((r) => r.status)).toEqual(["added", "same", "same"]);
    expect(rows[0]).toMatchObject({ key: "Ngành nghề", newValue: "4651 - Bán buôn", oldValue: null });
    expect(c.changed).toBe(1);
  });

  it("cùng mã ngành nhưng đổi tên thì là 'đã đổi', không phải bỏ + thêm", () => {
    const c = buildComparison([
      g("[CŨ] Ngành, nghề kinh doanh", ["Ngành nghề #1", "4651 - Bán buôn máy vi tính | Chi tiết: A"], ["Ngành nghề #2", "7020 - Tư vấn"]),
      g("[MỚI] Ngành, nghề kinh doanh", ["Ngành nghề #1", "4651 - Bán buôn máy tính | Chi tiết: A"], ["Ngành nghề #2", "6290 - Dịch vụ khác"]),
    ]);
    expect(c.sections[0].rows.map((r) => r.status)).toEqual(["changed", "removed", "added"]);
    expect(c.sections[0].rows[0]).toMatchObject({ oldValue: "4651 - Bán buôn máy vi tính | Chi tiết: A", newValue: "4651 - Bán buôn máy tính | Chi tiết: A" });
  });

  it("khoá lặp lại trong một nhóm được ghép theo thứ tự xuất hiện", () => {
    const c = buildComparison([
      g("[CŨ] Văn phòng đại diện #1", ["Tên", "VP1"], ["Địa chỉ", "A"], ["Tên", "VP2"], ["Địa chỉ", "B"]),
      g("[MỚI] Văn phòng đại diện #1", ["Tên", "VP1"], ["Địa chỉ", "A"], ["Tên", "VP2"], ["Địa chỉ", "C"]),
    ]);
    expect(c.sections[0].rows.map((r) => r.status)).toEqual(["same", "same", "same", "changed"]);
  });

  it("bỏ qua khác biệt chỉ ở khoảng trắng", () => {
    const c = buildComparison([g("[CŨ] X", ["k", "a  b"]), g("[MỚI] X", ["k", "a b "])]);
    expect(c.sections[0].rows[0].status).toBe("same");
  });
});

describe("orderedUnion", () => {
  it("chèn phần tử mới đúng sau phần tử đứng trước nó", () => {
    expect(orderedUnion(["a", "c"], ["a", "b", "c", "d"])).toEqual(["a", "b", "c", "d"]);
    expect(orderedUnion(["a", "b"], ["x", "a", "b"])).toEqual(["x", "a", "b"]);
    expect(orderedUnion([], ["a"])).toEqual(["a"]);
  });
});

describe("diffWords", () => {
  it("đánh dấu phần ở giữa khác nhau", () => {
    const d = diffWords("Tầng 9, toà nhà A, Hà Nội", "Tầng 12, toà nhà A, Hà Nội");
    expect(d.old.find((p) => p.mark)?.text).toBe("9,");
    expect(d.new.find((p) => p.mark)?.text).toBe("12,");
    expect(d.old.map((p) => p.text).join("")).toBe("Tầng 9, toà nhà A, Hà Nội");
  });
  it("đánh dấu riêng từng chỗ khác nhau thay vì cả đoạn giữa", () => {
    const d = diffWords("Tỉ lệ (%) 69,807 | Số lượng 263.743", "Tỉ lệ (%) 70,047 | Số lượng 266.776");
    expect(d.old.filter((p) => p.mark).map((p) => p.text)).toEqual(["69,807", "263.743"]);
    expect(d.new.filter((p) => p.mark).map((p) => p.text)).toEqual(["70,047", "266.776"]);
    expect(d.old.map((p) => p.text).join("")).toBe("Tỉ lệ (%) 69,807 | Số lượng 263.743");
  });
  it("chuỗi rất dài vẫn chạy được (không nổ bộ nhớ)", () => {
    const long = Array.from({ length: 2000 }, (_, i) => `w${i}`).join(" ");
    const d = diffWords(long + " cũ", long + " mới");
    expect(d.old.some((p) => p.mark) && d.new.some((p) => p.mark)).toBe(true);
  });
  it("hai chuỗi giống nhau không có phần đánh dấu", () => {
    expect(diffWords("a b", "a b").old.some((p) => p.mark)).toBe(false);
  });
});
