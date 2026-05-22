# Advisor Search

User:

```text
幫我找沙田 Band 1 英文男女校，最好有學額，想穩陣。
```

Recommended helper flow:

```bash
python3 scripts/schoolfit_api.py parse-parent-request --q "幫我找沙田 Band 1 英文男女校，最好有學額，想穩陣。" --format markdown
python3 scripts/schoolfit_api.py advisor-search --skill-code "PASTE_CODE" --q "幫我找沙田 Band 1 英文男女校，最好有學額，想穩陣。" --format markdown
```

Answer style:

- Start with 3-6 schools to look at first.
- Include SchoolFit links returned by the API.
- Say `Band 參考`, not official Band.
- Keep vacancy/admission caveats visible.
