# afa_modules

## Odoo 19 local test stack

The development-only stack in `compose.test.yaml` runs PostgreSQL 16 and Odoo 19
with `afa_family`, `afa_membership`, `afa_member_pricing`, and `afa_sepa` mounted from this checkout.
It does not change the separate Odoo 16 stack. Docker Engine and Compose are required.

For SEPA tests, fetch the pinned OCA 19.0 bank-payment revision first:

```sh
git clone --branch 19.0 https://github.com/OCA/bank-payment.git .oca-bank-payment
git -C .oca-bank-payment checkout fdd5d4040b235a4c688b2aec30611d57dd246b64
```

The checkout is ignored by Git; the CI workflow fetches the same revision.

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

## Demo data and CI

`afa_family` defines fictitious families and contacts under its manifest `demo` key,
not regular installation data. Use a **new database name** for an isolated install
with demo records and the focused addon tests; do not reuse the live UI database:

```sh
docker compose -f compose.test.yaml run --rm -e AFA_EXPECT_DEMO=1 odoo -d afa_addons_fresh_example -i afa_family,afa_membership,afa_member_pricing,afa_sepa --with-demo --test-enable --test-tags /afa_family,/afa_membership,/afa_member_pricing,/afa_sepa --stop-after-init --log-level=test --db_host=db --db_user=odoo --db_password=odoo
```

Use another unused database name for each fresh local install. When demo data
is absent, the demo-specific test skips unless `AFA_EXPECT_DEMO=1` is set; CI
sets it so a missing demo fixture fails instead of silently passing. The
`.github/workflows/odoo-tests.yml` workflow runs the combined install and tests
on PRs targeting `main` and pushes to `main` with read-only repository
permission. It runs all four AFA addons' tests, not the full upstream Odoo
suite. CI also checks Odoo's result summary and confirms the family and pricing
demo fixtures and all four addons' test classes ran.
Odoo can log test failures while returning a successful process exit status.
Local tests do not constitute remote CI evidence; check the PR's Actions status.
See [AFA Membership](afa_membership/README.md) for period, invoice, refund,
manual-mode, and access rules. `afa_family` can still be installed alone.
See [AFA Member Pricing](afa_member_pricing/README.md) for sales and web pricing setup.
See [AFA SEPA Collections](afa_sepa/README.md) for setup, bank validation, and returns.
