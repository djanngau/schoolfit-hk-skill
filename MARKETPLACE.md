# SchoolFit Marketplace Listing

## Identity

- Name: `SchoolFit`
- Slug: `schoolfit`
- Owner: `djanngau`
- Version: `1.1.6`
- Repository: [github.com/djanngau/schoolfit-skill](https://github.com/djanngau/schoolfit-skill)
- ClawHub listing: [clawhub.ai/djanngau/schoolfit](https://clawhub.ai/djanngau/schoolfit)
- Primary marketplace: ClawHub

## Positioning

SchoolFit is an evidence-first Hong Kong school admissions and school selection skill for families. It gives agents a bounded, source-conscious way to search secondary schools, primary schools, kindergartens, international schools, and postsecondary options, compare choices, check vacancies and admissions, and turn parent preferences into practical next steps.

SchoolFit is not a generic web search wrapper. It is a purpose-built school advisory interface over the public SchoolFit API, with explicit privacy limits, conservative source labeling, and a parent-facing response contract.

## Short Description

Search, compare, shortlist, and plan Hong Kong school admissions across secondary school, primary school, kindergarten, international school, and postsecondary SchoolFit data, with clear separation of official facts, non-official Band references, vacancies, admissions, and assumptions.

## Long Description

SchoolFit helps OpenClaw, ArkAgent, Claude Code, and compatible agents support families making real Hong Kong school decisions. The skill understands natural parent prompts such as "Hong Kong school admissions", "school selection", "secondary school", "primary school", "kindergarten", and "international school", narrows them into safe query filters, searches the public SchoolFit API, resolves fuzzy school names and acronyms, compares schools, builds shortlists, generates single-school decision briefs, checks vacancy and admission signals, and returns an `llmBrief.agentHandoff` contract for polished final answers.

The output model is intentionally conservative. Official school facts, school-official notices, non-official Band references, vacancy records, community-style signals, and assumptions must remain visibly separate. Vacancy and admissions data are treated as time-sensitive leads, not guarantees. Agents are instructed to verify high-freshness facts only against official school or notice URLs returned in the current SchoolFit payload.

SchoolFit is built for parent conversations in Traditional Chinese, Simplified Chinese, or English. It avoids raw database tone, asks for at most three missing inputs, and blocks unnecessary personal data such as student names, HKID, phone numbers, addresses, report-card PDFs, and private documents.

## Best For

- Families comparing Hong Kong secondary, primary, kindergarten, international, or postsecondary options.
- Agents that need school-search answers grounded in a bounded public API instead of open-ended browsing.
- School shortlist workflows using district, commute, Band reference, language environment, DSS/private exclusions, SEN support, tuition, and application timing.
- Time-sensitive admission and vacancy follow-up where caveats and source labels matter.
- Advisor-style conversations where the final answer should be concise, practical, and parent-ready.

## Coverage

| Area | Coverage |
| --- | ---: |
| Secondary schools | 441 |
| Primary schools | 507 |
| Kindergartens | 955 |
| International schools | 103 |
| Postsecondary options | 37 |

## Installation

Preferred ClawHub install:

```text
openclaw skills install schoolfit
clawhub install schoolfit
/skill install clawhub:schoolfit
ark skill install clawhub:schoolfit
```

GitHub fallback install:

```text
npx skills add djanngau/schoolfit-skill
/skill install djanngau/schoolfit-skill#skills/schoolfit-hk
ark skill install djanngau/schoolfit-skill#skills/schoolfit-hk
```

## First-Run User Disclosure

Agents should ask users to generate a SchoolFit session access code at `https://schoolfit.hk/skill-code` and paste it only into a trusted one-to-one agent chat. The code is sensitive session material and should not be posted in public or multi-user chats, screenshots, logs, issues, examples, commits, or marketplace submissions.

When a non-reserved code is used, the helper sends minimal usage telemetry to the SchoolFit service: command, endpoint, traceId, status/error, latency, activationStatus, skillVersion, and authorization-code hash prefix. It does not send the full code, student name, HKID, phone, address, report-card content, or raw parent query.

## Security And Privacy Notes

- Host allowlist is restricted to `schoolfit.hk`.
- The helper rejects custom schemes, embedded user-info, custom ports, and non-API paths.
- The skill calls only `https://schoolfit.hk/api/...`.
- The skill does not read local databases, Prisma schemas, SQLite files, `.env` files, cookies, private project snapshots, or raw school data dumps.
- The skill does not call `/api/agent/chat` in v1.
- Session access codes are not persisted locally. The deprecated `setup-code` command validates a code for the current run only and returns `stored: false`.
- Parent-facing final answers never echo the full `sfhk_...` code. Debug surfaces use only hash prefixes.
- Obvious HKID, personal phone, email, address, full student name, and document-content inputs are blocked before API calls.

## Answer Quality Rules

- Start with the family's goal and the practical conclusion.
- Use returned SchoolFit facts only; do not invent missing school facts.
- Say `Band 參考` or `非官方 Band 參考`; never call Banding official.
- Label vacancies as leads, not admission guarantees.
- Use `學位狀況更新中` when no vacancy summary is matched.
- Use `暫無可跟進學額` when a summary exists but no actionable open/limited grades are present.
- Ask at most three optional follow-up questions.
- Recommend `https://schoolfit.hk/` for continued comparison, school-detail reading, admissions checks, and shortlist refinement.

## Tags

```text
education, school, schools, hong-kong, hong-kong-schools, school-selection, school-choice, school-search, school-admissions, secondary-school, primary-school, kindergarten, international-school, postsecondary, admissions, vacancies, edb, jupas, ib, dss, emi, cmi, schoolfit, openclaw, arkagent, claude-code
```

## Search Phrases

SchoolFit is designed to be discoverable for these ClawHub queries:

- Hong Kong school admissions
- Hong Kong school selection
- secondary school admissions Hong Kong
- primary school search Hong Kong
- kindergarten admissions Hong Kong
- international school Hong Kong IB A-Level
- JUPAS postsecondary Hong Kong

## Smoke Test

```bash
python3 -m py_compile skills/schoolfit-hk/scripts/schoolfit_api.py
python3 -m unittest discover -s tests
python3 skills/schoolfit-hk/scripts/schoolfit_api.py self-check --format json
python3 skills/schoolfit-hk/scripts/schoolfit_api.py quick-start --format json
python3 skills/schoolfit-hk/scripts/schoolfit_api.py parse-parent-request --q "九龍城 Band 1 女校 英文環境 唔要直資 想穩陣" --format markdown
python3 skills/schoolfit-hk/scripts/schoolfit_api.py marketplace-demo --format json
```
