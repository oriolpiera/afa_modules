# afa_modules

## Odoo 19 local test stack

The development-only stack in `compose.test.yaml` runs PostgreSQL 16 and Odoo 19
with `afa_family` mounted from this checkout. It does not change the separate
Odoo 16 stack. Docker Engine and Compose are required.

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
