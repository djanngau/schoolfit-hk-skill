#!/usr/bin/env python3
"""SchoolFit HK API helper for OpenClaw-compatible skills.

This script intentionally talks only to the public SchoolFit HK API. It does
not read local databases, Prisma files, snapshots, cookies, or private keys.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "https://schoolfit.hk"
ALLOWED_HOSTS = {"schoolfit.hk"}
SKILL_VERSION = "1.0.15"
SKILL_VERSION_HEADER_VERSION = "1.0.15"
MAX_COMPARE_IDS = 4
ROBUST_SEARCH_PAGE_SIZE = 1000
SCHOOLFIT_SKILL_CLIENT_CODE = "schoolfit-openclaw-v1-reserved"
TIMEOUT_SECONDS = 15
RETRIES = 2
SKILL_CODE_HEADER = "X-SchoolFit-Skill-Code"
SKILL_TRACE_HEADER = "X-SchoolFit-Skill-Trace-Id"
SKILL_VERSION_HEADER = "X-SchoolFit-Skill-Version"
SKILL_ACTIVATION_STATUS_HEADER = "X-SchoolFit-Skill-Activation-Status"
ACTIVATION_PAGE_PATH = "/skill-code"
ACTIVATION_PAGE_URL = f"{DEFAULT_BASE_URL}{ACTIVATION_PAGE_PATH}"
SKILL_REQUIRES_CODE_MESSAGE = (
    "請先開啟 https://schoolfit.hk/skill-code 取得授權碼，複製後直接在聊天窗口發給 Agent。"
)
SKILL_ACTIVATION_HINT = (
    "請先到 https://schoolfit.hk/skill-code 取得授權碼，複製後直接在聊天窗口發給 Agent。"
)
SKILL_USAGE_EVENT = "command_run"
SKILL_TELEMETRY_ENDPOINT = "/api/skill/telemetry"
SKILL_CODE_HASH_PREFIX_LEN = 8
PUBLIC_COMMANDS = {"quick-start", "parse-parent-request", "school-levels", "marketplace-demo", "self-check"}
SKILL_CODE_RE = re.compile(r"\bsfhk_[A-Za-z0-9_-]{8,}\b")
HKID_RE = re.compile(r"\b[A-Z]{1,2}\d{6}\(?[0-9A]\)?\b", re.IGNORECASE)
HK_PHONE_RE = re.compile(r"(?<!\d)(?:\+?852[-\s]?)?[456789]\d{3}[-\s]?\d{4}(?!\d)")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PII_WARNING_MESSAGE = (
    "為保護學生私隱，請不要在 Skill 請求中提供學生全名、HKID、電話、住址、成績表 PDF 或其他可識別個人資料。"
)
SCHOOLFIT_SKILL_CONFIG_ENV = "SCHOOLFIT_SKILL_CODE"
SCHOOLFIT_SKILL_LEGACY_CODE_ENV = "SCHOOLFIT_SKILL_API_CODE"
SCHOOLFIT_SKILL_CONFIG_PATH_ENV = "SCHOOLFIT_SKILL_CONFIG"
DEFAULT_SKILL_CONFIG_PATH = os.path.expanduser("~/.schoolfit-hk/skill.json")

TraceId = str
ActivationMode = str

SCHOOL_LEVELS = ("secondary", "primary", "kindergarten", "international", "postsecondary")
SCHOOL_LEVEL_LABELS = {
    "secondary": "中學資料庫",
    "primary": "小學資料庫",
    "kindergarten": "幼稚園資料庫",
    "international": "國際學校資料庫",
    "postsecondary": "專上教育庫",
}
SCHOOL_LEVEL_COUNTS = {
    "secondary": 441,
    "primary": 507,
    "kindergarten": 955,
    "international": 103,
    "postsecondary": 35,
}
SCHOOL_LEVEL_PROMPTS = {
    "secondary": [
        "沙田 Band 1 英文男女校，想穩陣，不考慮直資。",
        "九龍城 Band 1 女校，英文環境，有沒有學額或招生提醒？",
    ],
    "primary": [
        "九龍城小學，英文環境，通勤短，想先看資助/直資分別。",
        "港島小學，重視校風和升中銜接。",
    ],
    "kindergarten": [
        "荃灣幼稚園 K1，想看全日制和學費範圍。",
        "九龍區幼稚園，偏好學券、近屋企。",
    ],
    "international": [
        "港島國際學校，想了解 IB/A-Level 路線和學費。",
        "新界國際學校，有沒有寄宿或英文支援？",
    ],
    "postsecondary": [
        "JUPAS、本科、HD/副學士銜接有哪些選項？",
        "專上教育，想比較副學士和高級文憑升學路線。",
    ],
}
INTERACTION_STYLE = {
    "tone": "warm, concise, parent-friendly, and evidence-conscious",
    "opening": "可以，我先幫你把條件收窄，再用 SchoolFit HK 資料逐步核實。",
    "askMissingInfo": "我先不需要孩子姓名或證件資料，只要補充以下幾點就可以幫你查得更準：",
    "privacyReassurance": "為保護學生私隱，請先刪走可識別個人資料；保留地區、年級、偏好和預算已足夠。",
    "sourceReassurance": "我會把官方資料、非官方參考、學額和招生時效分開說明。",
}
FILTER_LABELS = {
    "level": "資料庫",
    "region": "區域",
    "district": "地區",
    "banding": "Band 參考",
    "gender": "性別偏好",
    "medium": "授課語言",
    "fundingType": "辦學類型",
    "religion": "宗教",
    "maxTuition": "學費上限",
    "vacancyGrade": "年級/學額年級",
    "hasVacancy": "只看有學額訊號",
}
SIGNAL_LABELS = {
    "responseLanguage": "回覆語言",
    "level": "資料庫",
    "levelLabel": "資料庫名稱",
    "region": "區域",
    "district": "地區",
    "banding": "Band 參考",
    "gender": "性別偏好",
    "medium": "授課語言",
    "languagePriority": "語言優先",
    "acceptsDss": "是否接受直資",
    "riskPreference": "風險偏好",
    "grade": "年級",
    "priorities": "重視因素",
    "supportNeeds": "支援需要",
    "maxTuition": "學費上限",
}


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


def canonical_activation_url(raw_url: str | None = None) -> str:
    """Return the only activation URL agents should show to users."""
    if not raw_url:
        return ACTIVATION_PAGE_URL
    try:
        parsed = urllib.parse.urlparse(raw_url.strip())
    except Exception:
        return ACTIVATION_PAGE_URL
    if parsed.scheme == "https" and parsed.hostname == "schoolfit.hk" and parsed.path.startswith(ACTIVATION_PAGE_PATH):
        return ACTIVATION_PAGE_URL
    return ACTIVATION_PAGE_URL


def activation_url_policy() -> dict[str, Any]:
    return {
        "canonicalUrl": ACTIVATION_PAGE_URL,
        "allowed": "https://schoolfit.hk/skill-code only",
        "strip": ["query", "hash", "path suffix", "tracking parameters"],
        "recovery": "如果打開後找不到頁面，請把網址刪到 https://schoolfit.hk/skill-code 後再重新打開。",
    }


def next_trace_id() -> TraceId:
    return f"sf_{int(time.time() * 1000)}_{os.urandom(6).hex()}"


def code_hash_prefix(code: str | None) -> str:
    if not code:
        return ""
    normalized = code.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:SKILL_CODE_HASH_PREFIX_LEN]


def code_display(code: str | None) -> str:
    if not code:
        return ""
    normalized = code.strip()
    if len(normalized) <= 8:
        return normalized
    return f"{normalized[:4]}...{normalized[-4:]}"


def load_saved_skill_code() -> str | None:
    config_path = os.environ.get(SCHOOLFIT_SKILL_CONFIG_PATH_ENV, DEFAULT_SKILL_CONFIG_PATH)
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    code = data.get("code")
    return str(code).strip() if isinstance(code, str) and code.strip() else None


def save_skill_code(code: str) -> None:
    config_path = os.environ.get(SCHOOLFIT_SKILL_CONFIG_PATH_ENV, DEFAULT_SKILL_CONFIG_PATH)
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    payload = {
        "code": code.strip(),
        "updatedAt": int(time.time()),
    }
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)


def mark_skill_code_activated(code: str, activation_status: ActivationMode = "active") -> None:
    config_path = os.environ.get(SCHOOLFIT_SKILL_CONFIG_PATH_ENV, DEFAULT_SKILL_CONFIG_PATH)
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    payload = {
        "code": code.strip(),
        "activationStatus": activation_status,
        "activatedAt": int(time.time()),
    }
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)


def resolve_skill_code(cli_code: str | None = None, *, allow_fallback: bool = True) -> str | None:
    if cli_code and str(cli_code).strip():
        return str(cli_code).strip()

    env_code = os.environ.get(SCHOOLFIT_SKILL_CONFIG_ENV, "").strip()
    if env_code:
        return env_code

    saved_code = load_saved_skill_code()
    if saved_code:
        return saved_code

    legacy_code = os.environ.get(SCHOOLFIT_SKILL_LEGACY_CODE_ENV, "").strip()
    if legacy_code:
        return legacy_code

    if allow_fallback:
        return SCHOOLFIT_SKILL_CLIENT_CODE
    return None


def extract_skill_code_from_text(text: str | None) -> str | None:
    if not text:
        return None
    match = SKILL_CODE_RE.search(text.strip())
    return match.group(0) if match else None


def get_skill_code(args: argparse.Namespace, *, allow_fallback: bool = True) -> str | None:
    explicit = getattr(args, "skill_code", None)
    if explicit and str(explicit).strip() == SCHOOLFIT_SKILL_CLIENT_CODE:
        return SCHOOLFIT_SKILL_CLIENT_CODE
    resolved = resolve_skill_code(explicit, allow_fallback=allow_fallback)
    if resolved:
        return resolved
    return None


def activation_required_output(command: str, trace_id: TraceId, code: str | None = None, reason: str = "missing_code") -> dict[str, Any]:
    return {
        "needsActivation": True,
        "activationStatus": "inactive",
        "activationReason": reason,
        "activationUrl": canonical_activation_url(),
        "activationUrlPolicy": activation_url_policy(),
        "message": SKILL_REQUIRES_CODE_MESSAGE,
        "interactionStyle": INTERACTION_STYLE,
        "chatInstruction": "請把取得的授權碼原文貼回這個聊天窗口，例如：我的 SchoolFit 授權碼是 sfhk_xxxxx。收到後我會直接幫你查，不需要你操作命令行。",
        "agentInstruction": "收到用戶授權碼後，後續工具調用請使用 --skill-code 或 SCHOOLFIT_SKILL_CODE 傳入該碼；不要要求用戶操作命令行。",
        "quickStart": {
            "step1": "打開 https://schoolfit.hk/skill-code。若網址後面有 ?、# 或其他字串，請先刪到 /skill-code 為止。",
            "step2": "點擊生成授權碼。",
            "step3": "把授權碼原文貼回同一個 Agent 聊天窗口。",
            "step4": "之後直接問：幫我找沙田 Band 1 英文男女校，或查小學、幼稚園、國際學校、專上教育選項。",
        },
        "example": "我的 SchoolFit 授權碼是 sfhk_xxxxxxxxxxxxxxxx",
        "skillVersion": SKILL_VERSION,
        "traceId": trace_id,
        "schoolfitUrl": DEFAULT_BASE_URL,
        "code": {
            "display": code_display(code),
            "hashPrefix": code_hash_prefix(code),
        },
        "sourceLedger": build_source_ledger(),
    }


def activation_result_output(code: str | None, activation_status: ActivationMode, trace_id: TraceId) -> dict[str, Any]:
    active = activation_status in {"active", "reserved"}
    return {
        "activationStatus": activation_status,
        "activated": active,
        "message": (
            "授權碼已可用。之後在這個聊天窗口可直接查學校、比較、做推薦和申請計劃。"
            if active else SKILL_REQUIRES_CODE_MESSAGE
        ),
        "chatMemoryInstruction": (
            "Agent 應在本次對話上下文中記住此授權碼，後續 SchoolFit 工具調用用 --skill-code 傳入；不要寫入磁碟、README、日誌或 commit。"
        ),
        "code": {
            "display": code_display(code),
            "hashPrefix": code_hash_prefix(code),
        },
        "activationUrl": canonical_activation_url(),
        "activationUrlPolicy": activation_url_policy(),
        "skillVersion": SKILL_VERSION,
        "traceId": trace_id,
        "sourceLedger": build_source_ledger(),
    }


def attach_runtime_metadata(output: dict[str, Any], *, activation_status: ActivationMode, trace_id: TraceId, code: str | None) -> dict[str, Any]:
    output["activationStatus"] = activation_status
    output["skillVersion"] = SKILL_VERSION
    output["traceId"] = trace_id
    output["schoolfitUrl"] = output.get("schoolfitUrl") or DEFAULT_BASE_URL
    output["skillCodeHashPrefix"] = code_hash_prefix(code)
    return output


def activate_skill_code(base_url: str, code: str | None, trace_id: TraceId) -> ActivationMode:
    if not code:
        return "inactive"
    if code == SCHOOLFIT_SKILL_CLIENT_CODE:
        return "reserved"
    try:
        result = request_json(
            "POST",
            base_url,
            f"/api/skill/codes/{urllib.parse.quote(code, safe='')}/activate",
            body={"skillVersion": SKILL_VERSION, "traceId": trace_id, "agentHint": "openclaw"},
            skill_code=code,
            trace_id=trace_id,
            activation_status="activating",
        )
    except SchoolFitError:
        return "inactive"
    status = str((result or {}).get("activationStatus") or (result or {}).get("status") or "").lower()
    return "active" if status == "active" else "inactive"


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


def normalize_csv_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def infer_intent(args: argparse.Namespace) -> str:
    explicit = (getattr(args, "intent", "auto") or "auto").strip().lower()
    if explicit and explicit != "auto":
        return explicit

    raw_q = getattr(args, "q", "") or ""
    q = raw_q.lower()
    if any(keyword in q for keyword in ("比較", "對比", "比對", "vs", "v.s", "對拋")):
        return "compare"
    if is_vacancy_query(raw_q, q):
        return "vacancy"
    if any(keyword in q for keyword in ("招生", "通告", "截止", "申請表", "申请表", "deadline", "報名", "报名")):
        return "admissions"
    if any(keyword in q for keyword in ("申請計劃", "準備", "面試", "文件", "timeline", "時間表")):
        return "plan"
    if any(keyword in q for keyword in ("口碑", "評價", "評論", "review")):
        return "report"
    if any(keyword in q for keyword in ("推薦", "建議", "幫我揀", "幫我挑", "幫我搵", "揀校", "適合", "適合邊")):
        return "recommend"
    if any(keyword in q for keyword in ("詳情", "介紹", "個學校", "呢間", "呢校", "個校", "這間")):
        return "detail"
    return "search"


def extract_school_ids_from_search(payload: dict[str, Any], limit: int = MAX_COMPARE_IDS) -> list[str]:
    schools = payload.get("schools", []) if isinstance(payload, dict) else []
    ids: list[str] = []
    for school in schools[:limit]:
        slug = school.get("slug")
        if slug:
            ids.append(str(slug))
    return ids


def build_source_ledger() -> dict[str, Any]:
    return {
        "officialFacts": [{
            "name": "SchoolFit HK API",
            "scope": "School profile fields across secondary, primary, kindergarten, international and postsecondary SchoolFit public endpoints",
            "source": "https://schoolfit.hk/api/",
        }],
        "coverage": {
            "levels": [
                {"level": level, "label": SCHOOL_LEVEL_LABELS[level], "count": SCHOOL_LEVEL_COUNTS[level]}
                for level in SCHOOL_LEVELS
            ],
            "total": sum(SCHOOL_LEVEL_COUNTS.values()),
        },
        "schoolOfficial": [],
        "thirdPartyBand": "third-party band reference; not official",
        "communitySignal": [],
        "vacancyAndAdmissions": {
            "status": "included when /api/vacancies or /api/admission-notices are called",
            "confidenceRequired": True,
            "confirm": "Please confirm with school before final decision",
        },
        "assumptions": [
            "No local Edu DB is read.",
            "No PII or private profile data is persisted.",
        ],
    }


def add_school_level_sources(source_ledger: dict[str, Any], school: dict[str, Any]) -> None:
    if school.get("sourceName"):
        source_ledger["officialFacts"].append({
            "name": school.get("sourceName"),
            "source": school.get("sourceUrl") or school.get("sourceName"),
        })
    if school.get("officialUrl"):
        source_ledger["schoolOfficial"].append({
            "name": school.get("nameZh") or school.get("nameEn"),
            "officialUrl": school.get("officialUrl"),
        })
    for signal in school.get("externalSignals", []) or []:
        if signal.get("provider"):
            source_ledger["communitySignal"].append({
                "provider": signal.get("provider"),
                "signalType": signal.get("signalType"),
                "isOfficial": signal.get("isOfficial"),
            })
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
    skill_code: str | None = None,
    trace_id: TraceId | None = None,
    activation_status: ActivationMode = "reserved",
    skill_version: str | None = None,
) -> Any:
    url = make_url(base_url, path, params)
    data = None
    code = skill_code or SCHOOLFIT_SKILL_CLIENT_CODE
    headers = {
        "Accept": "application/json",
        "User-Agent": f"schoolfit-openclaw-skill/{SKILL_VERSION}",
        SKILL_CODE_HEADER: code,
        SKILL_VERSION_HEADER: skill_version or SKILL_VERSION_HEADER_VERSION,
        SKILL_ACTIVATION_STATUS_HEADER: activation_status,
    }
    if trace_id:
        headers[SKILL_TRACE_HEADER] = trace_id
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


def telemetry_payload(
    command: str,
    endpoint: str,
    skill_code: str,
    trace_id: str,
    latency_ms: int,
    status_code: int,
    *,
    activation_status: ActivationMode = "reserved",
    error_code: str | None = None,
) -> dict[str, Any]:
    return {
        "eventName": SKILL_USAGE_EVENT,
        "command": command,
        "endpoint": endpoint,
        "statusCode": status_code,
        "errorCode": error_code,
        "traceId": trace_id,
        "skillCodeHashPrefix": code_hash_prefix(skill_code),
        "payload": {
            "skill_version": SKILL_VERSION,
            "command": command,
            "status": "success" if error_code is None else "failed",
            "trace_id": trace_id,
            "schoolfit_code_hash_prefix": code_hash_prefix(skill_code),
            "activation_status": activation_status,
            "latency_ms": latency_ms,
            "error_code": error_code,
        },
    }


def record_telemetry(
    base_url: str,
    *,
    command: str,
    status: str,
    trace_id: TraceId,
    skill_code: str | None,
    activation_status: ActivationMode,
    latency_ms: int | None = None,
    error_code: str | None = None,
) -> None:
    if not skill_code or skill_code == SCHOOLFIT_SKILL_CLIENT_CODE:
        return

    def send() -> None:
        try:
            status_code = 200 if status == "success" else 500
            payload = telemetry_payload(
                command,
                command,
                skill_code,
                trace_id,
                latency_ms or 0,
                status_code,
                activation_status=activation_status,
                error_code=error_code,
            )
            request_json(
                "POST",
                base_url,
                SKILL_TELEMETRY_ENDPOINT,
                body={"events": [payload]},
                skill_code=skill_code,
                trace_id=trace_id,
                activation_status=activation_status,
            )
        except Exception:
            return

    threading.Thread(target=send, daemon=True).start()


def post_telemetry(base_url: str, telemetry_context: dict[str, Any], skill_code: str) -> None:
    status_code = int(telemetry_context.get("statusCode", 200))
    command = telemetry_context.get("command") or telemetry_context.get("endpoint") or "unknown"
    trace_id = telemetry_context.get("traceId") or ""
    endpoint = telemetry_context.get("endpoint", "") or ""
    latency_ms = telemetry_context.get("latencyMs") or telemetry_context.get("latency_ms") or 0

    payload = {
        "events": [
            telemetry_payload(
                command,
                endpoint,
                skill_code,
                str(trace_id),
                int(latency_ms) if isinstance(latency_ms, (int, float, str)) and str(latency_ms).strip().isdigit() else 0,
                status_code=status_code,
                activation_status="active",
            )
        ]
    }

    try:
        request_json(
            "POST",
            base_url,
            SKILL_TELEMETRY_ENDPOINT,
            body=payload,
            skill_code=skill_code,
            trace_id=trace_id,
            activation_status="active",
        )
    except Exception:
        return


def safe_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8")[:500]
        payload = json.loads(raw)
        detail = payload.get("error") or payload.get("message") or raw
    except Exception:
        detail = exc.reason
    recovery = {
        401: "請重新到 https://schoolfit.hk/skill-code 取得授權碼；如網址後面有 ?、# 或其他字串，先刪到 /skill-code。",
        403: "授權碼可能未啟用或已被停用，請重新取碼或稍後再試。",
        404: "找不到指定學校或端點；如是學校名稱，請先用 resolve-school 或 search-schools 查 slug。",
        429: "請求太頻密；稍等一分鐘後重試，或縮小查詢範圍。",
        500: "SchoolFit 服務暫時出錯；可稍後重試。",
        502: "SchoolFit 服務暫時不可用；可稍後重試。",
        503: "SchoolFit 服務暫時不可用；可稍後重試。",
        504: "SchoolFit API 回應逾時；可降低 page-size 後重試。",
    }.get(exc.code, "請保留查詢條件，稍後重試。")
    return f"SchoolFit API returned HTTP {exc.code}: {detail}. Recovery: {recovery}"


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


def command_text_fields(args: argparse.Namespace) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key in (
        "q",
        "notes",
        "personality",
        "application_goal",
        "language_priority",
        "student_profile_json",
        "input_json",
        "text",
    ):
        value = getattr(args, key, None)
        if isinstance(value, str) and value.strip():
            fields[key] = value.strip()
    for key in ("priorities", "support_needs"):
        value = getattr(args, key, None)
        if isinstance(value, list) and value:
            fields[key] = " ".join(str(item) for item in value)
    return fields


def detect_sensitive_input(args: argparse.Namespace) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for field, text in command_text_fields(args).items():
        cleaned = SKILL_CODE_RE.sub("", text)
        checks = [
            ("hkid", HKID_RE),
            ("phone", HK_PHONE_RE),
            ("email", EMAIL_RE),
        ]
        for label, pattern in checks:
            if pattern.search(cleaned):
                findings.append({"field": field, "type": label})
    return findings


def privacy_warning_output(command: str, trace_id: TraceId, findings: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "privacyWarning": True,
        "blocked": True,
        "command": command,
        "message": PII_WARNING_MESSAGE,
        "interactionStyle": INTERACTION_STYLE,
        "friendlyMessage": INTERACTION_STYLE["privacyReassurance"],
        "detected": findings,
        "allowedAlternatives": [
            "可提供學校階段、Band 參考或課程方向、地區、性別偏好、授課語言、通勤時間和學費上限。",
            "可描述學習需要，例如 SEN、非華語支援、英文環境偏好，但不要提供可識別身份資料。",
            "如要處理文件，請先移除姓名、HKID、電話、住址和學校內部編號。",
        ],
        "skillVersion": SKILL_VERSION,
        "traceId": trace_id,
        "sourceLedger": build_source_ledger(),
    }


DISTRICT_ALIASES = {
    "沙田": "沙田區",
    "沙田區": "沙田區",
    "沙田区": "沙田區",
    "sha tin": "沙田區",
    "shatin": "沙田區",
    "馬鞍山": "沙田區",
    "马鞍山": "沙田區",
    "ma on shan": "沙田區",
    "九龍城": "九龍城區",
    "九龍城區": "九龍城區",
    "九龙城": "九龍城區",
    "九龙城区": "九龍城區",
    "kowloon city": "九龍城區",
    "油尖旺": "油尖旺區",
    "yau tsim mong": "油尖旺區",
    "深水埗": "深水埗區",
    "深水埗区": "深水埗區",
    "sham shui po": "深水埗區",
    "黃大仙": "黃大仙區",
    "黄大仙": "黃大仙區",
    "wong tai sin": "黃大仙區",
    "觀塘": "觀塘區",
    "观塘": "觀塘區",
    "kwun tong": "觀塘區",
    "大埔": "大埔區",
    "tai po": "大埔區",
    "屯門": "屯門區",
    "屯门": "屯門區",
    "tuen mun": "屯門區",
    "元朗": "元朗區",
    "yuen long": "元朗區",
    "荃灣": "荃灣區",
    "荃湾": "荃灣區",
    "tsuen wan": "荃灣區",
    "葵青": "葵青區",
    "kwai tsing": "葵青區",
    "西貢": "西貢區",
    "西贡": "西貢區",
    "sai kung": "西貢區",
    "將軍澳": "西貢區",
    "将军澳": "西貢區",
    "tseung kwan o": "西貢區",
    "中西區": "中西區",
    "中西区": "中西區",
    "central and western": "中西區",
    "灣仔": "灣仔區",
    "湾仔": "灣仔區",
    "wan chai": "灣仔區",
    "東區": "東區",
    "东区": "東區",
    "eastern": "東區",
    "南區": "南區",
    "南区": "南區",
    "southern": "南區",
    "北區": "北區",
    "北区": "北區",
    "north": "北區",
    "離島": "離島區",
    "离岛": "離島區",
    "islands": "離島區",
}

REGION_ALIASES = {
    "港島": "港島",
    "香港島": "港島",
    "hong kong island": "港島",
    "九龍": "九龍",
    "九龙": "九龍",
    "kowloon": "九龍",
    "新界": "新界",
    "new territories": "新界",
}

GRADE_ALIASES = {
    "中一": "S1",
    "初一": "S1",
    "form 1": "S1",
    "中二": "S2",
    "初二": "S2",
    "form 2": "S2",
    "中三": "S3",
    "初三": "S3",
    "form 3": "S3",
    "中四": "S4",
    "高一": "S4",
    "form 4": "S4",
    "中五": "S5",
    "高二": "S5",
    "form 5": "S5",
    "中六": "S6",
    "高三": "S6",
    "form 6": "S6",
}

SCHOOL_LEVEL_ALIASES = {
    "secondary": "secondary",
    "中學": "secondary",
    "中学": "secondary",
    "升中": "secondary",
    "中一": "secondary",
    "中二": "secondary",
    "中三": "secondary",
    "中四": "secondary",
    "中五": "secondary",
    "中六": "secondary",
    "secondary": "secondary",
    "secondary school": "secondary",
    "form 1": "secondary",
    "form 2": "secondary",
    "form 3": "secondary",
    "form 4": "secondary",
    "form 5": "secondary",
    "form 6": "secondary",
    "primary": "primary",
    "小學": "primary",
    "小学": "primary",
    "升小": "primary",
    "小一": "primary",
    "小二": "primary",
    "小三": "primary",
    "小四": "primary",
    "小五": "primary",
    "小六": "primary",
    "primary school": "primary",
    "p1": "primary",
    "p2": "primary",
    "p3": "primary",
    "p4": "primary",
    "p5": "primary",
    "p6": "primary",
    "kindergarten": "kindergarten",
    "幼稚園": "kindergarten",
    "幼稚园": "kindergarten",
    "幼兒園": "kindergarten",
    "幼儿园": "kindergarten",
    "k1": "kindergarten",
    "k2": "kindergarten",
    "k3": "kindergarten",
    "pn": "kindergarten",
    "n班": "kindergarten",
    "n 班": "kindergarten",
    "pre-nursery": "kindergarten",
    "pre nursery": "kindergarten",
    "nursery": "kindergarten",
    "international": "international",
    "國際學校": "international",
    "国际学校": "international",
    "國際校": "international",
    "国际校": "international",
    "ib": "international",
    "a-level": "international",
    "a level": "international",
    "postsecondary": "postsecondary",
    "專上": "postsecondary",
    "专上": "postsecondary",
    "大專": "postsecondary",
    "大专": "postsecondary",
    "jupas": "postsecondary",
    "e-app": "postsecondary",
    "eapp": "postsecondary",
    "副學士": "postsecondary",
    "副学士": "postsecondary",
    "高級文憑": "postsecondary",
    "高级文凭": "postsecondary",
    "higher diploma": "postsecondary",
    "associate degree": "postsecondary",
    "top-up degree": "postsecondary",
    "top up degree": "postsecondary",
}

SCHOOL_NAME_ALIASES = {
    "spcc": "St. Paul's Co-educational College",
    "spc": "St. Paul's College",
    "spcs": "St. Paul's Convent School",
    "spcssection": "St. Paul's Convent School",
    "dgs": "Diocesan Girls' School",
    "dbs": "Diocesan Boys' School",
    "ywgs": "Ying Wa Girls' School",
    "ywc": "Ying Wa College",
    "qc": "Queen's College",
    "bps": "Belilios Public School",
    "mcs": "Maryknoll Convent School",
    "smcc": "St. Mary's Canossian College",
    "hy": "Heep Yunn School",
    "hys": "Heep Yunn School",
    "hyschool": "Heep Yunn School",
    "ghs": "Good Hope School",
    "gh": "Good Hope School",
    "lgc": "La Salle College",
    "lsc": "La Salle College",
    "kc": "King's College",
    "wyhk": "Wah Yan College Hong Kong",
    "wyk": "Wah Yan College Kowloon",
    "sjc": "St. Joseph's College",
    "sjc hk": "St. Joseph's College",
    "sfxc": "St. Francis Xavier's College",
    "sfx": "St. Francis Xavier's College",
    "stmark": "St. Mark's School",
    "stmarks": "St. Mark's School",
    "ststephen": "St. Stephen's College",
    "ssc": "St. Stephen's College",
    "ststephengirls": "St. Stephen's Girls' College",
    "ssgc": "St. Stephen's Girls' College",
    "bhs": "Baptist Lui Ming Choi Secondary School",
    "blmcss": "Baptist Lui Ming Choi Secondary School",
    "lmc": "Baptist Lui Ming Choi Secondary School",
    "skhtst": "SKH Tsang Shiu Tim Secondary School",
    "tstss": "SKH Tsang Shiu Tim Secondary School",
    "ktss": "Kwok Tak Seng Catholic Secondary School",
    "kts": "Kwok Tak Seng Catholic Secondary School",
    "stmc": "Sha Tin Methodist College",
    "stm": "Sha Tin Methodist College",
    "stgss": "Sha Tin Government Secondary School",
    "spcsc": "St. Paul's College",
    "ccsc": "Cheung Chuk Shan College",
    "ccscs": "Cheung Chuk Shan College",
    "twgss": "True Light Girls' College",
    "tlgc": "True Light Girls' College",
    "ktls": "Kowloon True Light School",
    "hfcc": "Holy Family Canossian College",
    "mss": "Munsang College",
    "msc": "Munsang College",
    "qes": "Queen Elizabeth School",
    "qesosa": "Queen Elizabeth School Old Students' Association Secondary School",
    "csk": "Chan Sui Ki (La Salle) College",
    "csklsc": "Chan Sui Ki (La Salle) College",
    "plkno1": "Po Leung Kuk No.1 W.H. Cheung College",
    "plkwhc": "Po Leung Kuk No.1 W.H. Cheung College",
    "npl": "Ning Po College",
    "plkcfs": "Po Leung Kuk Choi Kai Yau School",
}

NEARBY_DISTRICTS = {
    "沙田區": {"大埔區", "西貢區", "九龍城區", "黃大仙區", "葵青區"},
    "大埔區": {"沙田區", "北區", "元朗區"},
    "西貢區": {"觀塘區", "黃大仙區", "沙田區"},
    "九龍城區": {"油尖旺區", "黃大仙區", "觀塘區", "深水埗區", "沙田區"},
    "油尖旺區": {"九龍城區", "深水埗區", "灣仔區", "中西區"},
    "深水埗區": {"油尖旺區", "九龍城區", "葵青區", "荃灣區"},
    "黃大仙區": {"九龍城區", "觀塘區", "西貢區", "沙田區"},
    "觀塘區": {"黃大仙區", "西貢區", "九龍城區", "東區"},
    "葵青區": {"荃灣區", "深水埗區", "沙田區"},
    "荃灣區": {"葵青區", "屯門區", "元朗區", "深水埗區"},
    "屯門區": {"元朗區", "荃灣區"},
    "元朗區": {"屯門區", "北區", "大埔區", "荃灣區"},
    "北區": {"大埔區", "元朗區"},
    "中西區": {"灣仔區", "南區", "油尖旺區"},
    "灣仔區": {"中西區", "東區", "油尖旺區"},
    "東區": {"灣仔區", "南區", "觀塘區"},
    "南區": {"中西區", "灣仔區", "東區"},
    "離島區": {"中西區", "荃灣區"},
}


def contains_any_text(raw: str, lowered: str, words: tuple[str, ...]) -> bool:
    for word in words:
        if not word:
            continue
        if word.isascii():
            if word.lower() in lowered:
                return True
        elif word in raw or word.lower() in lowered:
            return True
    return False


def normalized_ascii_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def mentions_known_secondary_school(raw: str, lowered: str) -> bool:
    compact = normalized_ascii_text(raw)
    for alias, school_name in SCHOOL_NAME_ALIASES.items():
        if alias.isascii() and re.search(rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])", lowered):
            return True
        if school_name and school_name.lower() in lowered:
            return True
        if school_name and normalized_ascii_text(school_name) in compact:
            return True
    return False


def is_allocation_context(raw: str, lowered: str) -> bool:
    return contains_any_text(raw, lowered, (
        "自行分配學位", "自行分配学位", "學位分配辦法", "学位分配办法",
        "統一派位", "统一派位", "中一派位", "小一入學", "小一入学",
        "派位", "甲部", "乙部", "校網", "校网", "聯繫中學位", "联系中学位",
        "直屬中學位", "直属中学位", "allocation system",
        "central allocation", "discretionary places", "兄姊分", "兄姐分",
    ))


def is_vacancy_query(raw: str, lowered: str) -> bool:
    if infer_school_level_from_common_question(raw, lowered) == "postsecondary":
        return False
    if contains_any_text(raw, lowered, (
        "學額", "学额", "插班", "插班位", "空位", "餘額", "余额",
        "有冇位", "有位", "有无位", "vacancy", "vacancies", "available places",
        "places available", "seats available", "有無位", "有无位", "冇位", "無位", "无位",
    )):
        return True
    if contains_any_text(raw, lowered, ("學位", "学位", "places", "seats")) and not is_allocation_context(raw, lowered):
        return True
    return False


def infer_school_level_from_common_question(raw: str, lowered: str) -> str | None:
    if contains_any_text(raw, lowered, ("k3 primary school", "kindergarten to dss primary", "幼稚園校長推薦信升小", "幼稚园校长推荐信升小")):
        return "kindergarten"
    if contains_any_text(raw, lowered, ("woodland pre-schools international kindergarten", "woodland pre-schools",)):
        return "international"
    if contains_any_text(raw, lowered, ("primary section", "primary division", "junior school", "preparatory school", "primary school", "附屬小學", "附属小学")):
        return "primary"
    if mentions_known_secondary_school(raw, lowered):
        return "secondary"
    if "primary school" in lowered and "international school" not in lowered:
        return "primary"
    if ("小學" in raw or "小学" in raw) and "ib pyp" in lowered and "國際學校" not in raw and "国际学校" not in raw:
        return "primary"
    if contains_any_text(raw, lowered, ("本地小學轉國際學校前", "本地小学转国际学校前")):
        return "primary"
    if "international kindergarten to international primary" in lowered:
        return "international"
    if contains_any_text(raw, lowered, ("k1", "k2", "k3", "幼稚園", "幼稚园", "幼兒園", "幼儿园", "international kindergarten")):
        return "kindergarten"
    if contains_any_text(raw, lowered, (
        "直屬中學", "直属中学", "聯繫中學", "联系中学", "中學位", "中学位",
        "自行分配兩個", "自行分配两个", "兩個 choice", "两个 choice", "choice 次序",
        "banding reference", "自行分配面試", "自行分配面试", "中學學位分配", "中学学位分配",
        "自行分配學位面試", "自行分配学位面试",
        "小六呈分後升中", "小六呈分后升中", "小六操行", "呈分後升中", "呈分后升中",
        "heep yunn", "想轉直資中學", "想转直资中学", "嘉諾撒聖瑪利書院", "嘉诺撒圣玛利书院",
        "st francis xavier college", "中六轉校", "中六转校", "f1 admission",
        "學校 banding", "学校 banding", "banding 係咪官方", "banding 系咪官方",
        "自行面試", "自行面试", "女校今年仲收唔收插班",
        "升中統一派位", "升中统一派位",
    )):
        return "secondary"
    if contains_any_text(raw, lowered, ("小一", "p1", "小二", "p2", "小三", "p3", "小四", "p4", "小五", "p5", "小六", "p6")):
        return "primary"
    if contains_any_text(raw, lowered, ("pn", "n1", "n班", "n 班", "pre-nursery", "pre nursery", "細b", "细b", "註冊證", "注册证")):
        return "kindergarten"
    if contains_any_text(raw, lowered, (
        "hku space", "hpshcc", "hkcc", "polyu hkcc", "cuscs", "continuing and professional studies",
        "vtc youth college", "hku space community college", "international culinary institute",
        "caritas institute of higher education", "ouhk lipace", "lipace", "stanley ho community college",
    )):
        return "postsecondary"
    if contains_any_text(raw, lowered, (
        "國際學校", "国际学校", "international school", "year 1", "year1", "year 6", "year6",
        "year 7", "year7", "year 8", "year8", "year 9", "year9", "year 10", "year10",
        "grade 10", "grade10", "igcse", "ib school", "ib pyp", "ib myp", "ib dp",
        "ap school", "canadian curriculum", "esf", "harrow", "kellett", "chinese international school",
        "isf academy", "victoria shanghai academy", "vsa", "german swiss international school",
        "french international school", "debenture", "capital levy", "corporate nomination",
        "nomination right", "boarding fees", "國際學校 waiting list", "国际学校 waiting list",
        "gsis", "german stream", "hkis", "american curriculum", "malvern college hong kong",
        "malvern college pre-school", "nord anglia", "international primary", "international kindergarten",
        "discovery college", "dbis", "american school hong kong", "shrewsbury", "wycombe abbey",
        "mount kelly", "invictus school", "delia school of canada", "woodland pre-schools",
        "外籍 passport", "foreign passport",
    )):
        return "international"
    if contains_any_text(raw, lowered, (
        "top-up degree", "top up degree", "bachelor", "degree", "dse", "ugc", "學士", "学士",
        "自資學士", "自资学士", "聯招", "联招", "大學銜接", "大学衔接", "university",
        "hk university", "sub-degree", "副學位", "副学位", "nmtss", "sssdp", "higher diploma",
        "associate degree", "e-app", "eapp", "jupas", "top up", "scope top up", "hsuhk",
        "undergraduate admission", "cityu", "chu hai college", "savannah college", "elder academy",
        "海外學歷申請香港大學", "海外学历申请香港大学",
    )):
        return "postsecondary"
    if re.search(r"\bHD\b", raw):
        return "postsecondary"
    if re.search(r"\bS[1-6]\b", raw, re.IGNORECASE):
        return "secondary"
    if contains_any_text(raw, lowered, ("小學", "小学", "私小", "津小", "primary school", "小一入學", "小一入学", "小一自行", "小一統一", "小一统一", "小學校網", "小学校网")):
        return "primary"
    if re.search(r"band\s*[123]", lowered) or contains_any_text(raw, lowered, ("中一", "中一派位")):
        return "secondary"
    if re.search(r"\b\d{2}\s*校網\b", raw) or re.search(r"\b\d{2}\s*校网\b", raw):
        return "primary"
    if contains_any_text(raw, lowered, ("統一派位", "统一派位", "甲一", "乙一", "central allocation")):
        return "primary"
    if contains_any_text(raw, lowered, ("自行分配 sibling", "兄姊分", "兄姐分", "sibling 兄姊")):
        return "primary"
    if re.search(r"band\s*[123]", lowered) or contains_any_text(raw, lowered, ("升中", "中一", "中一派位", "呈分", "自行兩間", "自行两间")):
        return "secondary"
    return None


def detect_response_language(raw: str, lowered: str) -> str:
    if contains_any_text(raw, lowered, ("用英文", "英文回答", "answer in english", "respond in english", "english answer")):
        return "en"
    if contains_any_text(raw, lowered, ("用简体", "简体回答", "簡體回答", "simplified chinese", "zh-hans")):
        return "zh-Hans"
    if contains_any_text(raw, lowered, ("用繁體", "繁體回答", "繁体回答", "traditional chinese", "zh-hant")):
        return "zh-Hant"
    simplified_markers = ("学校", "学额", "学位", "申请", "报名", "推荐", "建议", "适合", "稳阵", "直资", "环境")
    if any(marker in raw for marker in simplified_markers):
        return "zh-Hans"
    if raw and all(ord(char) < 128 for char in raw):
        return "en"
    return "zh-Hant"


def parse_parent_request_text(text: str | None) -> dict[str, Any]:
    raw = (text or "").strip()
    lowered = raw.lower()
    response_language = detect_response_language(raw, lowered)
    parsed: dict[str, Any] = {
        "rawText": raw,
        "responseLanguage": response_language,
        "filters": {},
        "recommendationSignals": {},
        "intentHints": [],
        "privacy": {
            "containsPossibleSensitiveData": bool(HKID_RE.search(raw) or HK_PHONE_RE.search(raw) or EMAIL_RE.search(raw)),
        },
        "confidence": "medium" if raw else "low",
        "conversationHints": [],
    }
    filters = parsed["filters"]
    signals = parsed["recommendationSignals"]
    signals["responseLanguage"] = response_language

    for alias, level in SCHOOL_LEVEL_ALIASES.items():
        if (alias.isascii() and alias in lowered) or (not alias.isascii() and (alias in raw or alias.lower() in lowered)):
            filters["level"] = level
            signals["level"] = level
            signals["levelLabel"] = SCHOOL_LEVEL_LABELS.get(level)
            break

    inferred_level = infer_school_level_from_common_question(raw, lowered)
    if inferred_level:
        filters["level"] = inferred_level
        signals["level"] = inferred_level
        signals["levelLabel"] = SCHOOL_LEVEL_LABELS.get(inferred_level)

    for alias, district in DISTRICT_ALIASES.items():
        if (alias.isascii() and alias in lowered) or (not alias.isascii() and alias in raw):
            filters["district"] = district
            signals["district"] = district
            break
    for alias, region in REGION_ALIASES.items():
        if (alias.isascii() and alias in lowered) or (not alias.isascii() and alias in raw):
            filters["region"] = region
            signals["region"] = region
            break

    band_match = re.search(r"band\s*([123])\s*([abc])?", lowered, re.IGNORECASE)
    if band_match:
        band = f"Band {band_match.group(1)}"
        if band_match.group(2):
            band += band_match.group(2).upper()
        filters["banding"] = band
        signals["banding"] = band

    if contains_any_text(raw, lowered, ("男女校", "男女", "co-ed", "coed", "co-educational", "mixed school", "mixed gender")):
        filters["gender"] = "男女校"
        signals["gender"] = "男女校"
    elif contains_any_text(raw, lowered, ("女校", "girls", "girl school", "girls school", "girls' school")):
        filters["gender"] = "女校"
        signals["gender"] = "女校"
    elif contains_any_text(raw, lowered, ("男校", "boys", "boy school", "boys school", "boys' school")):
        filters["gender"] = "男校"
        signals["gender"] = "男校"

    if contains_any_text(raw, lowered, ("英文中學", "英文中学", "英中", "英文", "english medium", "english-medium", "emi", "english environment")):
        filters["medium"] = "英文"
        signals["medium"] = "英文"
        signals["languagePriority"] = "英文環境"
    elif contains_any_text(raw, lowered, ("中文中學", "中文中学", "中中", "中文", "chinese medium", "chinese-medium", "cmi")):
        filters["medium"] = "中文"
        signals["medium"] = "中文"

    if contains_any_text(raw, lowered, ("直資", "直资", "dss", "direct subsidy")):
        rejects_dss = contains_any_text(raw, lowered, (
            "不要直資", "唔要直資", "不接受直資", "不考慮直資",
            "不要直资", "不接受直资", "不考虑直资",
            "no dss", "not dss", "without dss", "reject dss", "no direct subsidy", "not direct subsidy",
        ))
        signals["acceptsDss"] = not rejects_dss
        if not rejects_dss:
            filters["fundingType"] = "直資"
    if contains_any_text(raw, lowered, ("官立", "官校", "government school", "government")):
        filters["fundingType"] = "官立"
    if contains_any_text(raw, lowered, ("資助", "资助", "aided")):
        filters["fundingType"] = "資助"

    for label, grade in GRADE_ALIASES.items():
        if (label.isascii() and label in lowered) or (not label.isascii() and label in raw):
            filters["vacancyGrade"] = grade
            signals["grade"] = grade
            break
    grade_match = re.search(r"\bS([1-6])\b", raw, re.IGNORECASE)
    if grade_match:
        filters["vacancyGrade"] = f"S{grade_match.group(1)}"
        signals["grade"] = f"S{grade_match.group(1)}"

    if is_vacancy_query(raw, lowered):
        parsed["intentHints"].append("vacancy")
        filters["hasVacancy"] = True
    if contains_any_text(raw, lowered, ("招生", "通告", "截止", "申請", "申请", "報名", "报名", "deadline", "deadlines", "admission", "admissions", "application", "apply")):
        parsed["intentHints"].append("admissions")
    if contains_any_text(raw, lowered, ("比較", "对比", "對比", "vs", "compare", "comparison", "versus")):
        parsed["intentHints"].append("compare")
    if contains_any_text(raw, lowered, ("推薦", "推荐", "建議", "建议", "幫我揀", "帮我选", "適合", "适合", "recommend", "recommendation", "suggest", "shortlist", "suitable")):
        parsed["intentHints"].append("recommend")

    if contains_any_text(raw, lowered, ("穩陣", "稳阵", "保守", "安全", "safe", "conservative", "low risk")):
        signals["riskPreference"] = "conservative"
    elif contains_any_text(raw, lowered, ("衝", "冲", "進取", "进取", "reach", "ambitious")):
        signals["riskPreference"] = "ambitious"
    elif contains_any_text(raw, lowered, ("平衡", "match", "balanced")):
        signals["riskPreference"] = "balanced"

    if contains_any_text(raw, lowered, ("只看", "只要", "改成", "換成", "换成", "上次", "剛才", "刚才", "同樣", "一样", "last time", "same as before", "change to", "only")):
        parsed["conversationHints"].append("continue_previous_filters")
    if contains_any_text(raw, lowered, ("唔想太谷", "不要太谷", "不想太卷", "校風好", "校风好", "關愛", "关爱", "pastoral", "caring", "not too stressful")):
        signals.setdefault("priorities", [])
        signals["priorities"].append("校風")
        signals["personality"] = "偏好校風穩定、壓力不要過高"
    if contains_any_text(raw, lowered, ("近地鐵", "近地铁", "交通方便", "車程", "车程", "通勤", "commute", "transport", "near mtr")):
        signals.setdefault("priorities", [])
        signals["priorities"].append("通勤")
    if contains_any_text(raw, lowered, ("活動多", "多活動", "活动多", "多活动", "音樂", "音乐", "運動", "运动", "stem", "STEAM", "steam", "sports", "music", "activities")):
        signals.setdefault("priorities", [])
        signals["priorities"].append("課外活動")

    tuition_match = re.search(r"(\d+(?:\.\d+)?)\s*(萬|万)", raw)
    if tuition_match:
        filters["maxTuition"] = int(float(tuition_match.group(1)) * 10000)
        signals["maxTuition"] = filters["maxTuition"]
    else:
        tuition_match = re.search(r"學費[^\d]{0,4}(\d{4,6})", raw)
        if tuition_match:
            filters["maxTuition"] = int(tuition_match.group(1))
            signals["maxTuition"] = filters["maxTuition"]
        else:
            tuition_match = re.search(r"(?:tuition|fee|budget|under|below|max)[^\d]{0,12}(\d{4,6})", lowered)
            if tuition_match:
                filters["maxTuition"] = int(tuition_match.group(1))
                signals["maxTuition"] = filters["maxTuition"]

    priorities = []
    priority_map = {
        "校風": "校風",
        "校风": "校風",
        "英文環境": "英文環境",
        "英文环境": "英文環境",
        "english environment": "英文環境",
        "學額": "學額",
        "学额": "學額",
        "vacancy": "學額",
        "招生": "招生",
        "admission": "招生",
        "交通": "通勤",
        "通勤": "通勤",
        "commute": "通勤",
        "學費": "學費",
        "学费": "學費",
        "tuition": "學費",
        "面試": "面試",
        "面试": "面試",
        "interview": "面試",
        "支援": "支援需要",
        "support": "支援需要",
        "sen": "SEN 支援",
        "非華語": "非華語支援",
        "非华语": "非華語支援",
        "ncs": "非華語支援",
    }
    for keyword, label in priority_map.items():
        if keyword in raw or keyword in lowered:
            priorities.append(label)
    if priorities:
        signals["priorities"] = list(dict.fromkeys((signals.get("priorities") or []) + priorities))
    if contains_any_text(raw, lowered, ("SEN", "sen", "特殊需要", "special needs", "非華語", "非华语", "NCS", "ncs")):
        signals["supportNeeds"] = [item for item in ("SEN" if "sen" in lowered or "特殊需要" in raw else None, "NCS" if "ncs" in lowered or "非華語" in raw or "非华语" in raw else None) if item]

    suggested = {
        "advisor-search": {
            "q": raw,
            **filters,
            **{key: value for key, value in signals.items() if key in {"levelLabel", "languagePriority", "acceptsDss", "priorities", "supportNeeds", "responseLanguage"}},
        }
    }
    if parsed["intentHints"]:
        suggested["advisor-search"]["intent"] = parsed["intentHints"][0]
    parsed["suggestedCommandParams"] = suggested
    parsed["missingInfoQuestions"] = build_missing_info_questions(parsed)
    parsed["friendlySummary"] = build_friendly_condition_summary(parsed)
    parsed["friendlyFollowUp"] = build_friendly_follow_up(parsed)
    parsed["llmBrief"] = standard_llm_brief(
        "parse-parent-request",
        "Explain what conditions were understood from the parent request, then ask only for missing non-sensitive inputs.",
        [
            "不要要求姓名、HKID、電話、住址或成績表原件。",
            "可要求學校階段、Band 參考或課程方向、地區、語言、性別偏好、學費上限和通勤時間。",
        ],
        {
            "filters": filters,
            "recommendationSignals": signals,
            "intentHints": parsed["intentHints"],
            "missingInfoQuestions": parsed["missingInfoQuestions"],
            "conversationHints": parsed["conversationHints"],
        },
    )
    return parsed


def display_value(key: str, value: Any) -> str:
    if key == "level":
        return SCHOOL_LEVEL_LABELS.get(str(value), str(value))
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return str(value)


def build_friendly_condition_summary(parsed: dict[str, Any]) -> list[str]:
    filters = parsed.get("filters") or {}
    summary: list[str] = []
    ordered_keys = ["level", "region", "district", "banding", "gender", "medium", "fundingType", "maxTuition", "vacancyGrade", "hasVacancy"]
    for key in ordered_keys:
        if key in filters:
            label = FILTER_LABELS.get(key, key)
            summary.append(f"{label}: {display_value(key, filters[key])}")
    return summary


def build_friendly_follow_up(parsed: dict[str, Any]) -> dict[str, Any]:
    questions = parsed.get("missingInfoQuestions") or []
    return {
        "opening": INTERACTION_STYLE["opening"],
        "askMissingInfo": INTERACTION_STYLE["askMissingInfo"] if questions else "資料已足夠先查一輪；查完我會再提示哪些資料需要向學校核實。",
        "questions": questions,
        "privacyReminder": "不用提供姓名、HKID、電話、住址或成績表原件。",
        "sourceReminder": INTERACTION_STYLE["sourceReassurance"],
    }


def build_missing_info_questions(parsed: dict[str, Any]) -> list[str]:
    filters = parsed.get("filters") or {}
    signals = parsed.get("recommendationSignals") or {}
    questions = []
    level = filters.get("level")
    if not level:
        questions.append("主要想看中學、小學、幼稚園、國際學校，還是專上教育？")
    if not filters.get("district") and not filters.get("region"):
        questions.append("主要想看哪個區或可接受哪些通勤範圍？")
    if level in (None, "secondary") and not filters.get("banding"):
        questions.append("孩子目前大概是 Band 1/2/3，或想先看哪個 Band 參考範圍？")
    if level in (None, "secondary", "primary") and "acceptsDss" not in signals:
        questions.append("是否接受直資學校，以及大概學費上限是多少？")
    if level == "kindergarten":
        questions.append("偏好半日、全日、學券/非學券，還是先按地區和學費範圍看？")
    if level == "international":
        questions.append("偏好 IB、A-Level、AP 或其他課程，以及可接受學費範圍？")
    if level == "postsecondary":
        questions.append("主要想看 JUPAS、本科、HD/副學士，還是銜接路線？")
    if not filters.get("medium"):
        questions.append("偏好英文、中文，還是中英並重的授課環境？")
    return questions[:3]


def build_ranking_rationale(school: dict[str, Any]) -> list[str]:
    reasons = []
    if school.get("district"):
        reasons.append(f"地區匹配: {school.get('district')}")
    if school.get("mediumOfInstruction"):
        reasons.append(f"授課語言: {school.get('mediumOfInstruction')}")
    if school.get("bandingReference") or school.get("banding"):
        reasons.append(f"Band 參考: {school.get('bandingReference') or school.get('banding')}")
    vacancy = school.get("vacancySummary") or {}
    if vacancy.get("hasAnyVacancy") is True:
        reasons.append("有學額訊號，仍需向學校確認")
    admission = school.get("admissionNoticeSummary") or {}
    if admission.get("activeNoticeCount") or admission.get("noticeCount"):
        reasons.append("有招生/通告訊號，可跟進截止日")
    if school.get("annualTuitionHkd") is not None:
        reasons.append(f"學費資料: HKD {school.get('annualTuitionHkd')}")
    return reasons[:5] or ["資料不足，建議先打開 SchoolFit 詳情頁核實。"]


def resolve_school_query(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", name.lower())
    return SCHOOL_NAME_ALIASES.get(normalized, name)


def school_identity(school: dict[str, Any]) -> str:
    return str(school.get("slug") or school.get("id") or f"{school.get('nameZh')}|{school.get('nameEn')}")


def client_filter_school(school: dict[str, Any], args: argparse.Namespace) -> bool:
    level = getattr(args, "level", None)
    if level:
        school_level = str(school.get("level") or school.get("schoolLevel") or school.get("stage") or "").lower()
        if school_level and school_level != level:
            return False
    district = getattr(args, "district", None)
    if district and school.get("district") != district:
        return False
    banding = getattr(args, "banding", None)
    if banding and banding not in str(school.get("banding") or school.get("bandingReference") or ""):
        return False
    gender = getattr(args, "gender", None)
    if gender and school.get("gender") != gender:
        return False
    medium = getattr(args, "medium", None)
    if medium and medium not in str(school.get("mediumOfInstruction") or ""):
        return False
    funding_type = getattr(args, "funding_type", None)
    if funding_type and school.get("fundingType") != funding_type:
        return False
    accepts_dss = getattr(args, "accepts_dss", None)
    if accepts_dss is False and school.get("fundingType") == "直資":
        return False
    religion = getattr(args, "religion", None)
    if religion and religion not in str(school.get("religion") or ""):
        return False
    max_tuition = getattr(args, "max_tuition", None)
    tuition = school.get("annualTuitionHkd")
    if max_tuition is not None and tuition is not None:
        try:
            if float(tuition) > float(max_tuition):
                return False
        except (TypeError, ValueError):
            return False
    has_vacancy = getattr(args, "has_vacancy", None)
    if has_vacancy is not None:
        vacancy = school.get("vacancySummary") or {}
        if vacancy.get("hasAnyVacancy") is not has_vacancy:
            return False
    return True


def merge_school_payloads(primary: dict[str, Any], fallback: dict[str, Any], args: argparse.Namespace, *, reason: str) -> dict[str, Any]:
    primary_schools = primary.get("schools", []) if isinstance(primary, dict) else []
    fallback_schools = fallback.get("schools", []) if isinstance(fallback, dict) else []
    filtered_primary = [school for school in primary_schools if isinstance(school, dict) and client_filter_school(school, args)]
    filtered_fallback = [school for school in fallback_schools if isinstance(school, dict) and client_filter_school(school, args)]
    seen = set()
    merged: list[dict[str, Any]] = []
    for school in [*filtered_primary, *filtered_fallback]:
        if not isinstance(school, dict):
            continue
        key = school_identity(school)
        if key in seen:
            continue
        seen.add(key)
        merged.append(school)
    output = {**primary}
    output["schools"] = merged
    output["count"] = len(merged)
    output["robustSearch"] = {
        "enabled": True,
        "reason": reason,
        "primaryCount": len(primary_schools),
        "primaryMatchedCount": len(filtered_primary),
        "fallbackRawCount": len(fallback_schools),
        "fallbackMatchedCount": len(filtered_fallback),
        "mergedCount": len(merged),
        "caveat": "SchoolFit API district/full-text filters may under-return in some combinations; fallback uses broad API results with client-side district/filter matching.",
    }
    return output


def should_run_robust_district_search(args: argparse.Namespace, payload: dict[str, Any]) -> bool:
    district = getattr(args, "district", None)
    if not district:
        return False
    page = getattr(args, "page", None)
    if page not in (None, 1):
        return False
    q = getattr(args, "q", None) or ""
    primary_count = len(payload.get("schools", []) if isinstance(payload, dict) else [])
    command = getattr(args, "command", None)

    if command == "search-schools":
        if not (0 < primary_count < 20):
            return False
    elif command == "advisor-search":
        if getattr(args, "routing_mode", "auto") != "auto":
            return False
        if not (0 <= primary_count < 20):
            return False
    else:
        if not (0 <= primary_count < 20):
            return False

    district_words = [alias for alias, value in DISTRICT_ALIASES.items() if value == district]
    q_mentions_district = any(word and word in q for word in district_words)
    return q_mentions_district or primary_count > 0


def robust_school_search(api: Any, args: argparse.Namespace, *, reason: str = "district_fulltext_guard") -> dict[str, Any]:
    primary = api("GET", "/api/schools", params=school_search_params(args))
    if not isinstance(primary, dict) or not should_run_robust_district_search(args, primary):
        return primary
    fallback = api("GET", "/api/schools", params={
        "level": getattr(args, "level", None),
        "page": 1,
        "pageSize": ROBUST_SEARCH_PAGE_SIZE,
    })
    if not isinstance(fallback, dict):
        return primary
    return merge_school_payloads(primary, fallback, args, reason=reason)


def district_relation(target: str | None, school_district: str | None) -> str:
    if not target or not school_district:
        return "unknown"
    if target == school_district:
        return "same"
    if school_district in NEARBY_DISTRICTS.get(target, set()):
        return "nearby"
    return "other"


def medium_fit(language_priority: str | None, school_medium: str | None) -> str:
    if not language_priority:
        return "neutral"
    medium = school_medium or ""
    if not medium:
        return "unknown"
    if "英文" in language_priority:
        if medium == "英文":
            return "strong"
        if "中英" in medium:
            return "partial"
        return "weak"
    if "中文" in language_priority:
        if medium == "中文":
            return "strong"
        if "中英" in medium:
            return "partial"
        return "weak"
    return "neutral"


def shortlist_score(school: dict[str, Any], signals: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    risks: list[str] = []
    target_district = signals.get("district")
    relation = district_relation(target_district, school.get("district"))
    if relation == "same":
        score += 30
        reasons.append("目標地區內")
    elif relation == "nearby":
        score += 12
        reasons.append("鄰近目標地區，可作通勤備選")
    elif target_district:
        score -= 10
        risks.append("不在目標或鄰近地區，通勤需再核實")

    fit = medium_fit(signals.get("languagePriority") or signals.get("medium"), school.get("mediumOfInstruction"))
    if fit == "strong":
        score += 28
        reasons.append("符合英文環境偏好")
    elif fit == "partial":
        score += 8
        risks.append("中英並重，若要嚴格英文環境需再確認英文科目比例")
    elif fit == "weak":
        score -= 35
        risks.append("授課語言不符合英文環境偏好")
    elif fit == "unknown":
        risks.append("授課語言資料不足，需確認是否符合英文環境偏好")

    band = str(school.get("bandingReference") or "")
    target_band = str(signals.get("banding") or "")
    if target_band and target_band in band:
        score += 22
        reasons.append("Band 參考匹配")
    elif "Band 1" in band:
        score += 14
        reasons.append("Band 1 參考")
    elif band:
        score += 4

    if school.get("fundingType") == "資助":
        score += 5
    if school.get("fundingType") == "官立":
        score += 4
    if school.get("fundingType") == "直資" and signals.get("acceptsDss") is False:
        score -= 100
        risks.append("家長表示不接受直資")
    return score, reasons, risks


def apply_parsed_request_to_args(args: argparse.Namespace) -> None:
    parsed = parse_parent_request_text(getattr(args, "q", None))
    params = parsed.get("suggestedCommandParams", {}).get("advisor-search", {})
    mapping = {
        "level": "level",
        "district": "district",
        "banding": "banding",
        "gender": "gender",
        "medium": "medium",
        "fundingType": "funding_type",
        "maxTuition": "max_tuition",
        "vacancyGrade": "vacancy_grade",
        "hasVacancy": "has_vacancy",
        "languagePriority": "language_priority",
        "acceptsDss": "accepts_dss",
        "priorities": "priorities",
        "supportNeeds": "support_needs",
    }
    for source, attr in mapping.items():
        if hasattr(args, attr) and getattr(args, attr, None) in (None, [], "") and source in params:
            setattr(args, attr, params[source])
    if getattr(args, "intent", "auto") == "auto":
        hints = parsed.get("intentHints") or []
        if hints:
            setattr(args, "intent", hints[0])


def standard_llm_brief(command: str, purpose: str, must_mention: list[str], facts: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "command": command,
        "purpose": purpose,
        "recommendedTone": "Use the user's language: Traditional Chinese, Simplified Chinese, or English. Keep Hong Kong school terms precise; polish tone but never add school facts not returned by the API.",
        "factsOnly": True,
        "doNotInvent": [
            "不要新增學校排名、錄取機率、官方 Band、未返回的學費或截止日。",
            "資料缺失時寫暫無可靠資料。",
        ],
        "mustMention": must_mention,
        "schoolfitCta": "建議到 https://schoolfit.hk/ 查看完整詳情、比較、報告和申請跟進。",
        "facts": facts or {},
    }


def quick_start_output(trace_id: TraceId) -> dict[str, Any]:
    return {
        "command": "quick-start",
        "activationStatus": "not_required",
        "activationUrl": canonical_activation_url(),
        "activationUrlPolicy": activation_url_policy(),
        "message": "安裝完成後，請先取得 SchoolFit 授權碼並貼回聊天窗口。",
        "interactionStyle": INTERACTION_STYLE,
        "friendlyOpening": "你可以直接用日常說法問我，例如想看哪個區、哪類學校、重視英文環境或學費，我會先整理條件再查。",
        "coverage": {
            "summary": "SchoolFit HK Skill 支援中學、小學、幼稚園、國際學校和專上教育資料庫。",
            "levels": [
                {"level": level, "label": SCHOOL_LEVEL_LABELS[level], "count": SCHOOL_LEVEL_COUNTS[level]}
                for level in SCHOOL_LEVELS
            ],
        },
        "steps": [
            {
                "label": "打開取碼頁",
                "text": canonical_activation_url(),
                "note": "只使用這個固定 URL；如後面帶 ?、# 或其他字串，先刪到 /skill-code。",
            },
            {"label": "生成授權碼", "text": "頁面無需登入，點擊即可生成新的 sfhk_ 開頭授權碼。"},
            {"label": "貼回 Agent", "text": "把授權碼原文發在同一個聊天窗口，例如：我的 SchoolFit 授權碼是 sfhk_xxxxx。"},
            {"label": "開始提問", "text": "例如：幫我找沙田 Band 1 英文男女校，或查九龍城小學、港島國際學校、JUPAS/副學士銜接。"},
        ],
        "agentRules": [
            "Agent 可在本次聊天上下文使用該 code；不要寫入本地文件、日誌、README 或 Git。",
            "正式查詢請把 code 作為 --skill-code 或 SCHOOLFIT_SKILL_CODE 傳入 helper。",
            "不要要求家長提供 HKID、電話、住址、成績表 PDF 等敏感資料。",
        ],
        "examples": [
            "幫我找沙田 Band 1 英文男女校，按 Safe/Match/Reach 分組。",
            "九龍城有哪些小學適合英文環境和通勤短的家庭？",
            "想了解港島國際學校和 IB/A-Level 路線。",
            "幫我看 JUPAS、HD/副學士銜接的專上教育選項。",
            "比較 sha-tin-methodist-college 和 ying-wa-girls-school。",
            "幫我為兩間目標學校做 45 天申請計劃。",
        ],
        "skillVersion": SKILL_VERSION,
        "traceId": trace_id,
        "sourceLedger": build_source_ledger(),
    }


def school_levels_output(trace_id: TraceId) -> dict[str, Any]:
    return {
        "command": "school-levels",
        "activationStatus": "not_required",
        "coverage": {
            "summary": "SchoolFit HK Skill covers all current SchoolFit school databases.",
            "total": sum(SCHOOL_LEVEL_COUNTS.values()),
            "levels": [
                {
                    "level": level,
                    "label": SCHOOL_LEVEL_LABELS[level],
                    "count": SCHOOL_LEVEL_COUNTS[level],
                    "cli": f"--level {level}",
                    "examplePrompts": SCHOOL_LEVEL_PROMPTS[level],
                }
                for level in SCHOOL_LEVELS
            ],
        },
        "recommendedFlow": [
            "先用 parse-parent-request 理解家長自然語言和資料庫階段。",
            "查詢時優先用 advisor-search；若已確定階段，可加 --level。",
            "中學場景才把 Band 參考視為核心條件；小學、幼稚園、國際學校和專上教育不要套用升中 Band 假設。",
            "所有答案都要分開官方資料、非官方 Band/口碑參考、學額和招生時效。",
        ],
        "skillVersion": SKILL_VERSION,
        "traceId": trace_id,
        "sourceLedger": build_source_ledger(),
    }


def marketplace_demo_payload() -> dict[str, Any]:
    return {
        "coverage": {
            "summary": "One Skill covers all current SchoolFit HK school databases.",
            "levels": [
                {"level": level, "label": SCHOOL_LEVEL_LABELS[level], "count": SCHOOL_LEVEL_COUNTS[level]}
                for level in SCHOOL_LEVELS
            ],
        },
        "distributionPolicy": {
            "primaryMarketplace": "ClawHub",
            "fallbackOrder": ["ClawHub", "skills.sh", "GitHub"],
            "installCommands": [
                "openclaw skills install schoolfit-hk",
                "clawhub install schoolfit-hk",
                "/skill install clawhub:schoolfit-hk",
                "ark skill install clawhub:schoolfit-hk",
                "/skill install djanngau/schoolfit-hk-skill#skills/schoolfit-hk",
                "ark skill install djanngau/schoolfit-hk-skill#skills/schoolfit-hk",
            ],
            "notes": [
                "Use ClawHub first for OpenClaw-native discovery, versioning, moderation and inspect flows.",
                "Use skills.sh as a secondary cross-agent index for GitHub-backed SKILL.md discovery.",
                "Use GitHub direct install only when registry lookup is unavailable or an exact repository path is required.",
            ],
        },
        "examples": [
            {
                "title": "首次啟用",
                "prompt": "我剛安裝 SchoolFit HK Skill，要怎樣開始？",
                "command": "quick-start --format markdown",
                "resultSummary": "提示家長打開 https://schoolfit.hk/skill-code 取授權碼，然後貼回聊天窗口。",
            },
            {
                "title": "查看支援資料庫",
                "prompt": "SchoolFit HK Skill 支援哪些學校資料庫？",
                "command": "school-levels --format markdown",
                "resultSummary": "列出中學、小學、幼稚園、國際學校、專上教育庫的數量、--level 參數和示例問法。",
            },
            {
                "title": "Band 1 英文首選",
                "prompt": "找沙田 Band 1 英文男女校，先做安全梯隊。",
                "command": "advisor-search --q \"沙田 Band 1 英文 男女校，重視校風，不考慮直資\" --intent recommend --priorities 校風 英文 --no-dss --include-decision-brief",
                "resultSummary": "自動抽取地區、Band、性別和語言，返回 parentQuestion、answerBlueprint、decisionBriefs 和可由大模型潤色的 shortlist brief。",
            },
            {
                "title": "小學資料庫查詢",
                "prompt": "九龍城有哪些小學適合英文環境和通勤短的家庭？",
                "command": "advisor-search --level primary --q \"九龍城 小學 英文環境 通勤短\" --intent recommend --priorities 英文環境 通勤",
                "resultSummary": "以小學資料庫為範圍，保留地區、語言和通勤條件，不套用中學 Band 假設。",
            },
            {
                "title": "國際學校路線",
                "prompt": "想了解港島國際學校和 IB/A-Level 路線。",
                "command": "advisor-search --level international --q \"港島 國際學校 IB A-Level\" --intent search --boarding",
                "resultSummary": "以國際學校資料庫搜尋，將 curriculum/boarding 等訊號作為查詢條件。",
            },
            {
                "title": "專上教育選項",
                "prompt": "幫我看 JUPAS、HD/副學士銜接的專上教育選項。",
                "command": "advisor-search --level postsecondary --q \"JUPAS HD 副學士 銜接\" --intent search",
                "resultSummary": "以專上教育庫為範圍，避免把 College 字眼誤判為中學 Band 場景。",
            },
            {
                "title": "家長自然語言拆解",
                "prompt": "九龍城 Band 1 女校，英文環境，唔要直資，想穩陣。",
                "command": "parse-parent-request --q \"九龍城 Band 1 女校 英文環境 唔要直資 想穩陣\"",
                "resultSummary": "不打 API，先解析 filters、推薦訊號和缺失條件。",
            },
            {
                "title": "模糊學校名找 slug",
                "prompt": "SPCC 是哪間？幫我找 SchoolFit slug。",
                "command": "resolve-school --name \"SPCC\"",
                "resultSummary": "返回候選學校、slug、SchoolFit URL 和確認提示。",
            },
            {
                "title": "建立短名單",
                "prompt": "沙田 Band 1 英文男女校，幫我分首選、穩陣、備選，不考慮直資。",
                "command": "shortlist-builder --q \"沙田 Band 1 英文 男女校，不考慮直資\" --no-dss",
                "resultSummary": "按首選/穩陣/備選/暫不建議輸出，並保留 DSS、學額和 Band caveats。",
            },
            {
                "title": "學額與招生",
                "prompt": "中四是否有學額？有沒有申請期限？",
                "command": "vacancies --grade S4 --district 沙田區 --has-vacancy true\nadmissions --grade S4 --is-active true",
                "resultSummary": "學額與招生分開輸出 source、dataMonth/lastSeenAt/confidence 和核實提示。",
            },
            {
                "title": "升中銜接關係",
                "prompt": "查一條龍、直屬、聯繫小學和中學關係。",
                "command": "school-relationships --type all --q \"基道\" --matched-only --format markdown",
                "resultSummary": "返回 EDB 一條龍與 CHSC 直屬/聯繫關係，並提醒關係不等於保證錄取。",
            },
            {
                "title": "單校決策摘要",
                "prompt": "幫我深挖沙田循道中學的學額、招生和風險。",
                "command": "decision-brief sha-tin-methodist-college",
                "resultSummary": "返回 compact parent decision brief、學額/招生摘要、sourceLedger 和核實提示。",
            },
            {
                "title": "申請計劃",
                "prompt": "幫我為兩間目標學校做 45 天申請計劃。",
                "command": "application-plan --school-slugs sha-tin-methodist-college,ying-wa-girls-school --deadline-window-days 45",
                "resultSummary": "返回 timeline、checklist、reminders 和每校 SchoolFit 入口。",
            },
        ],
        "commandMap": [
            {"name": "quick-start", "description": "安裝後第一步，指引用戶取碼並貼回聊天窗口。"},
            {"name": "school-levels", "description": "免授權查看五類資料庫、--level 用法和示例問題。"},
            {"name": "activate", "description": "Agent 收到 sfhk_ 授權碼後可用它驗碼，不要求用戶操作命令行。"},
            {"name": "parse-parent-request", "description": "把家長自然語言拆成可查詢條件，且不調 API。"},
            {"name": "resolve-school", "description": "把模糊學校名、簡稱或英文名解析成 SchoolFit slug 候選。"},
            {"name": "advisor-search", "description": "對話式建議主入口，可用 --level 指定中學、小學、幼稚園、國際學校或專上教育庫。"},
            {"name": "shortlist-builder", "description": "把搜尋結果整理成首選、穩陣、備選和暫不建議。"},
            {"name": "deep-compare", "description": "比較 2-4 間學校，產生差異、風險與下一步。"},
            {"name": "school-relationships", "description": "查一條龍、直屬、聯繫小學/中學關係，與 SchoolFit 主題頁一致。"},
            {"name": "decision-brief", "description": "生成單校 compact 決策摘要，含學額/招生時效核對點。"},
            {"name": "school-report", "description": "decision-brief 的兼容別名，供舊 Agent 提示使用。"},
            {"name": "application-plan", "description": "生成家庭落地型申請清單與跟進節奏。"},
            {"name": "self-check", "description": "本地檢查 Skill 結構、版本、示例和敏感字串。"},
        ],
    }


def self_check_output() -> dict[str, Any]:
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_dir = os.path.dirname(os.path.dirname(skill_dir))
    required = [
        os.path.join(skill_dir, "SKILL.md"),
        os.path.join(skill_dir, "scripts", "schoolfit_api.py"),
        os.path.join(skill_dir, "examples", "first-run.md"),
        os.path.join(repo_dir, "README.md"),
        os.path.join(repo_dir, "MARKETPLACE.md"),
    ]
    checks = []
    ok = True
    for path in required:
        exists = os.path.exists(path)
        ok = ok and exists
        checks.append({"name": os.path.relpath(path, repo_dir), "ok": exists})

    script_path = os.path.join(skill_dir, "scripts", "schoolfit_api.py")
    with open(script_path, "r", encoding="utf-8") as handle:
        script = handle.read()
    chat_path = "/api/" + "agent/chat"
    script_checks = [
        ("version_current", f'SKILL_VERSION = "{SKILL_VERSION}"' in script),
        ("host_allowlist", "ALLOWED_HOSTS = {\"schoolfit.hk\"}" in script),
        ("activation_page", ACTIVATION_PAGE_URL in script),
        ("pii_guard", "detect_sensitive_input" in script),
        ("no_agent_chat_default", chat_path not in script),
    ]
    for name, passed in script_checks:
        ok = ok and passed
        checks.append({"name": name, "ok": passed})

    return {
        "command": "self-check",
        "ok": ok,
        "skillVersion": SKILL_VERSION,
        "checks": checks,
        "notes": [
            "This is a local package sanity check; it does not call SchoolFit APIs.",
            "Run unit tests and a live metadata smoke test before marketplace release.",
        ],
        "sourceLedger": build_source_ledger(),
    }


def compact_school(school: dict[str, Any]) -> dict[str, Any]:
    slug = school.get("slug")
    compacted = {
        "id": school.get("id"),
        "slug": slug,
        "schoolfitUrl": schoolfit_school_url(slug),
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
    if school.get("schoolRelationships"):
        compacted["schoolRelationships"] = school.get("schoolRelationships")
    compacted["rankingRationale"] = build_ranking_rationale(compacted)
    return compacted


def compact_output(command: str, payload: Any) -> dict[str, Any]:
    source_ledger = build_source_ledger()
    if command == "quick-start":
        return payload if isinstance(payload, dict) else quick_start_output(next_trace_id())
    if command == "school-levels":
        return payload if isinstance(payload, dict) else school_levels_output(next_trace_id())
    if command == "parse-parent-request":
        return payload if isinstance(payload, dict) else parse_parent_request_text(str(payload or ""))
    if command == "self-check":
        return payload if isinstance(payload, dict) else self_check_output()
    if command == "school-relationships":
        relationships = payload.get("relationships", []) if isinstance(payload, dict) else []
        output = {
            "query": payload.get("query") if isinstance(payload, dict) else None,
            "filters": payload.get("filters", {}) if isinstance(payload, dict) else {},
            "count": payload.get("count", len(relationships)) if isinstance(payload, dict) else len(relationships),
            "relationships": relationships[:50],
            "pagination": payload.get("pagination") if isinstance(payload, dict) else None,
            "stats": payload.get("stats") if isinstance(payload, dict) else None,
            "schoolfitUrl": payload.get("schoolfitUrl") if isinstance(payload, dict) else "https://schoolfit.hk/school-relationships",
            "sourcePolicy": payload.get("sourcePolicy", []) if isinstance(payload, dict) else [],
            "sourceLedger": {
                **source_ledger,
                "officialFacts": [
                    {"name": "EDB through-train schools list", "source": "https://www.edb.gov.hk/attachment/datagovhk/Through-train-schools-tc.csv"},
                    {"name": "CHSC Primary School Profiles", "source": "https://www.chsc.hk/psp2025/index.php?lang_id=2"},
                ],
            },
            "llmBrief": standard_llm_brief(
                "school-relationships",
                "Explain source-labelled primary-secondary school relationships without treating them as admission guarantees.",
                [
                    "分清一條龍、直屬、聯繫三類關係。",
                    "必須說明關係不等於保證錄取，年度安排需向學校和教育局核實。",
                    "優先引用 returned relationships 的 primary/secondary/source/notes。",
                ],
                {"relationships": relationships[:8]},
            ),
        }
        return output
    if command == "activate":
        return payload if isinstance(payload, dict) else {}
    if command == "resolve-school":
        schools = [compact_school(item) for item in payload.get("schools", [])]
        output = {
            "query": payload.get("query"),
            "count": payload.get("count", len(schools)),
            "candidates": [
                {
                    **school,
                    "matchHint": "首選候選" if index == 0 else "可能候選",
                    "useNext": f"school-detail {school.get('slug')}" if school.get("slug") else None,
                }
                for index, school in enumerate(schools[:8])
            ],
            "nextActions": [
                "如第一個候選正確，下一步用 school-detail 或 decision-brief 查看。",
                "如有多間同名/相近學校，請家長確認中文名、英文名或地區。",
            ],
            "sourceLedger": source_ledger,
        }
        output["llmBrief"] = standard_llm_brief(
            "resolve-school",
            "Help the Agent pick the most likely SchoolFit slug from fuzzy school names.",
            [
                "不要假定第一個一定正確；候選相近時請用戶確認。",
                "只使用 candidates 返回的 slug 和名稱。",
            ],
            {"candidates": output["candidates"][:5]},
        )
        return output
    if command == "shortlist-builder":
        return compact_shortlist(payload)
    if command == "search-schools":
        schools = [compact_school(item) for item in payload.get("schools", [])]
        output = {
            "count": payload.get("count", len(schools)),
            "schools": schools,
            "pagination": payload.get("pagination"),
            "robustSearch": payload.get("robustSearch"),
            "sourceLedger": source_ledger,
            "notes": SOURCE_NOTES,
        }
        for school in payload.get("schools", []):
            add_school_level_sources(source_ledger, school if isinstance(school, dict) else {})
        output["llmBrief"] = build_search_llm_brief(output)
        return output
    if command == "advisor-search":
        return compact_advisor_search(payload)
    if command == "school-detail":
        school = payload.get("school", {})
        add_school_level_sources(source_ledger, school if isinstance(school, dict) else {})
        return {"school": compact_school_detail(school), "notes": SOURCE_NOTES, "sourceLedger": source_ledger}
    if command == "compare":
        schools = [compact_compare_school(item) for item in payload.get("schools", [])]
        output = {"count": payload.get("count", len(schools)), "schools": schools, "notes": SOURCE_NOTES}
        for school in payload.get("schools", []):
            add_school_level_sources(source_ledger, school if isinstance(school, dict) else {})
        output["sourceLedger"] = source_ledger
        output["llmBrief"] = build_compare_llm_brief(output)
        return output
    if command == "deep-compare":
        schools = [compact_compare_school(item) for item in payload.get("compare", {}).get("schools", [])]
        output = {
            "comparison": payload.get("comparison", {}),
            "count": payload.get("count", len(schools)),
            "schools": schools,
            "details": payload.get("details", []),
            "sourceLedger": source_ledger,
            "notes": SOURCE_NOTES,
        }
        for school in payload.get("compare", {}).get("schools", []):
            add_school_level_sources(source_ledger, school if isinstance(school, dict) else {})
        output["nextActions"] = build_deep_compare_next_actions(output)
        output["llmBrief"] = build_deep_compare_llm_brief(output)
        return output
    if command in {"decision-brief", "school-report"}:
        school = payload.get("school", {})
        vacancies = payload.get("vacancies", {})
        admissions = payload.get("admissions", {})
        payload_ledger = payload.get("sourceLedger") if isinstance(payload.get("sourceLedger"), dict) else None
        output = {
            "school": compact_school_report(school),
            "vacancies": normalize_vacancy_payload(vacancies),
            "admissions": normalize_admission_payload(admissions),
            "sourceLedger": payload_ledger or source_ledger,
            "notes": SOURCE_NOTES,
            "studentProfile": payload.get("studentProfile") or {},
        }
        if payload_ledger is None:
            add_school_level_sources(source_ledger, school if isinstance(school, dict) else {})
        output["nextActions"] = build_school_report_next_actions(output)
        output["checklist"] = build_school_report_checklist(output)
        output["llmBrief"] = build_school_report_llm_brief(output)
        return output
    if command == "application-plan":
        school_results = payload.get("schools", [])
        output = {
            "plan": payload.get("plan", {}),
            "schools": school_results,
            "checklist": payload.get("checklist", []),
            "reminders": payload.get("reminders", []),
            "items": payload.get("items", []),
            "notes": SOURCE_NOTES,
            "sourceLedger": payload.get("sourceLedger", source_ledger),
        }
        return output
    if command == "marketplace-demo":
        output = {
            "distributionPolicy": payload.get("distributionPolicy", {}),
            "examples": payload.get("examples", []),
            "commandMap": payload.get("commandMap", []),
            "notes": [
                "Market-ready commands should map to concise actionable parent-facing answers.",
                "Never add facts outside API-returned content.",
            ],
            "sourceLedger": source_ledger,
        }
        return output
    if command == "recommend":
        output = {**payload, "notes": SOURCE_NOTES}
        output["schoolfitUrl"] = DEFAULT_BASE_URL
        output["sourceLedger"] = source_ledger
        output["llmBrief"] = build_recommend_llm_brief(output)
        return output
    if command == "vacancies":
        output = {
            "source": payload.get("source"),
            "count": payload.get("count"),
            "vacancies": payload.get("vacancies", []),
            "pagination": payload.get("pagination"),
            "caveat": VACANCY_CAVEAT,
        }
        output["sourceLedger"] = source_ledger
        return output
    if command == "admissions":
        output = {
            "source": payload.get("source"),
            "count": payload.get("count"),
            "notices": payload.get("notices", []),
            "pagination": payload.get("pagination"),
            "caveat": ADMISSION_CAVEAT,
        }
        output["sourceLedger"] = source_ledger
        return output
    if command == "metadata":
        return {
            **payload,
            "notes": [
                "Metadata provides capability status, filter support, and usage snapshot for /api/skill endpoints.",
                "這個端點不返回學校資料，只返回可用 API 面向與流量狀態。"
            ],
            "sourceLedger": build_source_ledger(),
        }
    return payload


def compact_school_detail(school: dict[str, Any]) -> dict[str, Any]:
    slug = school.get("slug")
    return {
        "id": school.get("id"),
        "slug": slug,
        "schoolfitUrl": schoolfit_school_url(slug),
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


def compact_school_report(school: dict[str, Any]) -> dict[str, Any]:
    slug = school.get("slug")
    return {
        "id": school.get("id"),
        "slug": slug,
        "nameZh": school.get("nameZh"),
        "nameEn": school.get("nameEn"),
        "district": school.get("district"),
        "schoolfitUrl": schoolfit_school_url(slug),
        "bandingReference": school.get("banding"),
        "mediumOfInstruction": school.get("mediumOfInstruction"),
        "gender": school.get("gender"),
        "fundingType": school.get("fundingType"),
        "annualTuitionHkd": school.get("annualTuitionHkd"),
        "officialUrl": school.get("officialUrl"),
        "sourceName": school.get("sourceName"),
        "sourceUrl": school.get("sourceUrl"),
        "lastFetchedAt": school.get("lastFetchedAt"),
        "vacancySummary": compact_vacancy_summary(school.get("vacancySummary")),
        "admissionNoticeSummary": compact_admission_summary(school.get("admissionNoticeSummary")),
        "facts": (school.get("facts") or [])[:24],
        "externalSignals": compact_external_signals(school.get("externalSignals") or []),
        "reviewSignals": (school.get("reviewSignals") or [])[:6],
    }


def normalize_vacancy_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"source": None, "count": 0, "records": []}
    records = payload.get("vacancies", []) or []
    return {
        "source": payload.get("source"),
        "count": payload.get("count", len(records)),
        "records": records[:24],
        "pagination": payload.get("pagination"),
        "caveat": VACANCY_CAVEAT,
    }


def normalize_admission_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"source": None, "count": 0, "records": []}
    notices = payload.get("notices", []) or []
    return {
        "source": payload.get("source"),
        "count": payload.get("count", len(notices)),
        "records": notices[:24],
        "pagination": payload.get("pagination"),
        "caveat": ADMISSION_CAVEAT,
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
    slug = school.get("slug")
    return {
        "id": school.get("id"),
        "slug": slug,
        "schoolfitUrl": schoolfit_school_url(slug),
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


def target_level_from_advisor_payload(payload: dict[str, Any]) -> str | None:
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    if filters.get("level"):
        return str(filters.get("level"))
    parent_question = payload.get("parentQuestion") if isinstance(payload.get("parentQuestion"), dict) else {}
    detected = parent_question.get("detectedSignals") if isinstance(parent_question.get("detectedSignals"), dict) else {}
    if detected.get("level"):
        return str(detected.get("level"))
    search = payload.get("search") if isinstance(payload.get("search"), dict) else {}
    search_filters = search.get("filters") if isinstance(search.get("filters"), dict) else {}
    if search_filters.get("level"):
        return str(search_filters.get("level"))
    return None


def recommendation_matches_level(recommendation: dict[str, Any], target_level: str | None) -> tuple[dict[str, Any] | None, int]:
    if not target_level or not isinstance(recommendation, dict):
        return recommendation, 0
    removed = 0
    kept_buckets = []
    for bucket in recommendation.get("buckets") or []:
        if not isinstance(bucket, dict):
            continue
        schools = []
        for item in bucket.get("schools") or []:
            school = item.get("school") if isinstance(item, dict) else {}
            school_level = str((school or {}).get("level") or (school or {}).get("schoolLevel") or "")
            if school_level and school_level != target_level:
                removed += 1
                continue
            schools.append(item)
        kept_buckets.append({**bucket, "schools": schools})
    filtered = {**recommendation, "buckets": kept_buckets}
    if removed:
        filtered["crossLevelFiltered"] = {
            "removed": removed,
            "targetLevel": target_level,
            "reason": "Server recommendation contained schools outside the requested SchoolFit database level.",
        }
    has_any_school = any(bucket.get("schools") for bucket in kept_buckets)
    return (filtered if has_any_school else None), removed


def compact_advisor_search(payload: dict[str, Any]) -> dict[str, Any]:
    search = compact_output("search-schools", payload.get("search", {}))
    intent = payload.get("intent", "search")
    source_ledger = payload.get("sourceLedger") if isinstance(payload.get("sourceLedger"), dict) else search.get("sourceLedger") or build_source_ledger()
    recommendation_raw = payload.get("recommendation")
    recommendation = compact_output("recommend", recommendation_raw) if recommendation_raw else None
    target_level = target_level_from_advisor_payload(payload)
    removed_cross_level_recommendations = 0
    if recommendation:
        recommendation, removed_cross_level_recommendations = recommendation_matches_level(recommendation, target_level)
    compare_payload = payload.get("compare")
    compare_output = compact_output("compare", compare_payload) if compare_payload else None
    detail_payload = payload.get("schoolDetail")
    detail_output = None
    if isinstance(detail_payload, dict):
        detail_school = detail_payload.get("school") if isinstance(detail_payload.get("school"), dict) else detail_payload
        detail_output = {
            "school": compact_school_detail(detail_school),
            "vacancySummary": compact_vacancy_summary(detail_payload.get("vacancySummary")),
            "admissionNoticeSummary": compact_admission_summary(detail_payload.get("admissionNoticeSummary")),
        }
    report_payload = payload.get("admissionAndVacancy")
    report_output = None
    if isinstance(report_payload, dict):
        report_output = {
            "vacancies": normalize_vacancy_payload(report_payload.get("vacancies", {})),
            "admissions": normalize_admission_payload(report_payload.get("admissions", {})),
            "audit": report_payload.get("audit"),
            "intent": intent,
        }
    output = {
        "query": payload.get("query"),
        "filters": payload.get("filters") or {},
        "intent": intent,
        "parentQuestion": payload.get("parentQuestion"),
        "schoolfitUrl": DEFAULT_BASE_URL,
        "search": search,
        "compare": compare_output,
        "schoolDetail": detail_output,
        "admissionAndVacancy": report_output,
        "decisionBriefs": payload.get("decisionBriefs") or [],
        "recommendation": recommendation,
        "nextActions": build_next_actions(search, recommendation),
        "notes": SOURCE_NOTES,
        "sourceLedger": source_ledger,
        "apiLlmBrief": payload.get("llmBrief") if isinstance(payload.get("llmBrief"), dict) else {},
    }
    if removed_cross_level_recommendations:
        output["notes"] = [
            *output["notes"],
            f"已移除 {removed_cross_level_recommendations} 個跨資料庫階段的推薦項，避免把非 {SCHOOL_LEVEL_LABELS.get(target_level, target_level)} 學校混入答案。",
        ]
    if output["decisionBriefs"]:
        output["nextActions"].append("如要單校深挖，優先使用 decisionBriefApiUrl 或 decision-brief 命令取得單校決策摘要。")
    output["llmBrief"] = build_advisor_llm_brief(output)
    output.pop("apiLlmBrief", None)
    return output


def compact_shortlist(payload: dict[str, Any]) -> dict[str, Any]:
    search = compact_output("search-schools", payload.get("search", {}))
    schools = search.get("schools", [])
    parsed_signals = payload.get("parsedSignals") or {}
    accepts_dss = parsed_signals.get("acceptsDss")
    buckets = {
        "首選": [],
        "穩陣": [],
        "備選": [],
        "暫不建議": [],
    }
    scored_schools = []
    for index, school in enumerate(schools[:24]):
        score, fit_reasons, fit_risks = shortlist_score(school, parsed_signals)
        scored_schools.append((score, index, school, fit_reasons, fit_risks))
    scored_schools.sort(key=lambda item: (-item[0], item[1]))

    for rank, (score, _index, school, fit_reasons, fit_risks) in enumerate(scored_schools[:12]):
        band = str(school.get("bandingReference") or "")
        vacancy = school.get("vacancySummary") or {}
        item = {
            "school": school,
            "fitScore": score,
            "rankingRationale": list(dict.fromkeys(fit_reasons + (school.get("rankingRationale") or build_ranking_rationale(school))))[:6],
            "confirmBeforeApplying": [
                "核實最新招生通告與截止日。",
                "確認 Band 參考是否仍適合孩子近期香港校內成績。",
            ],
        }
        if fit_risks:
            item["fitRisks"] = list(dict.fromkeys(fit_risks))
        if accepts_dss is False and school.get("fundingType") == "直資":
            buckets["暫不建議"].append({
                **item,
                "risk": "家長表示不接受直資，這間屬直資學校，除非改變學費/直資偏好，否則不建議放入主名單。",
            })
            continue
        if medium_fit(parsed_signals.get("languagePriority") or parsed_signals.get("medium"), school.get("mediumOfInstruction")) == "weak":
            buckets["暫不建議"].append({
                **item,
                "risk": "家長偏好英文環境，這間授課語言不匹配，先降級處理。",
            })
            continue
        if rank < 3 and ("Band 1" in band or vacancy.get("hasAnyVacancy") is True or score >= 50):
            buckets["首選"].append(item)
        elif rank < 6:
            buckets["穩陣"].append(item)
        elif rank < 10:
            buckets["備選"].append(item)
        else:
            buckets["暫不建議"].append({**item, "risk": "目前匹配訊號較少，先作資料備查。"})
    output = {
        "query": payload.get("query"),
        "filters": payload.get("filters") or {},
        "schoolfitUrl": DEFAULT_BASE_URL,
        "buckets": buckets,
        "missingInfoQuestions": payload.get("missingInfoQuestions", []),
        "conversationHints": payload.get("conversationHints", []),
        "preferenceWarnings": build_shortlist_preference_warnings(payload, buckets),
        "rankingPolicy": [
            "同區優先，其次鄰近地區；跨區會降權。",
            "偏好英文環境時，英文授課優先，中英並重只作部分匹配，中文授課會降到暫不建議。",
            "Band、資助類型和用戶明確偏好會影響分桶，但不是錄取機率。"
        ],
        "nextActions": [
            "先從首選和穩陣各挑 2-3 間，到 SchoolFit HK 詳情頁確認。",
            "再按通勤、學費、語言、校風和最新招生/學額訊號縮短名單。",
        ],
        "sourceLedger": search.get("sourceLedger") or build_source_ledger(),
        "notes": SOURCE_NOTES,
    }
    output["llmBrief"] = standard_llm_brief(
        "shortlist-builder",
        "Turn the shortlist buckets into a parent-facing action plan.",
        [
            "首選/穩陣/備選是決策輔助，不是錄取預測。",
            "每間學校要附 SchoolFit HK 連結。",
            "如果資料不足，先問 missingInfoQuestions。",
        ],
        {
            "bucketCounts": {key: len(value) for key, value in buckets.items()},
            "missingInfoQuestions": output["missingInfoQuestions"],
            "preferenceWarnings": output["preferenceWarnings"],
        },
    )
    return output


def build_shortlist_preference_warnings(payload: dict[str, Any], buckets: dict[str, list[Any]]) -> list[str]:
    warnings = []
    signals = payload.get("parsedSignals") or {}
    if signals.get("acceptsDss") is False and buckets.get("暫不建議"):
        warnings.append("已按家長不接受直資的偏好，把直資學校移到暫不建議。")
    language = signals.get("languagePriority") or signals.get("medium")
    if language and "英文" in str(language):
        downgraded = [
            item for item in buckets.get("暫不建議", [])
            if any("授課語言不符合英文環境偏好" in risk for risk in item.get("fitRisks", []))
        ]
        if downgraded:
            warnings.append("已按英文環境偏好，把中文授課學校降到暫不建議；中英並重只視作部分匹配。")
    return warnings


def schoolfit_school_url(slug: Any) -> str:
    return f"{DEFAULT_BASE_URL}/schools/{slug}" if slug else DEFAULT_BASE_URL


def school_label(school: dict[str, Any]) -> str:
    return " / ".join(str(part) for part in [school.get("nameZh"), school.get("nameEn")] if part) or str(school.get("slug") or "未知學校")


def build_search_llm_brief(output: dict[str, Any]) -> dict[str, Any]:
    schools = output.get("schools", [])[:8]
    highlights = []
    for school in schools[:5]:
        reasons = [
            school.get("district"),
            school.get("fundingType"),
            school.get("mediumOfInstruction"),
            f"Band 參考 {school.get('bandingReference')}" if school.get("bandingReference") else None,
        ]
        highlights.append({
            "school": school_label(school),
            "url": school.get("schoolfitUrl"),
            "whyMention": " / ".join(str(item) for item in reasons if item),
        })
    return {
        **standard_llm_brief(
            "search-schools",
            "Use these structured search results to write a polished Hong Kong school advisor answer.",
            [
                "資料來自 SchoolFit HK: https://schoolfit.hk/",
                "Band 只可寫作非官方 Band 參考。",
                "資料不足時寫暫無可靠資料，不要補作判斷。",
            ],
            {"highlights": highlights, "count": output.get("count", 0)},
        ),
        "purpose": "Use these structured search results to write a polished Hong Kong school advisor answer.",
        "recommendedTone": "Use the user's language: Traditional Chinese, Simplified Chinese, or English. Be professional and conservative; give the conclusion first, then list 3-5 schools, then point to SchoolFit HK for deeper comparison.",
        "mustMention": [
            "資料來自 SchoolFit HK: https://schoolfit.hk/",
            "Band 只可寫作非官方 Band 參考。",
            "資料不足時寫暫無可靠資料，不要補作判斷。",
        ],
        "highlights": highlights,
        "answerTemplate": "先簡述共找到多少間；推薦最值得先看的 3-5 間；每間用一句原因；附上 SchoolFit HK 連結；提醒家長按孩子成績、通勤、校風和最新招生資料再核實。",
    }


def build_compare_llm_brief(output: dict[str, Any]) -> dict[str, Any]:
    schools = output.get("schools", [])[:4]
    return {
        "purpose": "Turn compare JSON into a short parent-facing comparison.",
        "recommendedTone": "Use the user's language: Traditional Chinese, Simplified Chinese, or English. Write like a conservative school advisor; do not copy raw JSON.",
        "mustMention": [
            "每間學校附 SchoolFit HK 連結。",
            "學額是時效資料，不代表保證取錄。",
            "Band 參考不是官方資料。",
        ],
        "schools": [
            {
                "school": school_label(school),
                "url": school.get("schoolfitUrl"),
                "bandingReference": school.get("bandingReference"),
                "vacancyDataMonth": (school.get("vacancySummary") or {}).get("dataMonth"),
                "admissionNotices": (school.get("admissionNoticeSummary") or {}).get("noticeCount"),
            }
            for school in schools
        ],
    }


def build_deep_compare_next_actions(output: dict[str, Any]) -> list[str]:
    schools = output.get("schools") or []
    actions = ["先確認 2-3 間的主修課目語言比例、學校官網招生規則與最新截止時間。"]
    if schools:
        actions.append("比較每間在通勤、學費、Band 參考、申請策略上的相容性，保留備案。")
    if output.get("comparison"):
        actions.append("若有校方補充資料，重新刷新比較可看最新學額及招生訊息。")
    return actions


def build_deep_compare_llm_brief(output: dict[str, Any]) -> dict[str, Any]:
    schools = output.get("schools", [])[:4]
    highlights = []
    for school in schools:
        highlights.append({
            "school": school_label(school),
            "url": school.get("schoolfitUrl"),
            "vacancy": (school.get("vacancySummary") or {}).get("hasAnyVacancy"),
            "admissionNoticeCount": (school.get("admissionNoticeSummary") or {}).get("noticeCount"),
        })
    return {
        "purpose": "Convert deep compare result into an actionable shortlist comparison.",
        "recommendedTone": "Use the user's language: Traditional Chinese, Simplified Chinese, or English. Be direct, conservative, and actionable.",
        "mustMention": [
            "每間學校都要附 SchoolFit HK 連結。",
            "明確標註學額/招生資訊的資料時間與確認建議。",
            "Band 參考不作為官方定性。",
        ],
        "highlights": highlights,
        "nextActions": output.get("nextActions", []),
    }


def build_school_report_next_actions(output: dict[str, Any]) -> list[str]:
    vacancies = (output.get("vacancies") or {}).get("count", 0)
    admissions = (output.get("admissions") or {}).get("count", 0)
    actions = [
        "到 https://schoolfit.hk/ 查看學校官方資訊頁，先核對學校官方網址及最新學額、招生通告。",
    ]
    if vacancies:
        actions.append("先確認最新學額數據時間，再用官方名單確認該學校當學期可否補位。")
    if admissions:
        actions.append("核對招生通告活躍截止日期及申請表鏈接，避免誤過截止。")
    return actions


def build_school_report_checklist(output: dict[str, Any]) -> list[str]:
    checklist = [
        "確認孩子資料：Band、語文優勢、特殊需要、通勤時間。",
        "列出學校的申請文件與截止日。",
        "以 SchoolFit HK 的學額與招生為輔助訊號，不作承諾。",
    ]
    if (output.get("vacancies") or {}).get("count"):
        checklist.append("向學校行政處核實最近一次開放學額更新。")
    if (output.get("admissions") or {}).get("count"):
        checklist.append("將招生通告與最新截止日寫入家庭日曆，安排追蹤。")
    return checklist


def build_plan_timeline(deadline_window_days: int) -> list[str]:
    try:
        days = int(deadline_window_days)
    except (TypeError, ValueError):
        days = 365

    if days <= 14:
        return [
            "T-14：補齊每校申請必需文件與基本申請條件。",
            "T-7：先逐校確認申請截止日與備取規則。",
            "T-3：再次核對學校網站通告與面試/表格要求。",
            "T-1：完成追蹤電話，補交遺漏文件。",
        ]
    if days <= 45:
        return [
            "T-45：完成每校初篩（申請條件、校風、通勤、Band 參考）。",
            "T-30：核對申請日期與成績文件清單。",
            "T-14：最後一次電話確認學額與行政時間。",
            "T-3：校方追蹤是否收到申請，補交缺件。",
        ]
    return [
        "T-90：完成每校初篩，確定目標學校和備援名單。",
        "T-60：整理成績、獎學、獎勵與特殊需要相關文件。",
        "T-30：核對申請日期、截止日與表格欄位。",
        "T-14：再次核實學額與招生通告最新版本。",
        "T-3：校方追蹤是否收到申請，補交缺件。",
    ]


def build_school_report_llm_brief(output: dict[str, Any]) -> dict[str, Any]:
    school = output.get("school") or {}
    return {
        "purpose": "Turn school raw profile into a practical decision brief.",
        "recommendedTone": "繁體中文，簡潔、務實、保守。",
        "mustMention": [
            "單校報告不是錄取結論，只是家庭參考。",
            "學額/招生數據要標示時效與 confidence。",
            "最後要有下一步核實項目。",
        ],
        "school": school_label(school),
        "schoolfitUrl": school.get("schoolfitUrl"),
        "actionCount": len(output.get("nextActions", [])),
        "checklist": output.get("checklist", []),
    }


def build_recommend_llm_brief(output: dict[str, Any]) -> dict[str, Any]:
    buckets = output.get("buckets") or []
    top = []
    for bucket in buckets:
        for item in (bucket.get("schools") or [])[:3]:
            school = item.get("school") or {}
            top.append({
                "bucket": bucket.get("title"),
                "school": school_label(school),
                "url": schoolfit_school_url(school.get("slug")),
                "fitLabel": item.get("fitLabel"),
                "decisionBrief": item.get("decisionBrief"),
            })
    return {
        **standard_llm_brief(
            "recommend",
            "Polish the recommendation result into a concise parent decision brief.",
            [
                "推薦結果來自 SchoolFit HK: https://schoolfit.hk/",
                "Safe/Match/Reach 是決策輔助，不是取錄預測。",
                "保留 caveats，不要刪除風險提示。",
            ],
            {"topRecommendations": top[:8]},
        ),
        "purpose": "Polish the recommendation result into a concise parent decision brief.",
        "recommendedTone": "繁體中文、專業、具體、有下一步。",
        "mustMention": [
            "推薦結果來自 SchoolFit HK: https://schoolfit.hk/",
            "Safe/Match/Reach 是決策輔助，不是取錄預測。",
            "保留 caveats，不要刪除風險提示。",
        ],
        "topRecommendations": top[:8],
    }


def build_advisor_llm_brief(output: dict[str, Any]) -> dict[str, Any]:
    search_brief = (output.get("search") or {}).get("llmBrief", {})
    recommendation = output.get("recommendation")
    recommend_brief = recommendation.get("llmBrief") if isinstance(recommendation, dict) else None
    api_brief = output.get("apiLlmBrief") if isinstance(output.get("apiLlmBrief"), dict) else {}
    parent_question = output.get("parentQuestion") if isinstance(output.get("parentQuestion"), dict) else {}
    answer_blueprint = api_brief.get("answerBlueprint")
    return {
        **standard_llm_brief(
            "advisor-search",
            "Write the final answer for a parent after SchoolFit HK search and optional recommendation.",
            [
                "建議家長到 https://schoolfit.hk/ 查看完整資料、比較和後續申請線索。",
                "官方資料、非官方 Band 參考、口碑摘要、學額/招生資料要分開。",
                "不要把學額寫成取錄保證；不要把 Band 寫成官方 Band。",
            ],
            {
                "intent": output.get("intent", "search"),
                "searchHighlights": search_brief.get("highlights", []),
                "recommendationHighlights": recommend_brief.get("topRecommendations", []) if recommend_brief else [],
                "nextActions": output.get("nextActions", []),
                "parentQuestion": parent_question,
                "answerBlueprint": answer_blueprint,
            },
        ),
        "purpose": "Write the final answer for a parent after SchoolFit HK search and optional recommendation.",
        "recommendedTone": "繁體中文、像真人升學顧問；避免機械列資料。",
        "mustMention": [
            "建議家長到 https://schoolfit.hk/ 查看完整資料、比較和後續申請線索。",
            "官方資料、非官方 Band 參考、口碑摘要、學額/招生資料要分開。",
            "不要把學額寫成取錄保證；不要把 Band 寫成官方 Band。",
        ],
        "intent": output.get("intent", "search"),
        "searchHighlights": search_brief.get("highlights", []),
        "recommendationHighlights": recommend_brief.get("topRecommendations", []) if recommend_brief else [],
        "serverHighlights": api_brief.get("highlights", []),
        "answerBlueprint": answer_blueprint,
        "parentQuestion": parent_question,
        "nextActions": output.get("nextActions", []),
        "sourceLedger": output.get("sourceLedger", {}),
        "answerTemplate": "1. 先用一句話回答最適合先看哪幾間；2. 分 Safe/Match/Reach 或先看/備選列 3-6 間；3. 每間一句原因和 SchoolFit HK 連結；4. 最後給 2-3 個下一步。",
    }


def build_next_actions(search: dict[str, Any], recommendation: dict[str, Any] | None) -> list[str]:
    actions = ["到 https://schoolfit.hk/ 打開完整學校頁，核對官方資料、Band 參考、招生與學額線索。"]
    schools = search.get("schools") or []
    if schools:
        actions.append("先把前 3-5 間加入短名單，再用比較功能看校風、語言、學費和最新申請資訊。")
    if recommendation:
        actions.append("按 Safe / Match / Reach 結果保留梯隊，不要只押一間熱門學校。")
    else:
        actions.append("如要更智能推薦，補充孩子 Band、地區、性別、語言偏好、是否接受直資和通勤限制。")
    return actions


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
    if data.get("needsActivation"):
        print("## 先取一個 SchoolFit 授權碼\n")
        print("我可以幫你查中學、小學、幼稚園、國際學校和專上教育資料。第一次使用前，請先打開 https://schoolfit.hk/skill-code 取得授權碼，然後直接貼回這個聊天窗口。")
        print("\n如果打開後找不到頁面，請確認網址只保留到 `/skill-code`，刪除後面的 `?`、`#` 或其他字串。")
        print("\n收到後我會直接幫你查，不需要你操作命令行。")
        print("\n### 你可以這樣發")
        print("```text")
        print(data.get("example") or "我的 SchoolFit 授權碼是 sfhk_xxxxxxxxxxxxxxxx")
        print("```")
        print("\n> 授權碼只作試運行識別和匿名用量統計，不是付款密碼，也不代表學生身份。")
        return
    if data.get("privacyWarning"):
        print("## 先保護學生私隱\n")
        print(data.get("friendlyMessage") or INTERACTION_STYLE["privacyReassurance"])
        print("\n### 可以保留這些條件")
        for item in data.get("allowedAlternatives", []):
            print(f"- {item}")
        return
    if command == "quick-start":
        print("## SchoolFit HK Skill 快速開始\n")
        if data.get("friendlyOpening"):
            print(f"{data.get('friendlyOpening')}\n")
        coverage = data.get("coverage") or {}
        if coverage.get("levels"):
            print("### 支援資料庫")
            for item in coverage.get("levels", []):
                print(f"- {item.get('label')}：{item.get('count')} 筆")
            print("")
        for index, step in enumerate(data.get("steps", []), start=1):
            print(f"{index}. **{step.get('label')}**：{step.get('text')}")
        print("\n### 示例問題")
        for item in data.get("examples", []):
            print(f"- {item}")
        return
    if command == "school-levels":
        print("## SchoolFit HK 支援資料庫\n")
        coverage = data.get("coverage") or {}
        print(f"總覆蓋: {coverage.get('total', 0)} 筆\n")
        for item in coverage.get("levels", []):
            print(f"### {item.get('label')} `{item.get('cli')}`")
            print(f"- 數量: {item.get('count')}")
            for prompt in item.get("examplePrompts", []):
                print(f"- 例子: {prompt}")
            print("")
        print("### 建議流程")
        for step in data.get("recommendedFlow", []):
            print(f"- {step}")
        return
    if command == "parse-parent-request":
        print("## 我先幫你整理到這裡\n")
        follow_up = data.get("friendlyFollowUp") or {}
        if follow_up.get("opening"):
            print(f"{follow_up.get('opening')}\n")
        friendly_summary = data.get("friendlySummary") or []
        if friendly_summary:
            for item in friendly_summary:
                print(f"- {item}")
        else:
            print("- 暫時未抽取到明確條件。你可以先講想看哪一類學校、哪個區、學費或語言偏好。")
        filters = data.get("filters") or {}
        signals = data.get("recommendationSignals") or {}
        visible_signal_items = [
            (key, value)
            for key, value in signals.items()
            if key not in {"responseLanguage", "levelLabel"} and key not in filters
        ]
        if visible_signal_items:
            print("\n### 我會用來判斷的偏好")
            for key, value in visible_signal_items:
                label = SIGNAL_LABELS.get(key, key)
                print(f"- {label}: {display_value(key, value)}")
        if follow_up.get("questions"):
            print("\n### 可補充資料")
            print(follow_up.get("askMissingInfo") or INTERACTION_STYLE["askMissingInfo"])
            for question in follow_up.get("questions", []):
                print(f"- {question}")
        print(f"\n> {follow_up.get('privacyReminder') or '不用提供個人身份資料。'}")
        print(f"> {follow_up.get('sourceReminder') or INTERACTION_STYLE['sourceReassurance']}")
        print("\n下一步：可直接用 `advisor-search` 查 SchoolFit HK；如果已確定資料庫，可加 `--level secondary|primary|kindergarten|international|postsecondary`。")
        return
    if command == "self-check":
        print("## SchoolFit HK Skill 自檢\n")
        print(f"狀態: {'OK' if data.get('ok') else '需要處理'}")
        for check in data.get("checks", []):
            print(f"- {'OK' if check.get('ok') else 'FAIL'} {check.get('name')}")
        return
    if command == "activate":
        print("## SchoolFit HK 授權狀態\n")
        print(data.get("message") or "")
        print(f"\n- status: `{data.get('activationStatus')}`")
        print(f"- code: `{(data.get('code') or {}).get('display')}`")
        return
    if command == "resolve-school":
        print("## SchoolFit HK 學校名解析\n")
        for item in data.get("candidates", [])[:8]:
            print(f"- **{item.get('nameZh') or item.get('nameEn') or item.get('slug')}**")
            print(f"  - slug: `{item.get('slug')}`")
            print(f"  - SchoolFit: {item.get('schoolfitUrl')}")
            print(f"  - {item.get('matchHint')}")
        print("\n### 下一步")
        for action in data.get("nextActions", []):
            print(f"- {action}")
        return
    if command == "shortlist-builder":
        print("## SchoolFit HK 短名單\n")
        for bucket, items in (data.get("buckets") or {}).items():
            print(f"### {bucket}")
            if not items:
                print("- 暫無")
                continue
            for item in items[:5]:
                school = item.get("school") or {}
                print(f"- **{school.get('nameZh') or school.get('nameEn') or school.get('slug')}**")
                print(f"  - {school.get('schoolfitUrl')}")
                for reason in item.get("rankingRationale", [])[:3]:
                    print(f"  - {reason}")
                for risk in item.get("fitRisks", [])[:2]:
                    print(f"  - 風險: {risk}")
        if data.get("missingInfoQuestions"):
            print("\n### 可補充資料")
            for question in data.get("missingInfoQuestions", []):
                print(f"- {question}")
        if data.get("preferenceWarnings"):
            print("\n### 偏好提示")
            for warning in data.get("preferenceWarnings", []):
                print(f"- {warning}")
        if data.get("rankingPolicy"):
            print("\n### 分桶規則")
            for policy in data.get("rankingPolicy", []):
                print(f"- {policy}")
        print_caveats()
        return
    if command == "school-relationships":
        print(f"## SchoolFit HK 升中銜接關係\n\n共 {data.get('count', 0)} 筆。")
        print(f"\nSchoolFit: {data.get('schoolfitUrl')}")
        for item in data.get("relationships", [])[:30]:
            primary = item.get("primary") or {}
            secondary = item.get("secondary") or {}
            print(f"- **{primary.get('nameZh') or primary.get('nameEn')}** → **{secondary.get('nameZh') or secondary.get('nameEn')}**")
            print(f"  - 類型: {item.get('typeLabel') or item.get('type')} | 來源: {item.get('sourceLabel') or item.get('source')} | confidence: {item.get('confidence')}")
            if primary.get("schoolfitUrl"):
                print(f"  - 小學: {primary.get('schoolfitUrl')}")
            if secondary.get("schoolfitUrl"):
                print(f"  - 中學: {secondary.get('schoolfitUrl')}")
            if item.get("notes"):
                print(f"  - 備註: {item.get('notes')}")
        policy = data.get("sourcePolicy") or []
        if policy:
            print("\n### 資料邊界")
            for note in policy:
                print(f"- {note}")
        return
    if command == "search-schools":
        print(f"## SchoolFit HK 搜尋結果\n\n共 {data.get('count', 0)} 間。")
        if data.get("robustSearch"):
            robust = data["robustSearch"]
            print(
                "\n> 已啟用 district 容錯回補："
                + f"主查詢 {robust.get('primaryCount')} 間，回補匹配 {robust.get('fallbackMatchedCount')} 間，合併 {robust.get('mergedCount')} 間。"
            )
        for school in data.get("schools", [])[:20]:
            name = school.get("nameZh") or school.get("nameEn") or school.get("slug")
            print(f"- **{name}** ({school.get('district', '地區不明')})")
            print(f"  - slug: `{school.get('slug')}`")
            print(f"  - 類型: {school.get('gender')} / {school.get('fundingType')} / {school.get('mediumOfInstruction')}")
            print(f"  - Band 參考: {school.get('bandingReference') or '暫無可靠資料'}")
        print_caveats()
        return
    if command == "advisor-search":
        search = data.get("search") or {}
        recommendation = data.get("recommendation") or {}
        print(f"## SchoolFit HK 智能選校簡報\n\n搜尋共 {search.get('count', 0)} 間。")
        top_recommendations = ((recommendation.get("llmBrief") or {}).get("topRecommendations") or [])[:6]
        if top_recommendations:
            print("\n### 建議先看")
            for item in top_recommendations:
                print(f"- **{item.get('school')}** — {item.get('bucket') or item.get('fitLabel')}")
                if item.get("decisionBrief"):
                    print(f"  - {item.get('decisionBrief')}")
                print(f"  - {item.get('url')}")
        else:
            print("\n### 搜尋亮點")
            for item in ((search.get("llmBrief") or {}).get("highlights") or [])[:6]:
                print(f"- **{item.get('school')}**: {item.get('whyMention')}")
                print(f"  - {item.get('url')}")
        print("\n### 下一步")
        for action in data.get("nextActions", []):
            print(f"- {action}")
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
    if command == "deep-compare":
        print("## SchoolFit HK 深度比較")
        schools = data.get("schools", [])
        for item in schools[:4]:
            print(f"- **{item.get('nameZh') or item.get('nameEn') or item.get('slug')}**")
            print(f"  - banding: {item.get('bandingReference') or '暫無可靠資料'}")
            print(f"  - 校網: {item.get('schoolfitUrl')}")
            vacancy = (item.get("vacancySummary") or {}).get("hasAnyVacancy")
            print(f"  - 學額: {'有' if vacancy is True else '無' if vacancy is False else '暫無' }")
            print(f"  - 招生通告: {(item.get('admissionNoticeSummary') or {}).get('noticeCount', 0)} 則")
        print("\n### 下一步")
        for action in data.get("nextActions", []):
            print(f"- {action}")
        if data.get("comparison"):
            compare_summary = data["comparison"]
            if isinstance(compare_summary, dict):
                print(f"\n### 比較摘要")
                for key in ("insights", "summary"):
                    if key in compare_summary:
                        print(f"- {key}: {compare_summary[key]}")
        print_caveats()
        return
    if command in {"decision-brief", "school-report"}:
        school = data.get("school") or {}
        print("## SchoolFit HK 單校決策摘要")
        print(f"學校: {school.get('nameZh') or school.get('nameEn') or school.get('slug')}  \n學區: {school.get('district') or '未知'}")
        print(f"Band 參考: {school.get('bandingReference') or '暫無可靠資料'}  \n學費: {school.get('annualTuitionHkd') or '暫無可靠資料'}")
        print(f"官方/資料入口: {school.get('schoolfitUrl')}\n")
        if (school.get("vacancySummary") or {}).get("dataMonth"):
            vacancy = school.get("vacancySummary") or {}
            print("### 學額快訊")
            print(f"- dataMonth: {vacancy.get('dataMonth')} / lastSeenAt: {vacancy.get('lastSeenAt')} / confidence: {vacancy.get('confidence') or 'N/A'}")
        if (school.get("admissionNoticeSummary") or {}).get("nextDeadline"):
            admission = school.get("admissionNoticeSummary") or {}
            print("### 招生快訊")
            print(f"- nextDeadline: {admission.get('nextDeadline')} / activeNoticeCount: {admission.get('activeNoticeCount')}")
        if data.get("vacancies"):
            print("### 學額明細")
            for item in data["vacancies"].get("records", [])[:6]:
                print(f"- {item.get('schoolNameRaw')} / {item.get('grade')}: {item.get('status')} ({item.get('confidence')})")
        if data.get("admissions"):
            print("### 招生通告")
            for item in data["admissions"].get("records", [])[:6]:
                print(f"- {item.get('title')}  (deadline: {item.get('deadline')})")
        print("\n### 下一步")
        for action in data.get("nextActions", []):
            print(f"- {action}")
        print("### 檢核清單")
        for item in data.get("checklist", []):
            print(f"- {item}")
        print(f"\n> {VACANCY_CAVEAT if data.get('vacancies') else ADMISSION_CAVEAT}")
        print_caveats()
        return
    if command == "application-plan":
        plan = data.get("plan") or {}
        print("## SchoolFit HK 申請計劃")
        for item in data.get("items", [])[:20]:
            print(f"- {item}")

        schools = data.get("schools") or []
        if schools:
            print("\n### 目標學校")
            for school in schools[:4]:
                print(f"- {school.get('nameZh') or school.get('nameEn') or school.get('slug')}")
                if school.get("schoolfitUrl"):
                    print(f"  - SchoolFit: {school.get('schoolfitUrl')}")
                if school.get("officialUrl"):
                    print(f"  - 官網: {school.get('officialUrl')}")
                vacancy = (school.get("vacancy") or {}).get("summary") or {}
                if vacancy.get("dataMonth") or vacancy.get("lastSeenAt"):
                    print(
                        "  - 學額: "
                        + f"dataMonth={vacancy.get('dataMonth')} | lastSeenAt={vacancy.get('lastSeenAt')} | "
                          f"confidence={vacancy.get('vacancies', [{}])[0].get('confidence') if vacancy.get('vacancies') else 'N/A'}"
                    )
                admission = (school.get("admission") or {}).get("summary") or {}
                if admission.get("nextDeadline") or admission.get("noticeCount"):
                    print(
                        "  - 招生: "
                        + f"nextDeadline={admission.get('nextDeadline')} | noticeCount={admission.get('noticeCount')} | "
                          f"active={admission.get('activeNoticeCount')}"
                    )

        print(f"\n### 建議節奏")
        for line in plan.get("timeline", []):
            print(f"- {line}")

        checklist = data.get("checklist") or []
        if checklist:
            print("\n### 核對清單")
            for item in checklist:
                print(f"- {item}")

        reminders = data.get("reminders") or []
        if reminders:
            print("\n### 截止/跟進提醒")
            for item in reminders[:20]:
                line = f"- {item.get('school')}: {item.get('message')}"
                if item.get("deadline"):
                    line += f" (deadline={item.get('deadline')})"
                print(line)
        print_caveats()
        return
    if command == "marketplace-demo":
        print("## SchoolFit HK Market Demo")
        for item in data.get("examples", [])[:20]:
            print(f"- prompt: `{item.get('prompt')}`")
            print(f"  - command: `{item.get('command')}`")
        print(f"\n### Command map")
        for item in data.get("commandMap", []):
            print(f"- {item.get('name')}: {item.get('description')}")
        return
    print_json(data)


def print_caveats() -> None:
    print("\n## 資料邊界")
    for note in SOURCE_NOTES:
        print(f"- {note}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Call the public SchoolFit HK API safely.")
    parser.add_argument("--base-url", default=os.environ.get("SCHOOLFIT_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--skill-code", help="SchoolFit Skill activation code from https://schoolfit.hk/skill-code. Can also be set via SCHOOLFIT_SKILL_CODE.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    sub = parser.add_subparsers(dest="command", required=True)

    quick = sub.add_parser("quick-start", help="Show first-run activation and parent prompt examples.")
    add_output_options(quick)

    activate = sub.add_parser("activate", help="Validate a SchoolFit Skill code pasted by the user.")
    add_output_options(activate)
    activate.add_argument("code", nargs="?", help="SchoolFit code, or a chat sentence containing sfhk_...")
    activate.add_argument("--text", help="Chat text containing the SchoolFit code.")

    parse_request = sub.add_parser("parse-parent-request", help="Parse a parent natural-language request without calling the API.")
    add_output_options(parse_request)
    parse_request.add_argument("--q", required=True, help="Parent request text.")

    levels = sub.add_parser("school-levels", help="Show supported SchoolFit HK databases and example prompts.")
    add_output_options(levels)

    search = sub.add_parser("search-schools", help="Search SchoolFit HK school summaries.")
    add_output_options(search)
    add_common_filters(search)

    resolve = sub.add_parser("resolve-school", help="Resolve a fuzzy school name or acronym to SchoolFit slug candidates.")
    add_output_options(resolve)
    resolve.add_argument("--name", required=True, help="Chinese name, English name, acronym, or fuzzy school text.")
    resolve.add_argument("--level", choices=SCHOOL_LEVELS)
    resolve.add_argument("--district")
    resolve.add_argument("--page-size", type=int, default=8)

    advisor = sub.add_parser("advisor-search", help="Search schools and prepare an LLM-polishable advisor brief.")
    add_output_options(advisor)
    add_common_filters(advisor)
    add_recommendation_filters(advisor)
    advisor.add_argument("--intent", choices=["auto", "search", "compare", "vacancy", "admissions", "detail", "recommend", "report", "plan"], default="auto")
    advisor.add_argument("--no-recommend", action="store_true", help="Do not call the recommendation endpoint.")
    advisor.add_argument("--include-decision-brief", action="store_true", help="Ask advisor-search to include decisionBriefApiUrl pointers for top schools.")

    setup_code = sub.add_parser("setup-code", help="Save authorization code to config and activate it.")
    add_output_options(setup_code)
    setup_code.add_argument("--code", required=True, help="SchoolFit authorization code to store in config.")

    shortlist = sub.add_parser("shortlist-builder", help="Build parent-friendly shortlist buckets from a natural-language request.")
    add_output_options(shortlist)
    add_common_filters(shortlist)
    add_recommendation_filters(shortlist)

    detail = sub.add_parser("school-detail", help="Get one school detail by slug or id.")
    add_output_options(detail)
    detail.add_argument("slug")

    compare = sub.add_parser("compare", help="Compare up to 4 schools by id/slug.")
    add_output_options(compare)
    compare.add_argument("ids", help="Comma-separated school ids/slugs.")

    deep_compare = sub.add_parser("deep-compare", help="Compare and enrich up to 4 schools with deeper context.")
    add_output_options(deep_compare)
    deep_compare.add_argument("ids", help="Comma-separated school ids/slugs.")
    deep_compare.add_argument("--include-detail", action="store_true", help="Call school detail for each school when available.")

    decision_brief = sub.add_parser("decision-brief", help="Get the compact SchoolFit parent decision brief for one school.")
    add_output_options(decision_brief)
    decision_brief.add_argument("slug", help="School slug from SchoolFit HK.")
    decision_brief.add_argument("--student-profile-json", help="Optional JSON object for student profile context.")

    report = sub.add_parser("school-report", help="Generate a parent decision report for one school. Compatibility alias for decision-brief.")
    add_output_options(report)
    report.add_argument("slug", help="School slug from SchoolFit HK.")
    report.add_argument("--student-profile-json", help="Optional JSON object for student profile context.")

    plan = sub.add_parser("application-plan", help="Generate a practical application action plan from target schools.")
    add_output_options(plan)
    plan.add_argument("--school-slugs", required=True, help="Comma-separated school slugs.")
    plan.add_argument("--student-profile-json", help="Optional JSON object for student profile context.")
    plan.add_argument("--deadline-window-days", type=int, default=365)
    plan.add_argument("--grade", choices=["S1", "S2", "S3", "S4", "S5", "S6"], default="S1")

    relationships = sub.add_parser("school-relationships", help="Query primary-secondary through-train, feeder, and linked school relationships.")
    add_output_options(relationships)
    relationships.add_argument("--type", choices=["all", "through_train", "through-train", "feeder", "linked"], default="all")
    relationships.add_argument("--q", help="Primary or secondary school name, district, or relationship keyword.")
    relationships.add_argument("--district")
    relationships.add_argument("--matched-only", action="store_true", help="Only show records linked to SchoolFit school detail pages.")
    relationships.add_argument("--page", type=int)
    relationships.add_argument("--page-size", type=int, default=24)

    demo = sub.add_parser("marketplace-demo", help="Print high-quality output-ready examples for marketplaces.")
    add_output_options(demo)

    self_check = sub.add_parser("self-check", help="Run local package checks before release.")
    add_output_options(self_check)

    metadata = sub.add_parser("metadata", help="Show skill API metadata and runtime usage snapshot.")
    add_output_options(metadata)

    recommend = sub.add_parser("recommend", help="Run SchoolFit recommendation buckets.")
    add_output_options(recommend)
    recommend.add_argument("--input-json", help="Recommendation input JSON object.")
    add_core_recommendation_filters(recommend)
    add_recommendation_filters(recommend)

    vacancies = sub.add_parser("vacancies", help="Query EDB vacancy records exposed by SchoolFit.")
    add_output_options(vacancies)
    vacancies.add_argument("--school-id")
    vacancies.add_argument("--district")
    vacancies.add_argument("--grade", choices=["S1", "S2", "S3", "S4", "S5", "S6"])
    vacancies.add_argument("--status")
    vacancies.add_argument("--source-type")
    vacancies.add_argument("--has-vacancy", nargs="?", const="true", type=as_bool)
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
    parser.add_argument("--skill-code", default=argparse.SUPPRESS, help="SchoolFit Skill activation code.")
    parser.add_argument("--brief-level", choices=["full", "compact"], default="full")
    parser.add_argument("--routing-mode", choices=["auto", "precision", "broad"], default="auto")
    parser.add_argument("--fallback-empty", choices=["ignore", "broaden"], default="ignore")
    parser.add_argument("--audit-data", dest="audit_data", action="store_true", default=None)
    parser.add_argument("--no-audit-data", dest="audit_data", action="store_false")
    parser.add_argument("--boarding", action="store_true", help="Hint that user is looking for boarding-capable schools.")
    parser.add_argument("--verbose", action="store_true", help="Ask SchoolFit Skill APIs for raw vacancy/admission arrays and full source ledgers.")


def add_common_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--q")
    parser.add_argument("--level", choices=SCHOOL_LEVELS, help="School database level: secondary, primary, kindergarten, international, or postsecondary.")
    parser.add_argument("--district")
    parser.add_argument("--banding")
    parser.add_argument("--gender")
    parser.add_argument("--medium")
    parser.add_argument("--funding-type")
    parser.add_argument("--religion")
    parser.add_argument("--max-tuition", type=float)
    parser.add_argument("--vacancy-grade", choices=["S1", "S2", "S3", "S4", "S5", "S6"])
    parser.add_argument("--vacancy-status")
    parser.add_argument("--has-vacancy", nargs="?", const="true", type=as_bool)
    parser.add_argument("--page", type=int)
    parser.add_argument("--page-size", type=int, default=24)


def add_recommendation_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--application-goal")
    parser.add_argument("--language-priority")
    parser.add_argument("--support-needs", nargs="*")
    parser.add_argument("--accepts-dss", type=as_bool)
    parser.add_argument("--no-dss", dest="accepts_dss", action="store_false", help="Shortcut for --accepts-dss false.")
    parser.add_argument("--commute-minutes", type=float)
    parser.add_argument("--personality")
    parser.add_argument("--priorities", nargs="*")
    parser.add_argument("--notes")


def add_core_recommendation_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--level", choices=SCHOOL_LEVELS)
    parser.add_argument("--district")
    parser.add_argument("--banding")
    parser.add_argument("--gender")
    parser.add_argument("--medium")
    parser.add_argument("--max-tuition", type=float)


def school_search_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "q": args.q,
        "level": getattr(args, "level", None),
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
    }


def advisory_search_params(args: argparse.Namespace) -> dict[str, Any]:
    q = getattr(args, "q", None)
    has_boarding = False
    enriched_q = q
    if isinstance(q, str):
        normalized_q = q.lower()
        if "boarding" in normalized_q or "寄宿" in q or "寄宿制" in q:
            has_boarding = True
            if "boarding" not in normalized_q:
                enriched_q = f"{q} boarding"

    if getattr(args, "boarding", False):
        has_boarding = True
        if isinstance(enriched_q, str) and "boarding" not in enriched_q.lower():
            enriched_q = f"{enriched_q} boarding"

    intent = getattr(args, "intent", "auto") or "auto"
    resolved_intent = infer_intent(args) if intent == "auto" else intent
    args.intent = resolved_intent

    raw_audit = getattr(args, "audit_data", None)
    audit_data = bool(raw_audit) if raw_audit is not None else resolved_intent in {"admissions", "vacancy"}

    return {
        **school_search_params(args),
        "q": enriched_q,
        "intent": resolved_intent,
        "routingMode": getattr(args, "routing_mode", None) or "auto",
        "priorities": args.priorities,
        "supportNeeds": args.support_needs,
        "applicationGoal": args.application_goal,
        "languagePriority": args.language_priority,
        "acceptsDss": args.accepts_dss,
        "commuteMinutes": args.commute_minutes,
        "personality": args.personality,
        "notes": args.notes,
        "noRecommend": getattr(args, "no_recommend", None),
        "includeDecisionBrief": getattr(args, "include_decision_brief", None),
        "hasBoarding": has_boarding,
        "auditData": audit_data,
        "verbose": True if getattr(args, "verbose", False) else None,
    }


def build_advisor_search_params(args: argparse.Namespace, *, routing_mode: str | None = None) -> dict[str, Any]:
    params = advisory_search_params(args)
    mode = (routing_mode or getattr(args, "routing_mode", "auto") or "auto").strip().lower()
    if mode == "broad":
        params["routingMode"] = "broad"
        params["banding"] = None
        params["fundingType"] = None
        params["gender"] = None
        params["vacancyGrade"] = None
        params["pageSize"] = 48
    elif mode == "precision":
        params["routingMode"] = "precision"
        params["pageSize"] = getattr(args, "page_size", None)
    else:
        params["routingMode"] = "auto"

    return params


def recommendation_body_from_args(args: argparse.Namespace) -> dict[str, Any]:
    body = read_json_arg(getattr(args, "input_json", None))
    body.update(clean_params({
        "level": getattr(args, "level", None),
        "district": getattr(args, "district", None),
        "banding": getattr(args, "banding", None),
        "gender": getattr(args, "gender", None),
        "medium": getattr(args, "medium", None),
        "applicationGoal": getattr(args, "application_goal", None),
        "languagePriority": getattr(args, "language_priority", None),
        "personality": getattr(args, "personality", None),
        "notes": getattr(args, "notes", None),
    }))
    if getattr(args, "support_needs", None):
        body["supportNeeds"] = args.support_needs
    if getattr(args, "priorities", None):
        body["priorities"] = args.priorities
    if getattr(args, "accepts_dss", None) is not None:
        body["acceptsDss"] = args.accepts_dss
    if getattr(args, "max_tuition", None) is not None:
        body["maxTuition"] = args.max_tuition
    if getattr(args, "commute_minutes", None) is not None:
        body["commuteMinutes"] = args.commute_minutes
    return body


def school_relationship_params(args: argparse.Namespace) -> dict[str, Any]:
    relationship_type = getattr(args, "type", None)
    if relationship_type == "through-train":
        relationship_type = "through_train"
    return {
        "type": relationship_type,
        "q": getattr(args, "q", None),
        "district": getattr(args, "district", None),
        "matchedOnly": getattr(args, "matched_only", None),
        "page": getattr(args, "page", None),
        "pageSize": getattr(args, "page_size", None),
    }


def sanitize_student_profile(raw: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "banding",
        "district",
        "gender",
        "medium",
        "grade",
        "priorityOrder",
        "priorities",
        "supportNeeds",
        "acceptsDss",
        "maxTuition",
        "commuteMinutes",
        "applicationGoal",
        "languagePriority",
        "personality",
        "notes",
    }
    output: dict[str, Any] = {}
    for key, value in raw.items():
        if key in allowed:
            output[key] = value
    if "priorityOrder" in output:
        output["priorities"] = output.get("priorities") or output.pop("priorityOrder")
    return output


def should_recommend(args: argparse.Namespace) -> bool:
    if getattr(args, "no_recommend", False):
        return False
    signals = [
        getattr(args, "district", None),
        getattr(args, "banding", None),
        getattr(args, "gender", None),
        getattr(args, "medium", None),
        getattr(args, "max_tuition", None),
        getattr(args, "vacancy_grade", None),
        getattr(args, "application_goal", None),
        getattr(args, "language_priority", None),
        getattr(args, "support_needs", None),
        getattr(args, "accepts_dss", None),
        getattr(args, "commute_minutes", None),
        getattr(args, "personality", None),
        getattr(args, "priorities", None),
        getattr(args, "notes", None),
    ]
    return sum(1 for item in signals if item not in (None, [], "")) >= 2


def run(args: argparse.Namespace) -> dict[str, Any]:
    base_url = validate_base_url(args.base_url)
    command = args.command
    trace_id = next_trace_id()
    # For explicit search without a user code, surface activation guidance and
    # avoid a potentially noisy API probe on the public search entry point.
    use_client_code_fallback = command != "search-schools"
    skill_code = get_skill_code(args, allow_fallback=use_client_code_fallback)
    started_at = time.time()

    if command == "quick-start":
        return quick_start_output(trace_id)

    if command == "school-levels":
        return school_levels_output(trace_id)

    if command == "parse-parent-request":
        return parse_parent_request_text(getattr(args, "q", ""))

    if command == "self-check":
        return self_check_output()

    if command == "marketplace-demo":
        return attach_runtime_metadata(
            compact_output(command, marketplace_demo_payload()),
            activation_status="not_required",
            trace_id=trace_id,
            code=None,
        )

    if command == "activate":
        pasted = getattr(args, "code", None) or getattr(args, "text", None)
        pasted_code = extract_skill_code_from_text(pasted) or (pasted.strip() if isinstance(pasted, str) else None)
        skill_code = resolve_skill_code(pasted_code)
        activation_status = activate_skill_code(base_url, skill_code, trace_id)
        output = activation_result_output(skill_code, activation_status, trace_id)
        record_telemetry(
            base_url,
            command=command,
            status="success" if output.get("activated") else "failed",
            trace_id=trace_id,
            skill_code=skill_code,
            activation_status=activation_status,
            latency_ms=int((time.time() - started_at) * 1000),
            error_code=None if output.get("activated") else "activation_failed",
        )
        return output

    if command == "setup-code":
        setup_code = getattr(args, "code", None)
        if not setup_code:
            raise SchoolFitError("setup-code requires --code.")
        normalized_code = extract_skill_code_from_text(setup_code) or setup_code.strip()
        save_skill_code(normalized_code)
        activation_status = activate_skill_code(base_url, normalized_code, trace_id)
        if activation_status == "active":
            mark_skill_code_activated(normalized_code, activation_status)
        config_path = os.environ.get(SCHOOLFIT_SKILL_CONFIG_PATH_ENV, DEFAULT_SKILL_CONFIG_PATH)
        return {
            "configPath": config_path,
            "activationStatus": activation_status,
            "activationResult": activation_result_output(normalized_code, activation_status, trace_id),
            "skillVersion": SKILL_VERSION,
            "traceId": trace_id,
            "command": "setup-code",
        }

    sensitive_findings = detect_sensitive_input(args)
    if sensitive_findings:
        return privacy_warning_output(command, trace_id, sensitive_findings)

    if command == "advisor-search":
        apply_parsed_request_to_args(args)
    if command == "shortlist-builder":
        apply_parsed_request_to_args(args)
    if command == "search-schools":
        apply_parsed_request_to_args(args)

    activation_status = activate_skill_code(base_url, skill_code, trace_id)
    if activation_status == "inactive":
        output = activation_required_output(command, trace_id, skill_code)
        record_telemetry(
            base_url,
            command=command,
            status="needs_activation",
            trace_id=trace_id,
            skill_code=skill_code,
            activation_status=activation_status,
            latency_ms=int((time.time() - started_at) * 1000),
            error_code="needs_activation",
        )
        return output

    def api(method: str, path: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> Any:
        return request_json(
            method,
            base_url,
            path,
            params=params,
            body=body,
            skill_code=skill_code,
            trace_id=trace_id,
            activation_status=activation_status,
        )

    payload: Any
    if command == "search-schools":
        payload = robust_school_search(api, args)
    elif command == "resolve-school":
        resolved_query = resolve_school_query(args.name)
        payload = api("GET", "/api/schools", params={
            "q": resolved_query,
            "level": getattr(args, "level", None),
            "district": args.district,
            "pageSize": args.page_size,
        })
        if isinstance(payload, dict):
            payload["query"] = args.name
            payload["resolvedQuery"] = resolved_query
    elif command == "shortlist-builder":
        parsed = parse_parent_request_text(getattr(args, "q", ""))
        payload = api("GET", "/api/skill/search-advisor", params={
            **school_search_params(args),
            "intent": "recommend",
            "priorities": args.priorities,
            "supportNeeds": args.support_needs,
            "applicationGoal": args.application_goal,
            "languagePriority": args.language_priority,
            "acceptsDss": args.accepts_dss,
            "commuteMinutes": args.commute_minutes,
            "personality": args.personality,
            "notes": args.notes,
            "noRecommend": True,
        })
        if isinstance(payload, dict):
            payload["query"] = getattr(args, "q", None)
            payload["missingInfoQuestions"] = parsed.get("missingInfoQuestions", [])
            payload["conversationHints"] = parsed.get("conversationHints", [])
            payload["parsedSignals"] = parsed.get("recommendationSignals", {})
            search_payload = payload.get("search") if isinstance(payload.get("search"), dict) else payload
            if not (search_payload or {}).get("schools"):
                original_q = getattr(args, "q", None)
                setattr(args, "q", None)
                fallback = robust_school_search(api, args, reason="empty_skill_advisor_search")
                setattr(args, "q", original_q)
                payload["search"] = fallback
                payload["fallbackUsed"] = "structured_filter_search"
    elif command == "advisor-search":
        payload = api("GET", "/api/skill/search-advisor", params=build_advisor_search_params(args))
        if isinstance(payload, dict) and args.fallback_empty == "broaden":
            search_payload = payload.get("search") if isinstance(payload.get("search"), dict) else {}
            if int((search_payload or {}).get("count", 0) or 0) == 0:
                payload = api("GET", "/api/skill/search-advisor", params=build_advisor_search_params(args, routing_mode="broad"))
        if isinstance(payload, dict):
            search_payload = payload.get("search") if isinstance(payload.get("search"), dict) else {}
            if should_run_robust_district_search(args, search_payload):
                fallback = api("GET", "/api/schools", params={
                    "level": getattr(args, "level", None),
                    "page": 1,
                    "pageSize": ROBUST_SEARCH_PAGE_SIZE,
                })
                payload["search"] = merge_school_payloads(search_payload, fallback, args, reason="advisor_search_district_guard")
                payload["fallbackUsed"] = "advisor_search_district_guard"
    elif command == "school-relationships":
        payload = api("GET", "/api/skill/school-relationships", params=school_relationship_params(args))
    elif command == "school-detail":
        slug = urllib.parse.quote(args.slug.strip(), safe="")
        payload = api("GET", f"/api/schools/{slug}")
    elif command == "compare":
        ids = normalize_csv_list(args.ids)[:MAX_COMPARE_IDS]
        if not ids:
            raise SchoolFitError("At least one school id/slug is required.")
        payload = api("GET", "/api/compare", params={"ids": ids})
    elif command == "deep-compare":
        ids = normalize_csv_list(args.ids)[:MAX_COMPARE_IDS]
        if not ids:
            raise SchoolFitError("At least one school id/slug is required.")
        compare_payload = api("GET", "/api/compare", params={"ids": ids})
        details: list[Any] = []
        if getattr(args, "include_detail", False):
            unique_ids: list[str] = []
            for school_id in ids:
                if school_id not in unique_ids:
                    unique_ids.append(school_id)
            detail_map: dict[str, Any] = {}
            for school_id in unique_ids:
                try:
                    detail_map[school_id] = api("GET", f"/api/schools/{urllib.parse.quote(school_id, safe='')}")
                except SchoolFitError:
                    continue
            for school_id in ids:
                details.append(detail_map.get(school_id, {}))
        payload = {
            "compare": compare_payload,
            "count": len(compare_payload.get("schools", []) if isinstance(compare_payload, dict) else ids),
            "comparison": {
                "summary": "Use compare data with SchoolFit HK official data and time-sensitive indicators.",
                "insights": "Review school fit by commute, budget, language and admission context.",
                "sourcesUsed": ["/api/compare", "/api/schools/{id}"] if getattr(args, "include_detail", False) else ["/api/compare"],
            },
            "details": details,
        }
    elif command == "recommend":
        payload = api("POST", "/api/agent/recommend", body=recommendation_body_from_args(args))
    elif command == "vacancies":
        payload = api("GET", "/api/vacancies", params={
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
        payload = api("GET", "/api/admission-notices", params={
            "schoolId": args.school_id,
            "grade": args.grade,
            "isActive": args.is_active,
            "confidence": args.confidence,
            "q": args.q,
            "page": args.page,
            "pageSize": args.page_size,
        })
    elif command in {"decision-brief", "school-report"}:
        slug = urllib.parse.quote(args.slug.strip(), safe="")
        school_decision_payload = api(
            "GET",
            f"/api/skill/schools/{slug}/decision-brief",
            params={"verbose": True if getattr(args, "verbose", False) else None},
        )
        student_profile = sanitize_student_profile(read_json_arg(getattr(args, "student_profile_json", None)))
        school_payload = (school_decision_payload or {}).get("school", {}) if isinstance(school_decision_payload, dict) else {}
        vacancy_payload = (school_decision_payload or {}).get("vacancy", {}) if isinstance(school_decision_payload, dict) else {}
        admissions_payload = (school_decision_payload or {}).get("admission", {}) if isinstance(school_decision_payload, dict) else {}
        payload = {
            "mode": (school_decision_payload or {}).get("mode") if isinstance(school_decision_payload, dict) else None,
            "school": {
                **school_payload,
                "vacancySummary": (vacancy_payload.get("summary") or {}),
                "admissionNoticeSummary": (admissions_payload.get("summary") or {}),
            },
            "vacancies": vacancy_payload or {},
            "admissions": admissions_payload or {},
            "sourceLedger": (school_decision_payload or {}).get("sourceLedger") if isinstance(school_decision_payload, dict) else None,
            "studentProfile": student_profile,
        }
    elif command == "application-plan":
        school_ids = normalize_csv_list(args.school_slugs)
        if not school_ids:
            raise SchoolFitError("At least one target school slug is required.")
        student_profile = sanitize_student_profile(read_json_arg(getattr(args, "student_profile_json", None)))
        payload = api(
            "GET",
            "/api/skill/application-plan",
            params={
                "schoolSlugs": ",".join(school_ids[:MAX_COMPARE_IDS]),
                "grade": getattr(args, "grade", "S1"),
                "studentProfile": json.dumps(student_profile, ensure_ascii=False) if student_profile else None,
                "deadlineWindowDays": args.deadline_window_days,
            }
        )
    elif command == "metadata":
        payload = api("GET", "/api/skill/metadata")
    elif command == "marketplace-demo":
        payload = marketplace_demo_payload()
    else:
        raise SchoolFitError(f"Unsupported command: {command}")
    output = attach_runtime_metadata(
        compact_output(command, payload),
        activation_status=activation_status,
        trace_id=trace_id,
        code=skill_code,
    )
    if command == "search-schools" and getattr(args, "brief_level", "full") == "compact":
        output["schools"] = (output.get("schools") or [])[:8]
    record_telemetry(
        base_url,
        command=command,
        status="success",
        trace_id=trace_id,
        skill_code=skill_code,
        activation_status=activation_status,
        latency_ms=int((time.time() - started_at) * 1000),
    )
    return output


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
