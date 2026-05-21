---
name: schoolfit-hk
description: Use when helping Hong Kong families search, compare, shortlist, or assess secondary schools with SchoolFit HK data, including admissions notices, EDB vacancy signals, Band references, and conservative school-selection advice.
version: 0.1.0
metadata: {"openclaw":{"homepage":"https://github.com/djanngau/schoolfit-hk-skill","skillKey":"schoolfit-hk","default_enabled":true,"requires":{"bins":["python3"]},"envVars":[{"name":"SCHOOLFIT_BASE_URL","required":false,"description":"Optional SchoolFit HK base URL. Must remain https://schoolfit.hk."}]}}
---

# SchoolFit HK

Keywords: SchoolFit HK, 啱校, 香港升中, 香港中學, OpenClaw skill, CowAgent skill, Claude Code skill, school selection, admissions, vacancies, Banding, Reach Match Safe, schoolfit.hk.

Use this skill to help families make conservative Hong Kong secondary-school decisions using the public SchoolFit HK API. The skill must not read local Edu project databases, Prisma files, snapshots, cookies, `.env` files, or private API keys.

## Data Boundary

- Only call `https://schoolfit.hk/api/...` through `scripts/schoolfit_api.py`.
- Do not query local Postgres, Prisma, SQLite, JSON snapshots, or the Edu source tree for user answers.
- Keep official facts, third-party Band references, public review summaries, vacancy data, and admission notices visibly separate.
- Never call `/api/agent/chat` in v1. It can consume LLM resources and create persistent sessions; it is reserved for a future paid/API-gated version.
- A reserved client code is sent as `X-SchoolFit-Skill-Code` by the helper. Treat it as a future billing hook, not as a secret.

## Quick Commands

Use `<base_dir>` as the directory that contains this `SKILL.md`.

Search schools:

```bash
python3 <base_dir>/scripts/schoolfit_api.py search-schools --q "沙田 Band 1 英文 男女校" --page-size 10 --format markdown
```

Get one school detail:

```bash
python3 <base_dir>/scripts/schoolfit_api.py school-detail st-paul-s-co-educational-college
```

Compare up to four schools:

```bash
python3 <base_dir>/scripts/schoolfit_api.py compare st-paul-s-co-educational-college,ying-wa-girls-school
```

Recommend a shortlist:

```bash
python3 <base_dir>/scripts/schoolfit_api.py recommend \
  --district "沙田區" \
  --banding "Band 1" \
  --gender "男女校" \
  --medium "英文" \
  --application-goal "升中自行分配" \
  --priorities "校風" "英文環境" "學額"
```

Query EDB vacancy records:

```bash
python3 <base_dir>/scripts/schoolfit_api.py vacancies --district "沙田區" --grade S1 --has-vacancy true --format markdown
```

Query admission notices:

```bash
python3 <base_dir>/scripts/schoolfit_api.py admissions --grade S1 --is-active true --q "申請" --format markdown
```

## Answering Rules

When presenting results:

- Start with a short conclusion, then list schools or options.
- For every school, prefer `nameZh`, `nameEn`, `district`, `gender`, `fundingType`, `mediumOfInstruction`, `bandingReference`, and `annualTuitionHkd` when present.
- Say `Band 參考` or `非官方 Band 參考`; never say `官方 Band`.
- For EDB vacancy data, include source, data month, last seen time, confidence, and this caveat: vacancy status is not an admission guarantee and families must confirm latest availability with the school.
- For admission notices, include source/fetched time, notice URL, active status, confidence, deadline if present, and remind families to check the original notice.
- If data is missing, say `暫無可靠資料`; do not invent facts.

## Supported Workflows

### School Search

Use `search-schools` when the user asks for schools by district, Band reference, gender, medium, funding type, tuition, religion, or vacancy status. Supported filters include:

- `--q`
- `--district`
- `--banding`
- `--gender`
- `--medium`
- `--funding-type`
- `--religion`
- `--max-tuition`
- `--vacancy-grade`
- `--vacancy-status`
- `--has-vacancy`

### School Detail

Use `school-detail` when the user names one school or provides a SchoolFit slug. If the user only gives a Chinese or English name, search first, then call detail on the best slug.

### Compare

Use `compare` when the user asks `A vs B`, `比較`, `對比`, or wants a shortlist decision. Compare at most four schools in one call.

### Recommendation

Use `recommend` when the user gives a student's profile or asks for Safe / Match / Reach options. Include as many known inputs as possible:

- `district`, `banding`, `gender`, `medium`
- `applicationGoal`, `languagePriority`
- `supportNeeds`, `acceptsDss`, `maxTuition`, `commuteMinutes`
- `personality`, `priorities`, `notes`

### Vacancies

Use `vacancies` for school-place availability, transfer, 插班, S1-S6 vacancy, 學額, or 學位 questions. Always keep the answer conservative.

### Admissions

Use `admissions` for application forms, deadlines, S1 admission, transfer admission, school notices, or application links.

## Error Handling

- Missing or no results: explain which filters were used and suggest one concrete relaxation.
- `404`: tell the user the school or endpoint was not found; search by name if appropriate.
- `429` or `5xx`: report the temporary service issue and retry later; do not expose headers or stack traces.
- Any non-SchoolFit base URL: stop. The helper intentionally rejects it for safety.

## Publishing

Install examples after GitHub publication:

```text
/skill install djanngau/schoolfit-hk-skill#skills/schoolfit-hk
cow skill install djanngau/schoolfit-hk-skill#skills/schoolfit-hk
```

Marketplace summary:

```text
SchoolFit HK helps agents search, compare, and recommend Hong Kong secondary schools using schoolfit.hk public APIs, with conservative source labeling for official facts, Band references, EDB vacancy data, and admission notices.
```
