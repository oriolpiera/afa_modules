# Family import implementation design (provisional)

## Starting point
`afa_family` owns family identity, guardian/student roles and a required billing guardian. `afa_school_course` adds `res.partner.afa_course_id` restricted to students. `afa_sepa` brings OCA `account_banking_mandate` / `account_banking_sepa_direct_debit`, so a SEPA Core mandate has `format='sepa'`, `scheme='CORE'` and `type='recurrent'`. Both `afa.school.promotion.wizard` and `afa.sepa.wizard` already establish the preview-then-confirm pattern with transient staging lines.

## Proposed boundaries
| Boundary | Intended responsibility |
| --- | --- |
| `afa_family_import` addon | Own the wizard, the transient staging lines, the CSV/Excel parser, the template controller and its tests. Depend on the existing addons; never extend their models. |
| `afa.family` / `res.partner` | Unchanged. Creation goes through the public `create()` APIs so the billing and role invariants are exercised, not bypassed. |
| `account.banking.mandate` | Created only for the billing guardian, via `sudo()` after an explicit manager check, because accounting ACLs are not part of the family-manager role. |
| `res.partner.bank` | Created for every row that carries an IBAN, attached to that person; only the billing guardian gets a mandate. |
| Course identity | Read-only lookup by name; the course ladder keeps owning creation and uniqueness. |

## Load order and invariants
`afa.family.create()` browses the billing partner, requires it to be an unassigned guardian, creates the family under a `_afa_initial_family_creation` context and then writes `afa_family_id` onto the payer. The wizard therefore creates the payer without a family first, then the family, then the remaining people. A guardian row with an empty `is_billing` is auto-designated when the family has exactly one guardian; zero or more than one billing guardian in a multi-guardian family is an error, never a guess.

## Validation, atomicity and idempotency
Parsing normalises headers (lower-cased, underscored) and rejects unknown roles, malformed emails, invalid IBANs, unknown courses, students without a course and future mandate signature dates. Families present under the same name are marked `skip` and excluded from validation noise. Confirm re-validates, then creates each family inside `env.cr.savepoint()`; only `UserError` and `IntegrityError` are caught, other failures still propagate. A caught failure is written back onto that family's staging lines so the manager sees exactly which family was refused, and the remaining families still import. `env.invalidate_all()` runs after a rollback so later families read a fresh database state.

## Decisions deferred to evidence
- IBAN validation uses an ISO 13616 mod-97 check plus a country length table, rather than relying on an undocumented Odoo internal, so the preview message is deterministic and testable.
- CSV parsing uses the standard library with `utf-8-sig`; `.xlsx` uses `openpyxl` and is optional. No `.xls` support, because Odoo 19 does not pin a reader for it.
- The template is served by a read-only HTTP controller restricted to family managers, avoiding the creation of attachment records for a static file.
- Duplicate detection matches `afa.family.name` with `active_test=False`; the file is the source of truth for names, and two families sharing a name in one file are merged into one because name is the natural key here.

## Verification and rollback
Test first with `TransactionCase`: a valid file creates guardians, students, courses, bank accounts and valid SEPA mandates; invalid roles, unknown courses, missing or duplicated billing guardians, bad IBANs and future dates each produce a staged error and create nothing. Atomicity is verified by a file where the second family is invalid: the first family must still be created. Install the addon on a fresh Odoo 19 database in the isolated Compose stack and assert the real Odoo test summary. Rollback is removing the addon and its Compose/CI mount.
