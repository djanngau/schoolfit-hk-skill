# Application Plan

User:

```text
這兩間學校想試，幫我做 45 天申請計劃。
```

Recommended helper call:

```bash
python3 scripts/schoolfit_api.py application-plan --skill-code "PASTE_CODE" --school-slugs sha-tin-methodist-college,ying-wa-girls-school --deadline-window-days 45 --format markdown
```

Answer style:

- Turn returned timeline into a practical family checklist.
- Include documents, deadline confirmation, interview preparation and school follow-up reminders.
- Do not ask for HKID, phone, address, full name or report-card PDF in the chat.
