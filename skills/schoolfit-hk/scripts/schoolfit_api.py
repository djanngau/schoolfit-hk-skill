#!/usr/bin/env python3
"""SchoolFit HK API helper for OpenClaw-compatible skills.

This script intentionally talks only to the public SchoolFit HK API. It does
not read local databases, Prisma files, snapshots, cookies, or private keys.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "https://schoolfit.hk"
ALLOWED_HOSTS = {"schoolfit.hk"}
SCHOOLFIT_SKILL_CLIENT_CODE = "schoolfit-openclaw-v1-reserved"
TIMEOUT_SECONDS = 15
RETRIES = 2


class SchoolFitError(RuntimeError):
    pass


def validate_base_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme != "https":
        raise SchoolFitError("Base URL must use https.")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise SchoolFitError("Refusing to call non-SchoolFit host. Allowed host: schoolfit.hk.")
    if parsed.username or parsed.password or parsed.port:
        raise SchoolFitError("Base URL must not include credentials or custom ports.")
    return base_url.rstrip("/")


def clean_params(params: dict[str, Any]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            cleaned[key] = "true" if value else "false"
        elif isinstance(value, list):
            if value:
                cleaned[key] = ",".join(str(item) for item in value if str(item).strip())
        else:
            text = str(value).strip()
            if text:
                cleaned[key] = text
    return cleaned


def make_url(base_url: str, path: str, params: dict[str, Any] | None = None) -> str:
    base = validate_base_url(base_url)
    if not path.startswith("/api/"):
        raise SchoolFitError("Only /api/ paths are allowed.")
    query = urllib.parse.urlencode(clean_params(params or {}))
    url = f"{base}{path}"
    return f"{url}?{query}" if query else url


def request_json(
    method: str,
    base_url: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    url = make_url(base_url, path, params)
    data = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "schoolfit-openclaw-skill/0.1.0",
        "X-SchoolFit-Skill-Code": SCHOOLFIT_SKILL_CLIENT_CODE,
    }
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last_error: Exception | None = None
    for attempt in range(RETRIES + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            message = safe_http_error(exc)
            if exc.code in {429, 500, 502, 503, 504} and attempt < RETRIES:
                time.sleep(0.6 * (attempt + 1))
                last_error = SchoolFitError(message)
                continue
            raise SchoolFitError(message) from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < RETRIES:
                time.sleep(0.6 * (attempt + 1))
                continue
            break
    raise SchoolFitError(f"SchoolFit API request failed: {last_error}") from None


def safe_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8")[:500]
        payload = json.loads(raw)
        detail = payload.get("error") or payload.get("message") or raw
    except Exception:
        detail = exc.reason
    return f"SchoolFit API returned HTTP {exc.code}: {detail}"


def as_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "有", "是"}:
        return True
    if normalized in {"0", "false", "no", "n", "無", "否"}:
        return False
    raise argparse.ArgumentTypeError("Expected a boolean value.")


def read_json_arg(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"Invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("JSON input must be an object.")
    return parsed


def compact_school(school: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": school.get("id"),
        "slug": school.get("slug"),
        "nameZh": school.get("nameZh"),
        "nameEn": school.get("nameEn"),
        "district": school.get("district"),
        "gender": school.get("gender"),
        "fundingType": school.get("fundingType"),
        "mediumOfInstruction": school.get("mediumOfInstruction"),
        "bandingReference": school.get("banding"),
        "annualTuitionHkd": school.get("annualTuitionHkd"),
        "summary": school.get("primaryReviewSummary") or school.get("purpose"),
    }


def compact_output(command: str, payload: Any) -> dict[str, Any]:
    if command == "search-schools":
        schools = [compact_school(item) for item in payload.get("schools", [])]
        return {
            "count": payload.get("count", len(schools)),
            "schools": schools,
            "pagination": payload.get("pagination"),
            "notes": SOURCE_NOTES,
        }
    if command == "school-detail":
        school = payload.get("school", {})
        return {"school": compact_school_detail(school), "notes": SOURCE_NOTES}
    if command == "compare":
        schools = [compact_compare_school(item) for item in payload.get("schools", [])]
        return {"count": payload.get("count", len(schools)), "schools": schools, "notes": SOURCE_NOTES}
    if command == "recommend":
        return {**payload, "notes": SOURCE_NOTES}
    if command == "vacancies":
        return {
            "source": payload.get("source"),
            "count": payload.get("count"),
            "vacancies": payload.get("vacancies", []),
            "pagination": payload.get("pagination"),
            "caveat": VACANCY_CAVEAT,
        }
    if command == "admissions":
        return {
            "source": payload.get("source"),
            "count": payload.get("count"),
            "notices": payload.get("notices", []),
            "pagination": payload.get("pagination"),
            "caveat": ADMISSION_CAVEAT,
        }
    return payload


def compact_school_detail(school: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": school.get("id"),
        "slug": school.get("slug"),
        "nameZh": school.get("nameZh"),
        "nameEn": school.get("nameEn"),
        "district": school.get("district"),
        "allocationDistricts": school.get("allocationDistricts"),
        "address": school.get("address"),
        "gender": school.get("gender"),
        "fundingType": school.get("fundingType"),
        "religion": school.get("religion"),
        "annualTuitionHkd": school.get("annualTuitionHkd"),
        "mediumOfInstruction": school.get("mediumOfInstruction"),
        "officialUrl": school.get("officialUrl"),
        "phone": school.get("phone"),
        "email": school.get("email"),
        "purpose": school.get("purpose"),
        "sourceName": school.get("sourceName"),
        "sourceUrl": school.get("sourceUrl"),
        "lastFetchedAt": school.get("lastFetchedAt"),
        "facts": (school.get("facts") or [])[:24],
        "externalSignals": compact_external_signals(school.get("externalSignals") or []),
        "reviewSignals": (school.get("reviewSignals") or [])[:6],
        "researchLinks": (school.get("researchLinks") or [])[:6],
    }


def compact_external_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted = []
    for signal in signals[:12]:
        compacted.append({
            "provider": signal.get("provider"),
            "signalType": signal.get("signalType"),
            "value": signal.get("value"),
            "confidence": signal.get("confidence"),
            "isOfficial": signal.get("isOfficial"),
            "sourceUrl": signal.get("sourceUrl"),
            "lastSeenAt": signal.get("lastSeenAt"),
        })
    return compacted


def compact_compare_school(school: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": school.get("id"),
        "slug": school.get("slug"),
        "nameZh": school.get("nameZh"),
        "nameEn": school.get("nameEn"),
        "district": school.get("district"),
        "fundingType": school.get("fundingType"),
        "gender": school.get("gender"),
        "mediumOfInstruction": school.get("mediumOfInstruction"),
        "annualTuitionHkd": school.get("annualTuitionHkd"),
        "bandingReference": school.get("banding"),
        "schoolEthos": school.get("schoolEthos"),
        "vacancySummary": compact_vacancy_summary(school.get("vacancySummary")),
        "admissionNoticeSummary": compact_admission_summary(school.get("admissionNoticeSummary")),
    }


def compact_vacancy_summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if not summary:
        return None
    return {
        "schoolId": summary.get("schoolId"),
        "dataMonth": summary.get("dataMonth"),
        "sourceName": summary.get("sourceName"),
        "sourceUrl": summary.get("sourceUrl"),
        "lastSeenAt": summary.get("lastSeenAt"),
        "openGrades": summary.get("openGrades"),
        "limitedGrades": summary.get("limitedGrades"),
        "hasAnyVacancy": summary.get("hasAnyVacancy"),
        "vacancies": (summary.get("vacancies") or [])[:8],
    }


def compact_admission_summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if not summary:
        return None
    return {
        "schoolId": summary.get("schoolId"),
        "sourceName": summary.get("sourceName"),
        "sourceType": summary.get("sourceType"),
        "fetchedAt": summary.get("fetchedAt"),
        "lastSeenAt": summary.get("lastSeenAt"),
        "noticeCount": summary.get("noticeCount"),
        "activeNoticeCount": summary.get("activeNoticeCount"),
        "nextDeadline": summary.get("nextDeadline"),
        "grades": summary.get("grades"),
        "applicationMethods": summary.get("applicationMethods"),
        "notices": (summary.get("notices") or [])[:6],
    }


SOURCE_NOTES = [
    "Official facts should be treated separately from third-party Band references and parent/community summaries.",
    "Banding references are not official EDB facts and must not be presented as official bands.",
    "When vacancy or admission data is used, cite source, data month/fetched time, last seen time, confidence, and ask families to confirm with the school.",
]

VACANCY_CAVEAT = (
    "EDB vacancy data is time-sensitive and updated by period/month. It is a decision signal, "
    "not an admission guarantee. Families should confirm latest availability directly with the school."
)

ADMISSION_CAVEAT = (
    "Admission notices are extracted from school/public pages and may change. Check the original notice "
    "and confirm deadlines, forms, and eligibility directly with the school."
)


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False))


def print_markdown(command: str, data: dict[str, Any]) -> None:
    if command == "search-schools":
        print(f"## SchoolFit HK 搜尋結果\n\n共 {data.get('count', 0)} 間。")
        for school in data.get("schools", [])[:20]:
            name = school.get("nameZh") or school.get("nameEn") or school.get("slug")
            print(f"- **{name}** ({school.get('district', '地區不明')})")
            print(f"  - slug: `{school.get('slug')}`")
            print(f"  - 類型: {school.get('gender')} / {school.get('fundingType')} / {school.get('mediumOfInstruction')}")
            print(f"  - Band 參考: {school.get('bandingReference') or '暫無可靠資料'}")
        print_caveats()
        return
    if command == "vacancies":
        source = data.get("source") or {}
        print("## SchoolFit HK 學額資料")
        print(f"\n來源: {source.get('sourceName', '未知')}  \n擷取時間: {source.get('fetchedAt', '未知')}  \n共 {data.get('count', 0)} 筆。")
        for item in data.get("vacancies", [])[:30]:
            print(f"- {item.get('schoolNameRaw')} / {item.get('grade')}: {item.get('status')}")
            print(f"  - dataMonth: {item.get('dataMonth')} | lastSeenAt: {item.get('lastSeenAt')} | confidence: {item.get('confidence')}")
        print(f"\n> {data.get('caveat')}")
        return
    if command == "admissions":
        source = data.get("source") or {}
        print("## SchoolFit HK 招生通告")
        print(f"\n來源: {source.get('sourceName', '未知')}  \n擷取時間: {source.get('fetchedAt', '未知')}  \n共 {data.get('count', 0)} 則。")
        for item in data.get("notices", [])[:20]:
            print(f"- **{item.get('title')}**")
            print(f"  - schoolId: `{item.get('schoolId')}` | grades: {', '.join(item.get('applicationGrades') or [])}")
            print(f"  - deadline: {item.get('deadline') or '暫無'} | active: {item.get('isActive')} | confidence: {item.get('confidence')}")
            print(f"  - url: {item.get('noticeUrl')}")
        print(f"\n> {data.get('caveat')}")
        return
    print_json(data)


def print_caveats() -> None:
    print("\n## 資料邊界")
    for note in SOURCE_NOTES:
        print(f"- {note}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Call the public SchoolFit HK API safely.")
    parser.add_argument("--base-url", default=os.environ.get("SCHOOLFIT_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search-schools", help="Search SchoolFit HK school summaries.")
    add_output_options(search)
    add_common_filters(search)

    detail = sub.add_parser("school-detail", help="Get one school detail by slug or id.")
    add_output_options(detail)
    detail.add_argument("slug")

    compare = sub.add_parser("compare", help="Compare up to 4 schools by id/slug.")
    add_output_options(compare)
    compare.add_argument("ids", help="Comma-separated school ids/slugs.")

    recommend = sub.add_parser("recommend", help="Run SchoolFit recommendation buckets.")
    add_output_options(recommend)
    recommend.add_argument("--input-json", help="Recommendation input JSON object.")
    recommend.add_argument("--district")
    recommend.add_argument("--banding")
    recommend.add_argument("--gender")
    recommend.add_argument("--medium")
    recommend.add_argument("--application-goal")
    recommend.add_argument("--language-priority")
    recommend.add_argument("--support-needs", nargs="*")
    recommend.add_argument("--accepts-dss", type=as_bool)
    recommend.add_argument("--max-tuition", type=float)
    recommend.add_argument("--commute-minutes", type=float)
    recommend.add_argument("--personality")
    recommend.add_argument("--priorities", nargs="*")
    recommend.add_argument("--notes")

    vacancies = sub.add_parser("vacancies", help="Query EDB vacancy records exposed by SchoolFit.")
    add_output_options(vacancies)
    vacancies.add_argument("--school-id")
    vacancies.add_argument("--district")
    vacancies.add_argument("--grade", choices=["S1", "S2", "S3", "S4", "S5", "S6"])
    vacancies.add_argument("--status")
    vacancies.add_argument("--source-type")
    vacancies.add_argument("--has-vacancy", type=as_bool)
    vacancies.add_argument("--q")
    vacancies.add_argument("--page", type=int)
    vacancies.add_argument("--page-size", type=int, default=100)

    admissions = sub.add_parser("admissions", help="Query school admission notices.")
    add_output_options(admissions)
    admissions.add_argument("--school-id")
    admissions.add_argument("--grade", choices=["S1", "S2", "S3", "S4", "S5", "S6"])
    admissions.add_argument("--is-active", type=as_bool)
    admissions.add_argument("--confidence")
    admissions.add_argument("--q")
    admissions.add_argument("--page", type=int)
    admissions.add_argument("--page-size", type=int, default=100)

    return parser


def add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=["json", "markdown"], default=argparse.SUPPRESS)


def add_common_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--q")
    parser.add_argument("--district")
    parser.add_argument("--banding")
    parser.add_argument("--gender")
    parser.add_argument("--medium")
    parser.add_argument("--funding-type")
    parser.add_argument("--religion")
    parser.add_argument("--max-tuition", type=float)
    parser.add_argument("--vacancy-grade", choices=["S1", "S2", "S3", "S4", "S5", "S6"])
    parser.add_argument("--vacancy-status")
    parser.add_argument("--has-vacancy", type=as_bool)
    parser.add_argument("--page", type=int)
    parser.add_argument("--page-size", type=int, default=24)


def run(args: argparse.Namespace) -> dict[str, Any]:
    base_url = validate_base_url(args.base_url)
    command = args.command
    if command == "search-schools":
        payload = request_json("GET", base_url, "/api/schools", params={
            "q": args.q,
            "district": args.district,
            "banding": args.banding,
            "gender": args.gender,
            "medium": args.medium,
            "fundingType": args.funding_type,
            "religion": args.religion,
            "maxTuition": args.max_tuition,
            "vacancyGrade": args.vacancy_grade,
            "vacancyStatus": args.vacancy_status,
            "hasVacancy": args.has_vacancy,
            "page": args.page,
            "pageSize": args.page_size,
        })
    elif command == "school-detail":
        slug = urllib.parse.quote(args.slug.strip(), safe="")
        payload = request_json("GET", base_url, f"/api/schools/{slug}")
    elif command == "compare":
        ids = [item.strip() for item in args.ids.split(",") if item.strip()][:4]
        if not ids:
            raise SchoolFitError("At least one school id/slug is required.")
        payload = request_json("GET", base_url, "/api/compare", params={"ids": ids})
    elif command == "recommend":
        body = read_json_arg(args.input_json)
        body.update(clean_params({
            "district": args.district,
            "banding": args.banding,
            "gender": args.gender,
            "medium": args.medium,
            "applicationGoal": args.application_goal,
            "languagePriority": args.language_priority,
            "personality": args.personality,
            "notes": args.notes,
        }))
        if args.support_needs:
            body["supportNeeds"] = args.support_needs
        if args.priorities:
            body["priorities"] = args.priorities
        if args.accepts_dss is not None:
            body["acceptsDss"] = args.accepts_dss
        if args.max_tuition is not None:
            body["maxTuition"] = args.max_tuition
        if args.commute_minutes is not None:
            body["commuteMinutes"] = args.commute_minutes
        payload = request_json("POST", base_url, "/api/agent/recommend", body=body)
    elif command == "vacancies":
        payload = request_json("GET", base_url, "/api/vacancies", params={
            "schoolId": args.school_id,
            "district": args.district,
            "grade": args.grade,
            "status": args.status,
            "sourceType": args.source_type,
            "hasVacancy": args.has_vacancy,
            "q": args.q,
            "page": args.page,
            "pageSize": args.page_size,
        })
    elif command == "admissions":
        payload = request_json("GET", base_url, "/api/admission-notices", params={
            "schoolId": args.school_id,
            "grade": args.grade,
            "isActive": args.is_active,
            "confidence": args.confidence,
            "q": args.q,
            "page": args.page,
            "pageSize": args.page_size,
        })
    else:
        raise SchoolFitError(f"Unsupported command: {command}")
    return compact_output(command, payload)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        output = run(args)
    except SchoolFitError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if args.format == "markdown":
        print_markdown(args.command, output)
    else:
        print_json(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
