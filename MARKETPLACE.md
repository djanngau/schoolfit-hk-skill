# Marketplace Submission Notes

## Skill Name

SchoolFit HK

## Repository

https://github.com/djanngau/schoolfit-hk-skill

## ClawHub Listing

https://clawhub.ai/djanngau/schoolfit-hk

## Install Path

```text
djanngau/schoolfit-hk-skill#skills/schoolfit-hk
```

## Short Description

Search, compare, and recommend Hong Kong secondary schools using SchoolFit HK public APIs, with conservative source labeling for official facts, Band references, EDB vacancy data, and admission notices.

## Long Description

SchoolFit HK helps OpenClaw, CowAgent, Claude Code, and compatible agents support Hong Kong secondary-school selection workflows. It can run smart advisor search with intent-aware routing, search schools, resolve fuzzy school names, inspect school details, compare shortlists, deep-compare, produce Safe / Match / Reach recommendation buckets, generate首選/穩陣/備選 shortlist buckets, generate single-school reports, build practical application plans, and retrieve EDB vacancy records/admission notices.

The skill uses only the public `https://schoolfit.hk/api/...` surface. It does not read local databases, Prisma schemas, `.env` files, cookies, private Edu project snapshots, or raw school data dumps.

## Tags

```text
education, hong-kong, school-selection, secondary-school, admissions, vacancies, schoolfit, openclaw, cowagent, claude-code
```

## Security Notes

- Host allowlist is restricted to `schoolfit.hk`.
- The helper rejects custom schemes, credentials, custom ports, and non-API paths.
- First use guides the user to `https://schoolfit.hk/skill-code` to generate a trial activation code, then paste it back into the same chat window for the Agent.
- The `X-SchoolFit-Skill-Code` header supports activation, rate limiting and anonymous telemetry; it is not a payment token or student identity.
- The v1 skill does not call `/api/agent/chat` to avoid LLM cost and persistent session creation.
- The skill keeps official facts, third-party Band references, community summaries, vacancy signals, and admission notices separated.

## Suggested Marketplace Commands

```text
/skill install clawhub:schoolfit-hk
ark skill install clawhub:schoolfit-hk
/skill install djanngau/schoolfit-hk-skill#skills/schoolfit-hk
cow skill install djanngau/schoolfit-hk-skill#skills/schoolfit-hk
```

## ClawHub Release

- Slug: `schoolfit-hk`
- Owner: `djanngau`
- Version: `1.0.2`
- Moderation: `CLEAN`

## Smoke Test

```bash
export SCHOOLFIT_SKILL_CODE="PASTE_CODE_FROM_https://schoolfit.hk/skill-code"
python3 skills/schoolfit-hk/scripts/schoolfit_api.py quick-start --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py parse-parent-request --q "九龍城 Band 1 女校 英文環境 唔要直資 想穩陣" --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py self-check --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py search-schools --q "沙田 Band 1 英文 男女校" --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py resolve-school --name "SPCC" --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py shortlist-builder --q "沙田 Band 1 英文 男女校，想穩陣" --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py advisor-search --q "沙田 Band 1 英文 男女校" --district "沙田區" --banding "Band 1" --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py deep-compare sha-tin-methodist-college,ying-wa-girls-school --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py vacancies --grade S1 --has-vacancy true --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py school-report sha-tin-methodist-college --format markdown
python3 -m unittest discover -s tests
```
