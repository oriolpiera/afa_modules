# Add a CSV/Excel family load assistant

## Why
An AFA has no way to perform an initial load of families (guardians plus students with a course) together with their contact and banking data. Odoo's native CSV/Excel import cannot create `afa.family`, because `create()` requires the billing guardian to be an unassigned guardian and links it only after the family exists. Role and course rules add further ordering constraints that a flat import cannot satisfy.

## What changes
- Introduce `afa_family_import`, depending on `afa_family`, `afa_school_course` and `afa_sepa`. A family-manager-only wizard accepts a CSV/Excel file with one person per row, grouped by family.
- Load order per family: billing guardian (unassigned guardian) → `afa.family` → remaining guardians and students (`afa_course_id`) → `res.partner.bank` (IBAN) → `account.banking.mandate` SEPA Core recurrent mandate.
- Validate and preview before writing anything, following the existing promotion/SEPA wizard pattern. Confirm creates each family inside a savepoint; a failing family rolls back on its own and is reported, without discarding other families.
- A family whose name already exists (including archived ones) is skipped and reported, so re-running a load is safe.
- Provide a downloadable CSV template, a Compose/CI wiring entry and addon documentation.

## Scope and risk
This is an additive assistant. It does not modify family identity, role or billing rules, the course ladder, or existing SEPA collection logic. Existing partners are never duplicated or merged; the wizard only creates new families. Course records must already exist, because the ladder owns course identity. Whether the `odoo:19.0` image ships `openpyxl` for `.xlsx` is verified during implementation; without it the wizard reports a clear message and supports CSV only. The ODD recovery checklist is at `odd/tasks/afa-family-import-issue-24.md`.
