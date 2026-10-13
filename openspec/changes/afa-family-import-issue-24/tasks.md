# Implementation checklist

The recovery task of record is `odd/tasks/afa-family-import-issue-24.md`. Work units are published as stacked PRs against `main`.

- [x] IMP-1 Addon skeleton: manifest, imports, transient models, manager ACL and Compose mount. Check: fresh Odoo 19 install loads `afa_family_import`. Route: delegated direct. Evidence: fresh install on `afa_fi_fresh2` loads the module and runs its tests.
- [x] IMP-2 CSV/Excel parsing and per-row validation with preview lines and the downloadable template. Check: focused parser/validation tests. Route: delegated direct. Evidence: focused tests green, including `.xlsx` round-trip and template column arity.
- [x] IMP-3 Confirm path: per-family savepoint creation, skip of existing families, bank account and SEPA mandate creation, atomicity and idempotency tests. Check: focused creation tests. Route: delegated direct. Evidence: happy path, savepoint rollback of real writes and re-run idempotency all green.
- [x] IMP-4 Documentation and CI wiring: addon README, root README entry, workflow install list, test tags and a marker assertion. Check: `docker compose -f compose.test.yaml config -q` and a fresh install with focused tests. Route: delegated direct. Evidence: `config -q` OK; `--test-tags /afa_family_import` reports `0 failed, 0 error(s) of 28 tests`; the CI marker `Starting TestFamilyImport.test_import_creates_family_guardians_students_bank_and_mandate` is present.

## Verification record

| Command | Result |
| --- | --- |
| `ruff check afa_family_import` | All checks passed |
| `ruff format --check afa_family_import` | Clean |
| `pre-commit run --all-files` | ruff-check and ruff-format pass |
| `docker compose -f compose.test.yaml config -q` | OK |
| Fresh install `-i afa_family_import --with-demo --test-tags /afa_family_import` on `afa_fi_fresh3` | `0 failed, 0 error(s) of 28 tests` |
| `openpyxl` in the `odoo:19.0` image | `3.1.2`, so `.xlsx` works natively |

## Review findings

Six Greptile findings on PR #25 were verified against the code and all were real; each got
its own commit (`1ebec61`, `4fe97f4`, `aeefceb`, `fa586be`, `7962d50`, `d64f1c9`). See the
`Review fixes` table in `odd/tasks/afa-family-import-issue-24.md`.

## Findings

- The test fixtures and the downloadable template both originally omitted the empty `course`
  field, which shifted `iban` one column left and put the mandate date in `iban`. Row
  building now derives from `file_format.COLUMNS`, and a test asserts every template row has
  exactly `len(COLUMNS)` fields.
- The Compose test stack volume on this machine still holds a PostgreSQL 16 cluster while
  `compose.test.yaml` pins `postgres:18`, so the default project fails to start `db`. All
  verification ran under an isolated project (`-p afa_import_check`) to leave the existing
  volume untouched. Pre-existing on `main`, not introduced here.
