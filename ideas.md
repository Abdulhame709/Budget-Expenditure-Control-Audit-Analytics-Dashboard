# Design direction — Audit Analytics & Budget Control System

## Ground truth
This is an existing professional internal-audit training dashboard. The existing Arabic RTL Bootstrap interface and its synthetic-data warning are the design source of truth; permanent hosting must preserve them rather than introduce a competing visual system.

## Design direction
- **Theme Name:** Evidence-first financial control console
- **Intro:** A restrained Arabic RTL operations dashboard that prioritizes audit traceability, readable KPI hierarchy, and clear risk signaling.
- **Probability:** 0.08

## Design dimensions
- **Design movement:** Enterprise utility UI with audit-document clarity.
- **Core principles:** Evidence before decoration; strong hierarchy; explicit permissions; visible synthetic-data boundary; responsive RTL layouts.
- **Color philosophy:** Preserve the existing Bootstrap primary blue, warning banner, danger/warning/success risk semantics, and neutral surfaces.
- **Layout paradigm:** Server-rendered Django pages with a global navigation shell, compact KPI cards, filterable data tables, and chart panels.
- **Signature elements:** Arabic RTL navigation, yellow synthetic-data notice, PostgreSQL health status, dashboard KPI cards, audit-test and exception traceability.
- **Interaction philosophy:** Predictable links and forms, explicit login gates, reversible review actions, and clear validation messages.
- **Animation:** Minimal; use Bootstrap behavior only where already present. No decorative motion.
- **Typography system:** Existing Bootstrap system sans-serif stack; preserve Arabic readability and tabular numeric alignment.
- **Brand essence:** Trustworthy, inspectable, training-safe financial control.
- **Brand voice:** Professional, direct, bilingual where technical audit terms benefit from English labels.
- **Wordmark/logo:** A flat shield containing audit bars and a check mark, used in the header and favicon.
- **Signature brand color:** Deep navy `#081e34` with teal `#14b8a6` and existing Bootstrap blue.

## Permanent deployment decisions
- Django 5.2 + Gunicorn server deployment.
- PostgreSQL remains mandatory; the production `DATABASE_URL` is supplied as a protected environment secret.
- HTTPS proxy compatibility remains enabled.
- Versioned/static assets are served by WhiteNoise; personalized/authenticated HTML and reports remain unshared and uncached.
