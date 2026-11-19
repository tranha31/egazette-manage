"""Chuyển đối tượng database thành dict JSON cho API (ngày: 'YYYY-MM-DD', ngày giờ: 'YYYY-MM-DDTHH:MM:SS')."""
from .models import STATUS_CLASS, STATUS_LABEL, TYPES
from .storage import location


def iso(d):
    return d.isoformat() if d else None


def job_dict(j, with_log=False):
    d = {
        "id": j.id, "tax_code": j.tax_code, "ann_type": j.ann_type, "ann_type_name": TYPES.get(j.ann_type, j.ann_type),
        "req_from": iso(j.req_from), "req_to": iso(j.req_to),
        "crawl_from": iso(j.crawl_from), "crawl_to": iso(j.crawl_to),
        "cover_from": iso(j.cover_from), "cover_to": iso(j.cover_to),
        "force": bool(j.force), "status": j.status, "message": j.message or "",
        "result_count": j.result_count or 0, "new_count": j.new_count or 0,
        "pdf_ok": j.pdf_ok or 0, "pdf_fail": j.pdf_fail or 0,
        "created_at": iso(j.created_at), "started_at": iso(j.started_at), "finished_at": iso(j.finished_at),
    }
    if with_log:
        d["log"] = j.log or ""
    return d


def rep_dict(r):
    return {
        "seq": r.seq, "full_name": r.full_name, "gender": r.gender, "position": r.position,
        "birth_date": iso(r.birth_date), "ethnicity": r.ethnicity, "nationality": r.nationality,
        "id_doc_type": r.id_doc_type, "id_number": r.id_number, "id_issue_date": iso(r.id_issue_date),
        "id_issue_place": r.id_issue_place, "residence_address": r.residence_address,
        "contact_address": r.contact_address,
    }


def announcement_summary(a):
    """Dòng trong danh sách."""
    return {
        "id": a.id, "tax_code": a.tax_code, "ann_type": a.ann_type, "ann_type_name": TYPES.get(a.ann_type, a.ann_type),
        "posted_at": iso(a.posted_at), "title": a.title, "company_name": a.company_name,
        "doc_tax_code": a.doc_tax_code, "established_date": iso(a.established_date), "hq_address": a.hq_address,
        "charter_capital": a.charter_capital, "reg_change_date": iso(a.reg_change_date), "reg_place": a.reg_place,
        "has_pdf": a.pdf_status == "ok" and bool(a.pdf_bucket and a.pdf_path),   # file thật sự nằm trên MinIO
        "pdf_status": a.pdf_status, "parse_status": a.parse_status,
        "reps": [{"full_name": r.full_name, "position": r.position, "id_number": r.id_number} for r in a.reps],
    }


def announcement_detail(a):
    groups, order = {}, []
    for f in a.fields:
        if f.grp not in groups:
            groups[f.grp] = []
            order.append(f.grp)
        groups[f.grp].append({"key": f.field_key, "value": f.field_value})
    d = announcement_summary(a)
    d.update({
        "start_at": a.start_at, "end_at": a.end_at, "place": a.place, "change_type": a.change_type,
        "pdf_bucket": a.pdf_bucket, "pdf_key": a.pdf_path, "pdf_location": location(a.pdf_bucket, a.pdf_path),
        "pdf_size": a.pdf_size or 0,
        "reps": [rep_dict(r) for r in a.reps],
        "groups": [{"name": g, "fields": groups[g]} for g in order],
    })
    return d


def person_dict(rep, ann):
    d = rep_dict(rep)
    d["announcement"] = {"id": ann.id, "tax_code": ann.tax_code, "company_name": ann.company_name,
                         "posted_at": iso(ann.posted_at), "ann_type": ann.ann_type}
    return d


def company_row(c):
    a = c["latest"]
    return {"tax_code": c["tax_code"], "count": c["count"], "last_at": iso(c["last_at"]),
            "company_name": a.company_name if a else "", "hq_address": a.hq_address if a else "", "reps": c["reps"]}


def coverage_dict(c):
    r, eff = c["row"], c["effective"]
    return {"ann_type": r.ann_type, "date_from": iso(r.date_from), "date_to": iso(r.date_to),
            "crawled_at": iso(r.crawled_at), "result_count": r.result_count,
            "effective": {"start": iso(eff.start), "end": iso(eff.end)} if eff else None}


def submission_dict(s):
    return {"tax_code": s.tax_code, "ann_type": s.ann_type, "skipped": s.skipped, "plan_status": s.plan.status,
            "needs_crawl": s.plan.needs_crawl, "job": job_dict(s.job)}


def meta():
    return {"types": [{"code": k, "name": v} for k, v in TYPES.items()],
            "statuses": {k: {"label": STATUS_LABEL[k], "tone": STATUS_CLASS[k]} for k in STATUS_LABEL}}
