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
- Running authored line count: 540 at `cddd53c` (commit already present on the branch); review boundary pending.

## Tasks
- [x] FAM-1: Implement installable Odoo 19 family/partner domain and regression tests for billing, roles, one-family membership and invoice-recipient stability. Check: Odoo 19 addon loads; scoped tests run. Route: delegated direct. Commit: `cddd53c` (already present on branch); review: pending. Invoice recipient stability is limited to not changing existing references; no `account.move` integration is claimed.
- [x] FAM-2: Add family and partner UI plus ACL/record rules and authorization regression tests. Check: Odoo 19 addon loads; scoped tests run. Route: delegated direct. Commit: `cddd53c` (already present on branch); review: pending.
- [ ] FAM-3: Run Odoo 19 in an isolated Compose stack, correct observed manager Contacts ACL failure and document repeatable focused test commands. Check: scoped Odoo 19 tests, Compose config, and HTTP readiness. Route: delegated test execution and bounded fix; commit: pending; review: pending.

## Progress and next step
- Product decision and Odoo target resolved. `cddd53c` contains the addon; a broad Odoo install run reported 3 failures and 27 errors across 1,914 tests, including unrelated upstream tests. The focused `/afa_family` run initially reported 7 setup errors out of 18 tests because managers lacked Contact creation rights. After a manager-only Contacts ACL and fixture corrections, the focused run reported 19 tests, 0 failures and 0 errors. `docker compose -f compose.test.yaml config -q` passed; Odoo 19 serves HTTP 200 at `http://127.0.0.1:8079/web/login` and PostgreSQL is healthy. Review and commit of FAM-3 remain pending; Engram mirror saved.
