# AFA Accounting Reconciliation

This addon filters partner choices in bank statement entry and reconciliation.
It keeps contacts outside AFA families (including suppliers) available and
allows only each family's designated billing guardian among its members.

The stored `afa_is_accounting_partner_eligible` flag is visible to accounting
users and does not expose family membership or guardian/student roles. OCA
addons are extended through inherited views; their source is not modified.

Install `afa_account_reconcile` together with its dependencies to enable the
filter. The selector domain is a user-interface guard; it does not change
partners assigned automatically during bank statement import.

Run the focused tests against a fresh database:

```sh
docker compose -f compose.test.yaml run --rm odoo \
  -d afa_account_reconcile_test \
  -i afa_account_reconcile \
  --test-enable --test-tags /afa_account_reconcile \
  --stop-after-init --log-level=test \
  --db_host=db --db_user=odoo --db_password=odoo
```
