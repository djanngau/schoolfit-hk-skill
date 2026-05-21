# SchoolFit HK Skill for OpenClaw (v1.0.0)

OpenClaw/CowAgent/Claude Code compatible skill for Hong Kong secondary-school selection using the public [SchoolFit HK](https://schoolfit.hk) API.

The skill wraps SchoolFit HK features for:

- smart advisor search with model-polishable briefs and intent routing
- school search and detail lookup
- school comparison
- Safe / Match / Reach recommendation buckets
- EDB vacancy records
- school admission notices
- deep compare
- single-school decision reports
- practical application planning output
- application plan with deadline reminders and parent checklist
- conservative source labeling and decision caveats

## Install

From ClawHub:

```text
/skill install clawhub:schoolfit-hk
ark skill install clawhub:schoolfit-hk
```

ClawHub listing: https://clawhub.ai/djanngau/schoolfit-hk

From GitHub:

```text
/skill install djanngau/schoolfit-hk-skill#skills/schoolfit-hk
cow skill install djanngau/schoolfit-hk-skill#skills/schoolfit-hk
```

## Safety Model

- Calls only `https://schoolfit.hk/api/...`.
- Does not read local Edu databases, Prisma files, raw data snapshots, cookies, or `.env` files.
- Rejects non-`schoolfit.hk` base URLs.
- First run asks the user to open `https://schoolfit.hk/skill-code`, generate a trial code, and pass it to the Agent.
- Sends `X-SchoolFit-Skill-Code`, `X-SchoolFit-Skill-Version`, and trace metadata for activation and anonymous telemetry. The code is not a payment token or student identity.
- Keeps official facts, third-party Band references, community summaries, vacancies, and admissions notices separate.

## Local Smoke Test

```bash
export SCHOOLFIT_SKILL_CODE="PASTE_CODE_FROM_https://schoolfit.hk/skill-code"
python3 skills/schoolfit-hk/scripts/schoolfit_api.py search-schools --q "沙田 Band 1 英文 男女校" --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py advisor-search --q "沙田 Band 1 英文 男女校" --district "沙田區" --banding "Band 1" --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py deep-compare sha-tin-methodist-college,ying-wa-girls-school --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py vacancies --grade S1 --has-vacancy true --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py school-report sha-tin-methodist-college --format markdown
python3 -m unittest discover -s tests
```

## Marketplace Summary

SchoolFit HK helps agents search, compare, and recommend Hong Kong secondary schools using schoolfit.hk public APIs, with conservative source labeling for official facts, Band references, EDB vacancy data, and admission notices.
