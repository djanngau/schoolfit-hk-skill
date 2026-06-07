# SchoolFit Audit Boundary

This file documents the security and product boundary for ClawHub review.

## Runtime Access

- The helper calls only `https://schoolfit.hk/api/...` and the session-code page at `https://schoolfit.hk/skill-code`.
- The default base URL is fixed to `https://schoolfit.hk`; custom schemes, embedded user-info, ports, and non-API paths are rejected by the helper.
- The skill does not read local databases, Prisma schemas, SQLite files, raw data snapshots, cookies, `.env` files, private project files, student files, or browser storage.
- The skill does not call `/api/agent/chat` in v1.

## Session Access Code

- The `sfhk_...` code is a SchoolFit session access code for trial API use and low-sensitive usage telemetry.
- It is not a password, school account login, student identity, or financial instrument.
- Agents should keep the code only in the active one-to-one chat context or the `SCHOOLFIT_SKILL_CODE` runtime environment variable for the current run.
- The full code must not be written to disk, logs, examples, issue trackers, commits, screenshots, marketplace submissions, or final answers.

## Privacy And Telemetry

- Telemetry records only command, endpoint, traceId, status/error, latency, activation status, skill version, and session-code hash prefix.
- Telemetry does not include the full session access code, raw parent question, student name, HKID, personal phone, address, report-card content, or private documents.
- Obvious HKID, personal phone, email, address, full student name, and document-content inputs are blocked before SchoolFit API calls.

## No Transactional Authority

- SchoolFit does not complete paid orders, tuition transactions, school applications, school-contact submissions, or enrollment commitments.
- Tuition and budget fields are search filters only.
- Vacancy and admissions data are time-sensitive leads, not guarantees.
- Application plans are checklists and reminders only; families must verify and submit directly through official school channels.

## Review Notes

- ClawHub may label the package as requiring sensitive setup because a session access code can be supplied. The code is deliberately scoped, non-transactional, and non-student-identifying.
- If ClawHub flags financial authority, the likely trigger is school tuition/budget wording. The skill never transfers funds or instructs agents to complete paid actions.
