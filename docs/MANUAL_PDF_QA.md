# Manual PDF QA (client-style, no e2e)

Walk through the **running Streamlit app** like a client: Reception → Analyst → Reviewer, download PDFs, verify letterhead/footer, then wipe dummy data.

## Automated alternative (run_tests.bat)

The same **backend services** as the app (not the Streamlit UI) run automatically when you execute **`run_tests.bat`** (with Docker Postgres + Word/LibreOffice):

- Tests: [`tests/integration/test_app_document_bundle.py`](../tests/integration/test_app_document_bundle.py)
- Output: [`tests/output_preview/app_flow/`](../tests/output_preview/app_flow/) — CTR, protocol, and final report for **food**, **water**, and **micro**
- Database: unique dummy GST per run; data deleted after each category test

Use manual steps below only when you need to verify the **browser UI** (login, widgets, download buttons).

---

## Prerequisites (manual run)

| Requirement | Why |
|-------------|-----|
| `docker compose up -d` | PostgreSQL |
| **Microsoft Word** or **LibreOffice** | PDF export for CTR and protocol |
| Reception / Analyst / Reviewer users | Role-gated pages |
| Dummy GST e.g. `99MANUAL0001A1Z5` | For cleanup |

Start: **`run_app.bat`**

---

## Steps 1–3 (Reception CTR, Analyst protocol, Reviewer final report)

See checklist in project plan; verify Surendra letterhead on CTR (`CTR_template.docx`) and protocol (`protocol.docx`).

---

## Wipe dummy data (manual)

Use only **dummy GSTINs** (e.g. `99MANUAL…`). The wipe script refuses real client GST numbers.

```text
python scripts/wipe_customer_by_gst.py --gst 99MANUAL0001A1Z5
```

Allowed patterns: prefix `99MANUAL`, `99DB`, `99TEST`, or integration-style `99…1Z5`.

Integration tests use `cleanup_test_data` instead (pytest teardown, not this CLI).
