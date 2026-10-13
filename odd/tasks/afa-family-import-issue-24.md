# Initial family load assistant (Issue #24)

## Objective and boundary
Add an Odoo 19 Community `afa_family_import` addon that performs the initial load of families from a CSV/Excel file: guardians and students with their course, contact data and, for the billing guardian, an IBAN plus a valid SEPA Core recurrent mandate. The wizard only creates new families; it never merges, rewrites or duplicates existing partners, and it never bypasses the family, role, course or SEPA rules already enforced by the existing addons.

## Authorized behavior and acceptance
- Input is one person per row, grouped by a shared `family_name`; the documented columns are `family_name, role, is_billing, name, email, phone, course, iban, mandate_date`. Headers are matched case-insensitively with spaces normalised to underscores.
- Per family the load order is: billing guardian without a family, `afa.family` linked to that guardian, remaining guardians and students with `afa_family_id` and `afa_course_id`, `res.partner.bank` for each row carrying an IBAN, and for the billing guardian a SEPA Core recurrent mandate with `format='sepa'`, `scheme='CORE'`, `signature_date` and state `valid`.
- Validation happens entirely before writing: role, name, email, IBAN mod-97 and country length, existing course for students, no course for non-students, at least one guardian and at most one billing guardian, and a non-future mandate signature date. A family with exactly one guardian and no marker auto-designates that guardian.
- Confirmation creates each family inside a `savepoint`; only `UserError` and `IntegrityError` are caught, a failure is written back onto that family's staging lines, `env.invalidate_all()` runs after a rollback and the remaining families still import.
- A family whose name already exists, including archived ones, is skipped and reported; re-running a file is therefore safe and creates no duplicates.
- Only `afa_family.group_family_manager` may load a file or confirm an import, enforced server-side.

## Repo evidence and assumptions to resolve during implementation
- `afa.family.create()` requires the billing partner to be an unassigned guardian and links it after creation (`afa_family/models/afa_family.py:48-65`); the payer must therefore be created before the family.
- `res.partner.create()` and `write()` deny family, role and course assignment without the manager group (`afa_family/models/res_partner.py:42-50`, `afa_school_course/models/res_partner.py:21-30`).
- OCA `account_banking_mandate` auto-assigns `unique_mandate_reference` from `/` and forbids `state='valid'` without `signature_date` and `partner_bank_id` (`_check_valid_state`); a signature date in the future is rejected (`_check_dates`). SEPA `format`, `scheme` and `type` choices come from `account_banking_sepa_direct_debit`.
- `res.partner.bank` and `account.banking.mandate` live outside the family-manager ACL, so the wizard creates them with `sudo()` only after the explicit manager check.
- Whether the `odoo:19.0` image ships `openpyxl` is verified at implementation time; without it `.xlsx` reports a clear message and CSV still works. **Resolved:** the image ships `openpyxl 3.1.2`, so `.xlsx` is read natively and a dedicated round-trip test covers it.

## Delivery and evidence policy
- Route: delegated direct implementation, because the addon spans a parser, transient staging models, a wizard, a controller, views, security, Compose/CI wiring and Odoo integration tests.
- Strategy: `stacked-to-main`, one work unit per PR. Forecast roughly 600–900 authored changed lines across implementation, tests, documentation and stack wiring; 400 lines per task is advisory and never a reason to drop tests.
- Test runner: fresh Odoo 19 database in the isolated Compose stack with `-i afa_family_import --test-enable --test-tags /afa_family_import --stop-after-init`; assert the Odoo test summary rather than the process exit status. Use a new database name for every installation.

## Work units
- [x] IMP-1 Addon skeleton and manager ACL. Check: fresh Odoo 19 install loads the addon. Route: delegated direct. Commit: `9cf649d`; review: pending.
- [x] IMP-2 CSV/Excel parsing, per-row validation, preview lines and template download. Check: focused parser/validation tests. Route: delegated direct. Commit: `9cf649d`; review: pending.
- [x] IMP-3 Confirm path with per-family savepoints, existing-family skip, bank account and SEPA mandate creation, atomicity and idempotency. Check: focused creation tests. Route: delegated direct. Commit: `9cf649d`; review: pending.
- [x] IMP-4 Addon and root documentation plus Compose and CI wiring. Check: `docker compose -f compose.test.yaml config -q` and a fresh focused install. Route: delegated direct. Commit: `9cf649d`; review: pending.

## Delivery decision
The forecast of 600–900 authored lines across four work units did not hold: the addon
landed as one coherent feature of 1235 added lines and the four units do not slice by
behaviour, only by layer, so splitting them would have left non-loadable intermediate
steps. Delivery is therefore `single-pr`: one work-unit commit `9cf649d` on
`feat/afa-family-import-issue-24`, maintainer-approved `size:exception`.

## Recovery state / next step
Work unit committed and pushed; pull request review is the remaining step. Fresh install on
database `afa_fi_fresh2` reports `0 failed, 0 error(s) of 22 tests` for
`--test-tags /afa_family_import`, and `ruff check`, `ruff format --check` and
`pre-commit run --all-files` are clean over `afa_family_import`. If the stack is run on this
machine, the PostgreSQL 16 volume behind `compose.test.yaml` still needs replacing so the
default project starts again; run under an isolated project name until then.
