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
- Running authored line count: 0. Reviewed boundary: branch point.

## Tasks
- [ ] FAM-1: Implement installable Odoo 19 family/partner domain and regression tests for billing, roles, one-family membership and invoice-recipient stability. Check: Odoo 19 addon tests where available; Python/XML structural checks otherwise. Route: delegated direct (multiple non-trivial files). Commit: pending; review: pending.
- [ ] FAM-2: Add family and partner UI plus ACL/record rules and authorization regression tests. Check: Odoo 19 addon tests where available; XML/security structural checks otherwise. Route: delegated direct (multiple non-trivial files). Commit: pending; review: pending.

## Progress and next step
- Product decision and Odoo target resolved. Start FAM-1; collect observed test evidence before marking it complete. Engram mirror pending if memory service cannot bind this session.
