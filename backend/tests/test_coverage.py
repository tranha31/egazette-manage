from datetime import date, datetime

import pytest

from app.coverage import FLOOR, Interval, describe, effective_interval, make_plan, merge, request_interval, subtract

D = date
NOW = datetime(2026, 11, 12, 10, 0, 0)   # "hôm nay" = 12/11/2026
TODAY = NOW.date()


def iv(a, b):
    return Interval(a, b)


def cov(f, t, at=datetime(2026, 11, 1, 9, 0, 0)):
    """Một lần crawl cũ (mặc định crawl từ 01/11, nên phủ hiệu lực tới 31/10)."""
    return (f, t, at)


# ---------- hàm khoảng cơ bản
def test_merge_overlap_and_adjacent():
    r = merge([iv(D(2024, 1, 10), D(2024, 1, 20)), iv(D(2024, 1, 1), D(2024, 1, 5)),
               iv(D(2024, 1, 6), D(2024, 1, 9)), iv(D(2024, 3, 1), D(2024, 3, 2))])
    assert r == [iv(D(2024, 1, 1), D(2024, 1, 20)), iv(D(2024, 3, 1), D(2024, 3, 2))]


def test_subtract_cases():
    req = iv(D(2024, 1, 1), D(2024, 12, 31))
    assert subtract(req, []) == [req]
    assert subtract(req, [req]) == []
    assert subtract(req, [iv(D(2023, 1, 1), D(2025, 1, 1))]) == []
    assert subtract(req, [iv(D(2024, 3, 1), D(2024, 6, 30))]) == [
        iv(D(2024, 1, 1), D(2024, 2, 29)), iv(D(2024, 7, 1), D(2024, 12, 31))]
    assert subtract(req, [iv(D(2023, 1, 1), D(2024, 6, 30))]) == [iv(D(2024, 7, 1), D(2024, 12, 31))]
    assert subtract(req, [iv(D(2024, 6, 1), D(2026, 1, 1))]) == [iv(D(2024, 1, 1), D(2024, 5, 31))]
    # các đoạn đã có liền kề nhau thì không tạo gap giữa chúng
    assert subtract(req, [iv(D(2024, 1, 1), D(2024, 6, 30)), iv(D(2024, 7, 1), D(2024, 12, 31))]) == []


def test_request_interval():
    assert request_interval(None, None, TODAY) == iv(FLOOR, TODAY)
    assert request_interval(D(2025, 1, 1), None, TODAY) == iv(D(2025, 1, 1), TODAY)
    assert request_interval(None, D(2025, 1, 1), TODAY) == iv(FLOOR, D(2025, 1, 1))
    assert request_interval(D(2025, 1, 1), D(2030, 1, 1), TODAY) == iv(D(2025, 1, 1), TODAY)  # tương lai bị cắt
    assert request_interval(D(2027, 1, 1), D(2027, 2, 1), TODAY) is None


# ---------- hiệu lực của lần crawl cũ
def test_effective_excludes_crawl_day():
    # crawl hôm qua (11/11) cho khoảng tới 11/11 -> chỉ chắc chắn tới 10/11
    at = datetime(2026, 11, 11, 15, 0)
    assert effective_interval(D(2026, 1, 1), D(2026, 11, 11), at, NOW, 60) == iv(D(2026, 1, 1), D(2026, 11, 10))
    # khoảng kết thúc trong quá khứ xa thì phủ trọn
    assert effective_interval(D(2024, 1, 1), D(2024, 12, 31), at, NOW, 60) == iv(D(2024, 1, 1), D(2024, 12, 31))


def test_effective_recheck_window_same_day():
    just = datetime(2026, 11, 12, 9, 30)    # 30 phút trước, cùng ngày -> coi hôm nay đã đủ
    old = datetime(2026, 11, 12, 7, 0)      # 3 giờ trước -> hôm nay chưa chắc đủ
    assert effective_interval(D(2026, 1, 1), TODAY, just, NOW, 60).end == TODAY
    assert effective_interval(D(2026, 1, 1), TODAY, old, NOW, 60).end == D(2026, 11, 11)
    assert effective_interval(D(2026, 11, 12), TODAY, old, NOW, 60) is None  # chỉ gồm hôm nay mà chưa chắc đủ


# ---------- kế hoạch crawl
def test_nothing_in_db_needs_full_crawl():
    p = make_plan(D(2024, 1, 1), D(2024, 12, 31), [], [], NOW)
    assert p.status == "missing" and p.needs_crawl
    assert (p.site_from, p.site_to) == (D(2024, 1, 1), D(2024, 12, 31))


def test_exact_same_range_is_skipped():
    p = make_plan(D(2024, 1, 1), D(2024, 12, 31), [cov(D(2024, 1, 1), D(2024, 12, 31))], [], NOW)
    assert p.status == "covered" and not p.needs_crawl


