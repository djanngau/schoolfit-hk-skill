# Deep Compare

User:

```text
幫我比較 sha-tin-methodist-college 和 ying-wa-girls-school，哪間更適合 Band 1B 女生？
```

Recommended helper call:

```bash
python3 scripts/schoolfit_api.py deep-compare sha-tin-methodist-college,ying-wa-girls-school --skill-code "PASTE_CODE" --include-detail --format markdown
```

Answer style:

- Explain the main differences first.
- Separate school facts, third-party Band reference, admissions and vacancy signals.
- End with a short next-step checklist.
