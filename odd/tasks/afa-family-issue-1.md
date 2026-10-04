# Family, guardians and students (Issue #1)

## Objective and problem
Provide an Odoo 19 Community `afa_family` addon to keep a family distinct from its people and its billing contact, without using commercial `parent_id` as a family link.

## Authorized scope and decisions
- One family per student, confirmed by the product owner; each family may have multiple guardians and students.
- One designated guardian is billed for future invoices. Existing posted invoices retain their own recipient; this addon does not rewrite invoice records.
- New addon under `afa_family/`, with tests and relevant documentation in the same repository. Do not modify the separate Odoo 16 Compose stack.
- Target Odoo 19; a 19 runtime is required for installation and integration tests.

## Constraints and acceptance
- Never duplicate partner records to add a guardian/student to a family.
- Enforce payer membership and guardian role on family and partner edits, including reassignment.
- Protect minor/student records from users without family-management authorization, not just hide the menu.
- Family form/list, guardian/student sections and contextual partner access.

## Delivery
- Route: delegated direct, since this feature requires multiple non-trivial model, security, view and test files; preparation reading belongs to the writer.
- Forecast: approximately 500–750 authored changed lines excluding generated files; use coherent work units and do not compress tests or documentation to meet a budget.
- Strategy: ask-on-risk. Branch point: `6fcefcd4a5ce026eb74ca5e2a51d3d11119eb3ed`.
- Running authored line count: at least 540 at `cddd53c`, plus existing commits `029ca43`, `92cb70a`, `43d5398`; review boundary pending. Demo/CI changes remain uncommitted.

## Tasks
- [x] FAM-1: Implement installable Odoo 19 family/partner domain and regression tests for billing, roles, one-family membership and invoice-recipient stability. Check: Odoo 19 addon loads; scoped tests run. Route: delegated direct. Commit: `cddd53c` (already present on branch); review: pending. Invoice recipient stability is limited to not changing existing references; no `account.move` integration is claimed.
- [x] FAM-2: Add family and partner UI plus ACL/record rules and authorization regression tests. Check: Odoo 19 addon loads; scoped tests run. Route: delegated direct. Commit: `cddd53c` (already present on branch); review: pending.
- [x] FAM-3: Run Odoo 19 in an isolated Compose stack, correct observed manager Contacts ACL failure and document repeatable focused test commands. Check: scoped Odoo 19 tests, Compose config, and HTTP readiness. Route: delegated test execution and bounded fix; commit: `029ca43` (already present); review: pending.
- [ ] FAM-4: Add fictitious demo family/partner records with distinct guardians and students and an Odoo regression test for payer membership, reuse and privacy. Check: install addon with demo data in a fresh Odoo 19 database and run focused tests. Route: delegated direct (manifest, demo data and tests); commit: pending; review: pending.
- [ ] FAM-5: Add a read-only GitHub Actions workflow that starts the existing Odoo 19 Compose test stack and runs the focused addon tests on pull requests and main pushes. Check: workflow syntax and local equivalent command; no remote workflow run unless published by the user. Route: delegated direct (workflow, documentation and runtime proof); commit: pending; review: pending.

## Progress and next step
- Product decision and Odoo target resolved. Existing FAM-3 commit `029ca43` contains the Compose setup and ACL correction; later `92cb70a` and `43d5398` add Ruff and pre-commit work. FAM-4/5: a fresh Odoo 19 database with demo loaded ran 20 focused tests with 0 failures and 0 errors; a missing demo produced a RED test failure, and a no-demo install skipped the demo test. After a backup, a one-time targeted XML import added 2 fictitious families and 8 partners to existing local `afa_family_test` (10 XML IDs, both payers guardians); web service restored. Local XML/YAML checks, Ruff check and Ruff format --check pass for changed Python. The GitHub Actions workflow has not run on GitHub because it is not published. Review and work-unit commit are pending; Engram mirror must match this document.
