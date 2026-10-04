# Implementation checklist

The recovery task of record is `odd/tasks/afa-membership-issue-2.md`. MEM-1 has focused RED/GREEN and fresh-install evidence there; work-unit commit/review and all later tasks remain pending.

- [x] MEM-1: Test-first July–June periods (including 2026/27), family-period links, invalid/overlap/duplicate-active constraints and manager access; installable addon, basic views and test mount. No effective membership field. Check: 6 focused tests, 0 failed and 0 errors on a fresh Odoo 19 install; commit/review pending.
- [ ] MEM-2: Test-first issuance snapshot and qualifying invoice lifecycle: unpaid, partial, currently fully paid inside/outside linked period, reversal/refund, multiple invoices and guardian reassignment; implement linkage and current eligibility after confirming Odoo 19 payment semantics and product rules. Check: focused accounting integration tests; no historical payment-date requirement.
- [ ] MEM-3: Test-first database setting, manual flag authorization and persistence across year/mode switches; implement settings and UI. Check: focused mode/permissions tests.
- [ ] MEM-4: Mount addon in isolated Compose stack and document install/test workflow; validate fresh install, focused suite, failure summary and family/security regressions. Record exact runner results and actual review/commit boundaries only after they happen.
