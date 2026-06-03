# Advisor Search

User:

```text
幫我找沙田 Band 1 英文男女校，最好有學額，想穩陣，不考慮直資，最重視校風。
```

Recommended helper flow:

```bash
python3 scripts/schoolfit_api.py parse-parent-request --q "幫我找沙田 Band 1 英文男女校，最好有學額，想穩陣，不考慮直資，最重視校風。" --format markdown
python3 scripts/schoolfit_api.py advisor-search --skill-code "PASTE_CODE" --q "幫我找沙田 Band 1 英文男女校，最好有學額，想穩陣，不考慮直資，最重視校風。" --intent recommend --no-dss --include-decision-brief --page-size 5 --format markdown
```

Answer style:

- Start with 3-6 schools to look at first.
- Preserve the user's constraints from `parentQuestion`; do not re-add DSS schools after `--no-dss`.
- Use `llmBrief.answerBlueprint` when present for the answer order, but keep caveats visible.
- Include SchoolFit links returned by the API.
- Say `Band 參考`, not official Band.
- Keep vacancy/admission caveats visible.
- If a result includes `decisionBriefApiUrl`, offer a one-school deep dive with `decision-brief` before making a final application plan.
- Mention source categories from `sourceLedger` when citing admissions, vacancy, or third-party Band signals.
