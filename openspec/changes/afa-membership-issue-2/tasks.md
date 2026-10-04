# Implementation checklist

The recovery task of record is `odd/tasks/afa-membership-issue-2.md`. All four work units have local RED/GREEN and fresh-install evidence and are committed on the feature branch. Remote CI and PR delivery have not occurred.

- [x] MEM-1 `ced8105`: Test-first July–June periods (including 2026/27), family-period links, invalid/overlap/duplicate-active constraints and manager access; installable addon, basic views and test mount. Initial 6 focused tests and final 8 focused tests passed on fresh Odoo 19 installs.
- [x] MEM-2 `65734c7`: Product-backed dues invoice, guardian snapshot, paid/partial/unreconcile/full reversal, posted linked credit-note revocation despite original remaining paid, unrelated/draft/canceled note exclusion and recreation safeguards. Fresh Odoo 19 run: 15 focused tests, 0 failures/errors. No historical payment-date requirement.
- [x] MEM-3 `d9ff791`: Admin-only invoice/manual setting, manager-only persistent family flag, non-stored derived status/current period/invoice and inherited form/settings views. Final fresh Odoo 19 focused suite: 23 tests, 0 failures/errors.
- [x] MEM-4 `5ce40f6`: Derived invoice-link state/dates, addon/root/family docs and combined read-only CI workflow with family demo and membership markers. Fresh combined demo install reported 0 failed, 0 errors of 46 tests; focused membership install reported 0 failed, 0 errors of 26 tests. CI has not run remotely; native review was declined for this candidate only.
