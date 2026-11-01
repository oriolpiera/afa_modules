# afa_modules

## Odoo 19 local test stack

The development-only stack in `compose.test.yaml` runs PostgreSQL 18 and Odoo 19
with `afa_family`, `afa_account_reconcile`, `afa_membership`, `afa_member_pricing`, `afa_sepa`,
`afa_apparel_shop`, `afa_service_subscription`, `afa_school_course`, `afa_extracurricular`,
`afa_family_import`, `afa_acollida`, and `afa_attendance_kiosk_pwa` mounted from
this checkout. It does not change the separate Odoo 16 stack. Docker Engine and
Compose are required.

Fetch the pinned OCA 19.0 revisions used by the local test stack:

```sh
git clone --branch 19.0 https://github.com/OCA/account-reconcile.git .oca-account-reconcile
git -C .oca-account-reconcile checkout 8fc48a4beff3203241c0f61c4d3bc15631f75a4d
git clone --branch 19.0 https://github.com/OCA/bank-payment.git .oca-bank-payment
git -C .oca-bank-payment checkout fdd5d4040b235a4c688b2aec30611d57dd246b64
```

The checkouts are ignored by Git; CI fetches the same revisions.

```sh
docker compose -f compose.test.yaml up -d db
docker compose -f compose.test.yaml run --rm odoo -d afa_family_test -i afa_family --test-enable --test-tags /afa_family --stop-after-init --log-level=test --db_host=db --db_user=odoo --db_password=odoo
docker compose -f compose.test.yaml up -d odoo
```

Open http://127.0.0.1:8079 after Odoo starts. For subsequent test runs against
the same database, replace `-i afa_family` with `-u afa_family`. Stop the stack
with `docker compose -f compose.test.yaml down` (the test data volumes persist).
This stack uses local development credentials; do not expose it to the network.
Select database `afa_family_test` and sign in to Odoo with `admin` / `admin`.
The `odoo` / `odoo` values in the Compose file authenticate Odoo to PostgreSQL;
they are not an Odoo web account.

If you ran this stack on PostgreSQL 16 before the upgrade to 18, the old cluster
stays at the volume root but PostgreSQL 18 looks in a versioned subdirectory, so
those databases are no longer listed. Back them up, or reset the test volumes
with `docker compose -f compose.test.yaml down -v` and reinstall.

## Demo data and CI

`afa_family` defines fictitious families and contacts under its manifest `demo` key;
`afa_extracurricular` also supplies a current-year billing example. Demo records
are not loaded in normal installations. Install them into a fresh database:

```sh
docker compose -f compose.test.yaml run --rm odoo -d afa_addons_demo_example -i afa_family,afa_account_reconcile,afa_membership,afa_member_pricing,afa_apparel_shop,afa_sepa,afa_service_subscription,afa_school_course,afa_extracurricular,afa_family_import,afa_acollida,afa_attendance_kiosk_pwa --with-demo --stop-after-init --log-level=warn --db_host=db --db_user=odoo --db_password=odoo
```

Use a new database for each fresh install. The `.github/workflows/odoo-tests.yml`
workflow runs demo-compatible tests in one database and membership, SEPA,
extracurricular, and Acollida billing tests in another without demo fixtures.
The demo-enabled group explicitly runs `TestExtracurricularDemo` while avoiding
the full extracurricular transactional test class against shared demo records.
The workflow targets PRs to `main` and pushes to `main`, with read-only
repository permission; it runs the twelve AFA addons' tests, not the full
upstream Odoo suite. Odoo can log test failures while returning a successful
process exit status, so CI also checks its result summary and expected test
markers. Local tests do not constitute remote CI evidence; check the PR's
Actions status.
See [AFA Membership](afa_membership/README.md) for family membership intention,
period, dues invoice, return, and access rules. `afa_family` can still be installed alone.
See [AFA Accounting Reconciliation](afa_account_reconcile/README.md) for the
billing-guardian partner filter in bank reconciliation.
See [AFA Member Pricing](afa_member_pricing/README.md) for sales and web pricing setup.
See [AFA Apparel Shop](afa_apparel_shop/README.md) for apparel variants, inventory,
school pickup, bank transfers, and seven-day stock reservations.
See [AFA SEPA Collections](afa_sepa/README.md) for setup, bank validation, and returns.
See [AFA Invoice Receipts](afa_invoice_receipt/README.md) for customer receipt PDFs,
SEPA account display, and transfer instructions.
See [Monthly Service Subscriptions](afa_service_subscription/README.md) for service
windows, staff enrollment, monthly review, and family invoicing.
See [School Courses](afa_school_course/README.md) for the course ladder, the
quick course setup assistant, and the once-per-year bulk promotion and
graduation workflow.
See [Extracurriculars](afa_extracurricular/README.md) for activity groups,
weekly schedules, staff student enrollment, and family scholarships billed to
the Consell Comarcal.
See [Initial Family Load](afa_family_import/README.md) for the CSV/Excel load of
families, guardians, students, IBANs and SEPA mandates.
See [Acollida Fixed Fees](afa_acollida/README.md) for importing monthly fixed-user
fees and generating family invoices.
See [Attendance Kiosk PWA](afa_attendance_kiosk_pwa/README.rst) for installing the
Odoo 19 attendance kiosk as a standalone Android web app.

## Pull request previews

The `.github/workflows/preview.yml` workflow starts a disposable Odoo 19 preview
for same-repository pull requests targeting `main`. It uses the development
Compose stack, installs all AFA addons with demo data declared by
`afa_extracurricular`, configures a current-month billing example, and exposes
Odoo through a temporary Cloudflare Quick Tunnel. It remains available for one
hour after becoming ready; new commits and PR closure cancel the previous run.
Open the workflow run's summary to find the URL.

Before enabling the workflow, add a repository Actions secret named
`AFA_PREVIEW_PASSWORD`. The preview gateway uses it for HTTP Basic
Authentication (username `preview`); the Odoo login is `admin` / `admin`.
Choose a strong, single-line password; reviewers need it to access the preview.
Fork-originated PR previews are skipped because GitHub does not provide
repository secrets to those workflows. The Quick Tunnel URL is public, so the
preview must contain only synthetic data. Do not enter real family, student,
payment, or other production data.
