# SchoolFit HK Skill for OpenClaw

OpenClaw/CowAgent/Claude Code compatible skill for Hong Kong secondary-school selection using the public [SchoolFit HK](https://schoolfit.hk) API.

The skill wraps SchoolFit HK features for:

- school search and detail lookup
- school comparison
- Safe / Match / Reach recommendation buckets
- EDB vacancy records
- school admission notices
- conservative source labeling and decision caveats

## Install

After this repo is published to GitHub:

```text
/skill install djanngau/schoolfit-hk-skill#skills/schoolfit-hk
cow skill install djanngau/schoolfit-hk-skill#skills/schoolfit-hk
```

## Safety Model

- Calls only `https://schoolfit.hk/api/...`.
- Does not read local Edu databases, Prisma files, raw data snapshots, cookies, or `.env` files.
- Rejects non-`schoolfit.hk` base URLs.
- Sends a reserved `X-SchoolFit-Skill-Code` header for future paid API activation; this is not a secret in v1.
- Keeps official facts, third-party Band references, community summaries, vacancies, and admissions notices separate.

## Local Smoke Test

```bash
python3 skills/schoolfit-hk/scripts/schoolfit_api.py search-schools --q "沙田 Band 1 英文 男女校" --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py vacancies --grade S1 --has-vacancy true --page-size 5 --format markdown
python3 -m unittest discover -s tests
```

## Marketplace Summary

SchoolFit HK helps agents search, compare, and recommend Hong Kong secondary schools using schoolfit.hk public APIs, with conservative source labeling for official facts, Band references, EDB vacancy data, and admission notices.
