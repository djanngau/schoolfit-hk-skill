# SchoolFit

Version: `1.3.0`

SchoolFit is an evidence-first Hong Kong school admissions and school selection skill for agent platforms. It helps OpenClaw, ArkAgent, Claude Code, and compatible agents answer secondary school, primary school, kindergarten, international school, and postsecondary family questions with bounded data access, conservative ranking, and clear source separation.

The skill is designed for real parent conversations, not database dumping. It turns natural-language questions into structured school searches, comparison briefs, shortlists, application plans, vacancy checks, and admissions follow-ups while keeping official facts, non-official Band references, time-limited notices, and assumptions visibly separate.

## What SchoolFit Does

- Searches secondary, primary, kindergarten, international, and postsecondary SchoolFit databases.
- Understands parent language such as district, commute, Band reference, EMI/CMI preference, DSS/private exclusions, SEN support, admissions, vacancies, yearly range, and application timing.
- Resolves fuzzy school names, Chinese/English names, and common acronyms before detail lookups.
- Builds parent-ready shortlists across `Reach`, `Match`, `Safe`, `首選`, `穩陣`, `備選`, and `暫不建議` buckets.
- Compares up to four schools by aggregating their current decision briefs, including practical differences, risks, and next steps.
- Produces compact single-school decision briefs and application plans.
- Checks EDB vacancy records, admissions notices, and primary-secondary relationship data when available.
- Refuses off-topic, model-probing, internal-data extraction, jailbreak, and deliberate token-wasting requests before making SchoolFit or model calls.

## Coverage

| Database | Current Coverage |
| --- | ---: |
| Secondary schools | 441 schools |
| Primary schools | 507 schools |
| Kindergartens | 955 schools |
| International schools | 103 schools |
| Postsecondary options | 37 institutions/options |

## Install

ClawHub is the canonical distribution channel.

```text
openclaw skills install schoolfit
clawhub install schoolfit
/skill install clawhub:schoolfit
ark skill install clawhub:schoolfit
```

