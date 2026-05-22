# Shortlist Builder

User:

```text
沙田 Band 1 英文男女校，幫我分首選、穩陣、備選。
```

Recommended helper call:

```bash
python3 scripts/schoolfit_api.py shortlist-builder --skill-code "PASTE_CODE" --q "沙田 Band 1 英文 男女校，想穩陣" --format markdown
```

Answer style:

- Present `首選`, `穩陣`, `備選`, and `暫不建議` buckets.
- Use `rankingRationale` as explanation, not as official ranking.
- Ask at most three missing-info questions when the request is too broad.
