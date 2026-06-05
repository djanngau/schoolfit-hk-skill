# Marketplace Submission Notes

## Skill Name

SchoolFit HK

## Repository

https://github.com/djanngau/schoolfit-hk-skill

## ClawHub Listing

https://clawhub.ai/djanngau/schoolfit-hk

## Marketplace Priority

Primary marketplace: ClawHub.

Fallback order:

1. ClawHub for OpenClaw-native discovery, install, inspect, versioning, moderation, and release verification.
2. skills.sh for broader cross-agent/GitHub-indexed discovery.
3. GitHub direct search or exact-path install.

Do not describe the default SchoolFit HK skill marketplace as SkillHub or `skillhub`. If a UI or agent needs a generic label, use "Skill marketplace" while resolving this project through ClawHub first.

## Install Path

```text
djanngau/schoolfit-hk-skill#skills/schoolfit-hk
```

## Short Description

Search, compare, and recommend Hong Kong schools across secondary, primary, kindergarten, international, and postsecondary SchoolFit HK public APIs, with conservative source labeling for official facts, Band references where applicable, vacancy data, and admission notices.

## Long Description

SchoolFit HK helps OpenClaw, CowAgent, Claude Code, and compatible agents support Hong Kong school-selection workflows across 中學資料庫, 小學資料庫, 幼稚園資料庫, 國際學校資料庫, and 專上教育庫. It can run smart advisor search with intent-aware routing, live parent-query understanding, answer blueprints, robust district fallback search, resolve fuzzy school names and Hong Kong school acronyms, inspect school details, compare shortlists, deep-compare, produce Safe / Match / Reach recommendation buckets where applicable, generate 首選/穩陣/備選 shortlist buckets with stricter English-environment and district ranking, generate compact single-school decision briefs, build practical application plans, retrieve vacancy records/admission notices, and handle Traditional Chinese, Simplified Chinese, or English parent prompts while matching the answer language.

The skill uses only the public `https://schoolfit.hk/api/...` surface. It does not read local databases, Prisma schemas, `.env` files, cookies, private Edu project snapshots, or raw school data dumps.

## Tags

```text
education, hong-kong, school-selection, secondary-school, primary-school, kindergarten, international-school, postsecondary, admissions, vacancies, schoolfit, openclaw, arkagent, claude-code
```

## Security Notes

- Host allowlist is restricted to `schoolfit.hk`.
- The helper rejects custom schemes, credentials, custom ports, and non-API paths.
- First use guides the user to `https://schoolfit.hk/skill-code` to generate a trial activation code, then paste it back into the same chat window for the Agent.
- Authorization page links must be normalized to exactly `https://schoolfit.hk/skill-code`; strip query strings, hash fragments, tracking strings, and path suffixes before opening.
- The `X-SchoolFit-Skill-Code` header supports activation, rate limiting and anonymous telemetry; it is not a payment token or student identity.
- The v1 skill does not call `/api/agent/chat` to avoid LLM cost and persistent session creation.
- The skill keeps official facts, third-party Band references where applicable, community summaries, vacancy signals, and admission notices separated.

## Suggested Marketplace Commands

```text
openclaw skills install schoolfit-hk
clawhub install schoolfit-hk
/skill install clawhub:schoolfit-hk
ark skill install clawhub:schoolfit-hk
npx skills add djanngau/schoolfit-hk-skill
/skill install djanngau/schoolfit-hk-skill#skills/schoolfit-hk
ark skill install djanngau/schoolfit-hk-skill#skills/schoolfit-hk
```

## ClawHub Release

- Slug: `schoolfit-hk`
- Owner: `djanngau`
- Version: `1.0.17`
- Moderation: `CLEAN`

## Smoke Test

```bash
export SCHOOLFIT_SKILL_CODE="PASTE_CODE_FROM_https://schoolfit.hk/skill-code"
python3 skills/schoolfit-hk/scripts/schoolfit_api.py quick-start --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py school-levels --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py parse-parent-request --q "九龍城 Band 1 女校 英文環境 唔要直資 想穩陣" --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py self-check --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py search-schools --level secondary --q "沙田 Band 1 英文 男女校" --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py search-schools --level primary --q "九龍城 小學 英文環境" --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py advisor-search --level international --q "港島 國際學校 IB A-Level" --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py advisor-search --level postsecondary --q "JUPAS HD 副學士 銜接" --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py resolve-school --name "SPCC" --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py shortlist-builder --q "沙田 Band 1 英文 男女校，想穩陣" --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py advisor-search --q "沙田 Band 1 英文 男女校，重視校風，不考慮直資" --district "沙田區" --banding "Band 1" --no-dss --include-decision-brief --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py deep-compare sha-tin-methodist-college,ying-wa-girls-school --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py decision-brief sha-tin-methodist-college --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py vacancies --grade S1 --has-vacancy true --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py school-report sha-tin-methodist-college --format markdown
python3 -m unittest discover -s tests
```
