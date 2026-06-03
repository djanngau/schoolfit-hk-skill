# SchoolFit HK Skill for OpenClaw (v1.0.14)

OpenClaw / ArkAgent / Claude Code compatible skill for Hong Kong secondary-school selection using the public [SchoolFit HK](https://schoolfit.hk) API.

The skill wraps SchoolFit HK features for:

- smart advisor search with model-polishable briefs and intent routing
- parent-query understanding with answer blueprints from the live Skill API
- school search and detail lookup
- school comparison
- compact single-school decision briefs
- Safe / Match / Reach recommendation buckets
- EDB vacancy records
- school admission notices
- deep compare
- single-school decision reports through the SchoolFit decision-brief API
- practical application planning output
- application plan with deadline reminders and parent checklist
- fuzzy school-name resolution
- shortlist buckets for 首選 / 穩陣 / 備選 / 暫不建議
- stricter English-environment sorting and district/nearby-district ranking
- robust district fallback search for API full-text/filter under-return cases
- local package self-check
- conservative source labeling and decision caveats
- Traditional Chinese, Simplified Chinese, and English parent prompts, with final answers matched to the user's language

## Install

Default marketplace: ClawHub. Use skills.sh only as a secondary cross-agent index, and direct GitHub install as the final fallback.

From ClawHub:

```text
openclaw skills install schoolfit-hk
clawhub install schoolfit-hk
/skill install clawhub:schoolfit-hk
ark skill install clawhub:schoolfit-hk
```

ClawHub listing: https://clawhub.ai/djanngau/schoolfit-hk

From skills.sh discovery:

```text
npx skills add djanngau/schoolfit-hk-skill
```

From GitHub:

```text
/skill install djanngau/schoolfit-hk-skill#skills/schoolfit-hk
ark skill install djanngau/schoolfit-hk-skill#skills/schoolfit-hk
```

## 30-Second Quick Start

After installation, the Agent should first say:

```text
請先打開 https://schoolfit.hk/skill-code 取得 SchoolFit 授權碼，複製後直接發到這個聊天窗口。我收到後就可以幫你查學校、比較、做推薦和申請計劃。
```

When the user pastes `sfhk_...`, the Agent keeps that code only in the active chat context and passes it to future helper calls as `--skill-code`. Do not write real user codes to files, logs, examples, commits, or marketplace material.

Always show the authorization page as exactly `https://schoolfit.hk/skill-code`. If a copied link has `?`, `#`, tracking strings, or any path suffix after `/skill-code`, strip it back to the canonical URL before opening.

## Safety Model

- Calls only `https://schoolfit.hk/api/...`.
- Does not read local Edu databases, Prisma files, raw data snapshots, cookies, or `.env` files.
- Rejects non-`schoolfit.hk` base URLs.
- First run asks the user to open `https://schoolfit.hk/skill-code`, generate a trial code, copy it, and paste it back into the same chat window for the Agent.
- Authorization-link handling is strict: only `https://schoolfit.hk/skill-code` is canonical; decorated links should be cleaned before use.
- Sends `X-SchoolFit-Skill-Code`, `X-SchoolFit-Skill-Version`, and trace metadata for activation and anonymous telemetry. The code is not a payment token or student identity.
- Keeps official facts, third-party Band references, community summaries, vacancies, and admissions notices separate.
- Blocks obvious HKID, phone, and email input before API calls, and asks the user to remove sensitive data.

## Marketplace Policy

- ClawHub is the preferred registry for OpenClaw-native discovery, install, inspect, versioning, moderation, and release checks.
- The project should not label its default market as SkillHub or `skillhub`.
- Fallback order is ClawHub, then skills.sh, then GitHub direct search/install.
- skills.sh is useful for broader Agent ecosystem discovery, but its API is authenticated and GitHub-index oriented, so it should not replace ClawHub as the OpenClaw default.
- GitHub direct install remains available for exact-path installs and source review.

## Local Smoke Test

```bash
export SCHOOLFIT_SKILL_CODE="PASTE_CODE_FROM_https://schoolfit.hk/skill-code"
python3 skills/schoolfit-hk/scripts/schoolfit_api.py quick-start --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py parse-parent-request --q "九龍城 Band 1 女校 英文環境 唔要直資 想穩陣" --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py self-check --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py search-schools --q "沙田 Band 1 英文 男女校" --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py resolve-school --name "SPCC" --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py shortlist-builder --q "沙田 Band 1 英文 男女校，想穩陣" --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py advisor-search --q "沙田 Band 1 英文 男女校，重視校風，不考慮直資" --district "沙田區" --banding "Band 1" --no-dss --include-decision-brief --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py deep-compare sha-tin-methodist-college,ying-wa-girls-school --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py decision-brief sha-tin-methodist-college --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py vacancies --grade S1 --has-vacancy true --page-size 5 --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py school-report sha-tin-methodist-college --format markdown
python3 -m unittest discover -s tests
```

Use compact Skill API payloads by default. Add `--verbose` only when a tester or agent explicitly needs raw vacancy/admission arrays, full source ledgers, or audit evidence.

For parent advisory flows, preserve `parentQuestion` and `llmBrief.answerBlueprint` from `advisor-search`; they are the live API's current understanding of the family's priorities, missing information and recommended answer shape.

## Marketplace Summary

SchoolFit HK helps agents search, compare, and recommend Hong Kong secondary schools using schoolfit.hk public APIs, with conservative source labeling for official facts, Band references, EDB vacancy data, and admission notices.