ClawHub listing: [clawhub.ai/djanngau/schoolfit](https://clawhub.ai/djanngau/schoolfit)

GitHub direct install remains available for agents that need an exact repository path:

```text
/skill install djanngau/schoolfit-skill#skills/schoolfit-hk
ark skill install djanngau/schoolfit-skill#skills/schoolfit-hk
npx skills add djanngau/schoolfit-skill
```

## First Use

After installation, the agent should ask the family to create a SchoolFit session access code:

```text
請先打開 https://schoolfit.hk/skill-code 取得 SchoolFit 授權碼，複製後只發到這個你信任的一對一聊天窗口。這是一次性會話訪問碼，不要貼到公開或多人聊天，也不要截圖外傳或寫入日誌。完整授權碼不會出現在最終回答。
```

Before the first live query, disclose the usage boundary:

- The code is a trial session access code for SchoolFit API use, not a school account login or student identity.
- The helper sends only minimal usage telemetry for non-reserved codes: command, endpoint, traceId, status/error, latency, activationStatus, skillVersion, and authorization-code hash prefix.
- Telemetry does not include the full authorization code, student name, HKID, phone, address, report-card content, or raw parent query.
- The code must stay in active chat context or the current helper invocation. It must not be written to files, logs, examples, commits, marketplace listings, or final answers.
- Live commands with `--q` send school-search preference text to `https://schoolfit.hk/api/...` for that request. Remove student names, HKID, phone numbers, addresses, report-card details, and private document contents first.

Always show the authorization page as exactly `https://schoolfit.hk/skill-code`. If a copied link contains query strings, hash fragments, tracking parameters, or any suffix after `/skill-code`, normalize it back to the canonical URL.

## Agent Contract

SchoolFit responses are optimized for downstream AI models through `llmBrief.agentHandoff`. Agents should use that contract to produce concise, parent-facing answers:

- Start with what was understood and the practical conclusion.
- Use returned facts only; do not invent missing school facts.
- Keep official SchoolFit facts, school-official notices, non-official Band references, vacancy signals, and assumptions separate.
- Say `Band 參考` or `非官方 Band 參考`; never call Banding official.
- For vacancies, use the API display wording. Missing vacancy data is `學位狀況更新中`; no actionable open/limited grades is `暫無可跟進學額`.
- Treat vacancies and admissions as time-limited leads, not guarantees.
- Ask at most three optional follow-up questions.
- Never ask for student full name, HKID, phone, address, report-card PDFs, or private documents.
- For high-freshness facts, verify only against official school or notice URLs returned in the current SchoolFit payload. Do not use search engines, guessed domains, social media, maps, or broad web browsing.

## Current SchoolFit Workflow

The redesigned SchoolFit site is organized around `Today`, `Explore`, `Advisor`, and `Applications`. The former comparison workspace and `/api/compare` endpoint are retired. The compatibility commands `compare` and `deep-compare` remain available, but now aggregate current per-school decision briefs. Parent-facing next steps should open the returned school detail pages, save the schools worth keeping, and use [schoolfit.hk/applications](https://schoolfit.hk/applications) to add schools and track applications.

## Safety Boundary

SchoolFit is intentionally narrow.

- Calls only `https://schoolfit.hk/api/...`.
- Rejects non-`schoolfit.hk` base URLs, custom schemes, embedded user-info, custom ports, and non-API paths.
- Does not read runtime environment variables or local package files in the published runtime helper.
- Does not read local Edu databases, Prisma files, SQLite files, raw data snapshots, cookies, `.env` files, or private project keys.
- Does not call `/api/agent/chat` in v1, avoiding LLM usage and persistent session creation.
- Blocks obvious HKID, phone, and email input before API calls and asks the user to remove personal identifiers.
- Does not persist authorization codes locally. The deprecated `setup-code` command validates a code for the current run only and returns `stored: false`.
- Does not echo the full `sfhk_...` code in parent-facing answers. Debug surfaces use only hash prefixes.

## Data Architecture

The public SchoolFit API treats the live SchoolFit database as the canonical runtime store.

- Prisma/SQLite is the canonical store behind public API responses.
- Runtime snapshots and skill search indexes are DB-built read caches for search and fallback behavior.
- Lightweight list indexes support broad list, search, and sitemap-style scans.
- Full source JSON files are ingest, seed, and audit inputs only. This skill must not read or cite them as runtime facts.
- Redis, if introduced later, should remain optional cache, rate-limit, or queue infrastructure, not a primary data source.

## ClawHub Search Examples

SchoolFit is intended to match searches such as:

- `Hong Kong school admissions`
- `Hong Kong school selection`
- `secondary school admissions Hong Kong`
- `primary school search Hong Kong`
- `kindergarten admissions Hong Kong`
- `international school Hong Kong IB A-Level`

## CLI Examples

These commands are for agents, maintainers, and release testing. Families should only need to paste the `sfhk_...` code in chat.

```bash
python3 skills/schoolfit-hk/scripts/schoolfit_api.py quick-start --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py school-levels --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py activate "我的 SchoolFit 授權碼是 sfhk_xxxxxxxxxxxxxxxx" --format markdown

python3 skills/schoolfit-hk/scripts/schoolfit_api.py parse-parent-request --q "九龍城 Band 1 女校 英文環境 唔要直資 想穩陣" --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py advisor-search --skill-code "PASTE_CODE" --q "沙田 Band 1 英文 男女校，重視校風，不考慮直資" --district "沙田區" --banding "Band 1" --no-dss --include-decision-brief --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py resolve-school --name "SPCC" --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py shortlist-builder --q "沙田 Band 1 英文 男女校，想穩陣，不考慮直資" --no-dss --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py deep-compare sha-tin-methodist-college,ying-wa-girls-school --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py decision-brief sha-tin-methodist-college --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py application-plan --school-slugs sha-tin-methodist-college,ying-wa-girls-school --deadline-window-days 45 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py vacancies --grade S1 --has-vacancy true --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py admissions --grade S1 --is-active true --q "申請" --page-size 5 --format markdown
```

Use compact payloads by default. Add `--verbose` only when a maintainer explicitly needs raw vacancy/admission arrays, full source ledgers, or audit evidence.

## Release Checks

Run these before publishing a new ClawHub version:

```bash
python3 -m py_compile skills/schoolfit-hk/scripts/schoolfit_api.py
python3 -m unittest discover -s tests
python3 tools/schoolfit_release_check.py
python3 skills/schoolfit-hk/scripts/schoolfit_api.py quick-start --format json
git diff --check
```

Current distribution:

- Brand: `SchoolFit`
- ClawHub slug: `schoolfit`
- GitHub repository: [github.com/djanngau/schoolfit-skill](https://github.com/djanngau/schoolfit-skill)
- Primary marketplace: ClawHub
- Fallback discovery: skills.sh, then GitHub direct install
- Audit note: see [skills/schoolfit-hk/AUDIT.md](skills/schoolfit-hk/AUDIT.md)
