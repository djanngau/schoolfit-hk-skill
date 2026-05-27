# SchoolFitSkill Release Notes

This repository is a SchoolFit HK skill package. It is not deployed through the
shared ARK server/Docker flow.

Release path:

- Commit and push this repository to GitHub.
- Publish or verify the `schoolfit-hk` package in ClawHub.
- Use skills.sh and direct GitHub install only as fallback discovery paths.
- Do not add server `.env`, GHCR, `ops/deploy.sh`, or container healthcheck
  requirements here unless the project is explicitly converted into a service.

Pre-release checks:

```bash
python3 -m py_compile skills/schoolfit-hk/scripts/schoolfit_api.py
python3 -m unittest discover -s tests
python3 skills/schoolfit-hk/scripts/schoolfit_api.py self-check --format json
python3 skills/schoolfit-hk/scripts/schoolfit_api.py metadata --skill-code schoolfit-openclaw-v1-reserved --format json
```

Live coordination:

- If auth-code generation fails on `https://schoolfit.hk/skill-code`, debug the
  SchoolFit/Edu service-side SQLite storage and permissions, not this package
  first.
- If ARKAgent opens the skill but chat returns provider credential errors such
  as `auth header format should be Bearer sk-...`, fix the live model/provider
  configuration before republishing the skill package.
