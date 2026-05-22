# Resolve School

User:

```text
SPCC 是哪間？幫我找 SchoolFit slug。
```

Recommended helper call:

```bash
python3 scripts/schoolfit_api.py resolve-school --skill-code "PASTE_CODE" --name "SPCC" --format markdown
```

Answer style:

- Show the top candidate slug and SchoolFit URL.
- If multiple candidates are returned, ask the parent to confirm district or full school name.
- Do not assume a fuzzy acronym is correct when candidates are ambiguous.
