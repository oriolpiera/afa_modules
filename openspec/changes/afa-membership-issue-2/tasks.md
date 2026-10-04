# Implementation checklist

The recovery task of record is `odd/tasks/afa-membership-issue-2.md`. MEM-1 has focused RED/GREEN and fresh-install evidence there; work-unit commit/review and all later tasks remain pending.

- [x] MEM-1: Test-first July–June periods (including 2026/27), family-period links, invalid/overlap/duplicate-active constraints and manager access; installable addon, basic views and test mount. No effective membership field. Check: 6 focused tests, 0 failed and 0 errors on a fresh Odoo 19 install; commit/review pending.
- [x] MEM-2 implementation and focused verification: product-backed dues invoice, guardian snapshot, paid/partial/unreconcile/full reversal, posted linked credit-note revocation despite original remaining paid, unrelated/draft/canceled note exclusion and recreation safeguards. Fresh Odoo 19 run: 15 focused tests, 0 failures/errors. No historical payment-date requirement; parent review/commit pending.
- [x] MEM-3 implementation and focused verification: admin-only invoice/manual setting, manager-only persistent family flag, non-stored derived status/current period/invoice and inherited form/settings views. Fresh Odoo 19 focused suite: 20 tests, 0 failures/errors. Work-unit commit/review pending.
- [ ] MEM-4: Mount addon in isolated Compose stack and document install/test workflow; validate fresh install, focused suite, failure summary and family/security regressions. Record exact runner results and actual review/commit boundaries only after they happen.