def test_sub_range_is_skipped():
    p = make_plan(D(2024, 3, 1), D(2024, 6, 30), [cov(D(2024, 1, 1), D(2024, 12, 31))], [], NOW)
    assert p.status == "covered"


def test_extension_crawls_only_the_missing_part():
    p = make_plan(D(2024, 1, 1), D(2025, 6, 30), [cov(D(2024, 1, 1), D(2024, 12, 31))], [], NOW)
    assert p.status == "partial"
    assert p.gaps == [iv(D(2025, 1, 1), D(2025, 6, 30))]
    assert (p.site_from, p.site_to) == (D(2025, 1, 1), D(2025, 6, 30))
    assert p.covered == [iv(D(2024, 1, 1), D(2024, 12, 31))]


def test_gap_in_the_middle_is_bounded_into_one_crawl():
    have = [cov(D(2024, 1, 1), D(2024, 3, 31)), cov(D(2024, 10, 1), D(2024, 12, 31))]
    p = make_plan(D(2023, 6, 1), D(2025, 3, 31), have, [], NOW)
    assert p.gaps == [iv(D(2023, 6, 1), D(2023, 12, 31)), iv(D(2024, 4, 1), D(2024, 9, 30)),
                      iv(D(2025, 1, 1), D(2025, 3, 31))]
    assert p.crawl == iv(D(2023, 6, 1), D(2025, 3, 31))   # 1 lần crawl duy nhất
    assert "1 lần" in describe(p)


def test_adjacent_stored_ranges_are_one_coverage():
    have = [cov(D(2024, 1, 1), D(2024, 6, 30)), cov(D(2024, 7, 1), D(2024, 12, 31))]
    assert make_plan(D(2024, 5, 1), D(2024, 8, 1), have, [], NOW).status == "covered"


def test_no_dates_means_everything_up_to_today():
    p = make_plan(None, None, [], [], NOW)
    assert p.status == "missing" and (p.site_from, p.site_to) == (None, None)   # không lọc ngày


def test_no_dates_after_earlier_full_crawl_only_fetches_new_days():
    # lần trước crawl "tất cả" lúc 01/11 -> phủ tới 31/10; giờ chỉ cần 01/11 → 12/11
    p = make_plan(None, None, [cov(FLOOR, D(2026, 11, 1))], [], NOW)
    assert p.status == "partial"
    assert p.crawl == iv(D(2026, 11, 1), TODAY)
    assert (p.site_from, p.site_to) == (D(2026, 11, 1), TODAY)


def test_today_is_recrawled_after_window_but_not_inside_it():
    done_3h_ago = [cov(FLOOR, TODAY, datetime(2026, 11, 12, 7, 0))]
    p = make_plan(None, None, done_3h_ago, [], NOW)
    assert p.status == "partial" and p.crawl == iv(TODAY, TODAY)
    done_10m_ago = [cov(FLOOR, TODAY, datetime(2026, 11, 12, 9, 50))]
    assert make_plan(None, None, done_10m_ago, [], NOW).status == "covered"


def test_future_end_is_clamped_and_future_start_is_noop():
    have = [cov(D(2026, 1, 1), D(2026, 11, 12), datetime(2026, 11, 12, 9, 55))]
    assert make_plan(D(2026, 1, 1), D(2030, 1, 1), have, [], NOW).status == "covered"
    assert make_plan(D(2027, 1, 1), D(2027, 3, 1), [], [], NOW).status == "future"


def test_pending_jobs_reserve_their_range():
    pend = [iv(D(2024, 1, 1), D(2024, 12, 31))]
    assert make_plan(D(2024, 2, 1), D(2024, 3, 1), [], pend, NOW).status == "covered"
    p = make_plan(D(2024, 1, 1), D(2025, 3, 31), [], pend, NOW)
    assert p.gaps == [iv(D(2025, 1, 1), D(2025, 3, 31))]


def test_force_ignores_database():
    p = make_plan(D(2024, 1, 1), D(2024, 12, 31), [cov(D(2024, 1, 1), D(2024, 12, 31))], [], NOW, force=True)
    assert p.status == "forced" and p.crawl == iv(D(2024, 1, 1), D(2024, 12, 31))
    assert (p.site_from, p.site_to) == (D(2024, 1, 1), D(2024, 12, 31))


def test_one_sided_dates_get_explicit_site_range():
    p = make_plan(D(2025, 1, 1), None, [], [], NOW)
    assert (p.site_from, p.site_to) == (D(2025, 1, 1), TODAY)
    p = make_plan(None, D(2020, 12, 31), [], [], NOW)
    assert (p.site_from, p.site_to) == (FLOOR, D(2020, 12, 31))


def test_interval_validation():
    with pytest.raises(ValueError):
        Interval(D(2025, 1, 2), D(2025, 1, 1))
