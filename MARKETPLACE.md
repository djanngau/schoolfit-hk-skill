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

SchoolFit HK helps OpenClaw, CowAgent, Claude Code, and compatible agents support Hong Kong secondary-school selection workflows. It can run smart advisor search with model-polishable briefs, search schools, inspect school details, compare shortlists, produce Safe / Match / Reach recommendation buckets, query EDB vacancy records, and retrieve school admission notices.

The skill uses only the public `https://schoolfit.hk/api/...` surface. It does not read local databases, Prisma schemas, `.env` files, cookies, private Edu project snapshots, or raw school data dumps.

## Tags

```text
education, hong-kong, school-selection, secondary-school, admissions, vacancies, schoolfit, openclaw, cowagent, claude-code
```

## Security Notes

- Host allowlist is restricted to `schoolfit.hk`.
- The helper rejects custom schemes, credentials, custom ports, and non-API paths.
- The reserved `X-SchoolFit-Skill-Code` header is a future billing hook, not a secret.
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
- Version: `0.1.1`
- Moderation: `CLEAN`

## Smoke Test

```bash
python3 skills/schoolfit-hk/scripts/schoolfit_api.py search-schools --q "沙田 Band 1 英文 男女校" --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py advisor-search --q "沙田 Band 1 英文 男女校" --district "沙田區" --banding "Band 1" --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py vacancies --grade S1 --has-vacancy true --page-size 5 --format markdown
python3 -m unittest discover -s tests
```
