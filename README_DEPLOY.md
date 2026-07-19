# SchoolFit Release Notes

This repository is a SchoolFit skill package. It is not deployed through the
shared ARK server/Docker flow.

Release path:

- Commit and push this repository to GitHub.
- Create a GitHub Release for every public publish. Do not run standalone
  tag-only publishing.
- Publish or verify the matching `schoolfit` package version in ClawHub.
- Keep the GitHub Release version and ClawHub version aligned. The current
  redesigned-product compatibility release is `1.3.0`, then increments from there.
- Use skills.sh and direct GitHub install only as fallback discovery paths.
- Do not add server `.env`, GHCR, `ops/deploy.sh`, or container healthcheck
  requirements here unless the project is explicitly converted into a service.
- Treat ClawHub security acceptance as part of the release design. Avoid adding
  local file/env reads, broad permissions, hidden install behavior, packaged
  maintenance commands, credential-heavy wording, or purchase/admissions
  authority claims to the published skill package.

Pre-release checks:

```bash
python3 -m py_compile skills/schoolfit-hk/scripts/schoolfit_api.py
python3 -m unittest discover -s tests
python3 tools/schoolfit_release_check.py
python3 skills/schoolfit-hk/scripts/schoolfit_api.py quick-start --format json
python3 skills/schoolfit-hk/scripts/schoolfit_api.py metadata --skill-code schoolfit-openclaw-v1-reserved --format json
python3 skills/schoolfit-hk/scripts/schoolfit_api.py advisor-search --skill-code schoolfit-openclaw-v1-reserved --q "沙田 Band 1 英文 男女校，重視校風，不考慮直資" --intent recommend --no-dss --include-decision-brief --page-size 5 --format json
python3 skills/schoolfit-hk/scripts/schoolfit_api.py decision-brief sha-tin-methodist-college --skill-code schoolfit-openclaw-v1-reserved --format json
python3 skills/schoolfit-hk/scripts/schoolfit_api.py deep-compare sha-tin-methodist-college,ying-wa-girls-school --skill-code schoolfit-openclaw-v1-reserved --include-detail --format json
git diff --check
```

Release readiness:

- Confirm `tools/schoolfit_release_check.py` passes and the version in
  `skills/schoolfit-hk/SKILL.md` matches the helper constants, `README.md`, and
  `MARKETPLACE.md`.
- Confirm `quick-start` returns the canonical activation URL
  `https://schoolfit.hk/skill-code` and a policy that strips query strings, hash
  fragments, tracking text, and accidental suffixes.
- Confirm the ClawHub package excludes `examples/`, contains only the intended
  runtime files, and keeps `scripts/schoolfit_api.py` small enough for raw-file
  inspection.
- Confirm live `advisor-search` can return `parentQuestion`,
  `llmBrief.answerBlueprint`, `sourceLedger`, and decision-brief links when the
  SchoolFit service exposes them.
- Confirm `decision-brief` works for a known slug before publishing updated
  examples or marketplace text.
- Confirm `compare` and `deep-compare` aggregate current decision briefs and do
  not call the retired `/api/compare` endpoint.
- After publish, confirm ClawHub `inspect`, the security audit page, SkillSpector,
  VirusTotal, and LLM scanner are clean or explicitly document any remaining
  platform-side pending state.

Live coordination:

- If auth-code generation fails on `https://schoolfit.hk/skill-code`, debug the
  SchoolFit/Edu service-side SQLite storage and permissions, not this package
  first.
- If ARKAgent opens the skill but chat returns provider credential errors such
  as `auth header format should be Bearer sk-...`, fix the live model/provider
  configuration before republishing the skill package.
