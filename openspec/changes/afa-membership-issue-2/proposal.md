# Add school-year family membership

## Why
The existing family addon identifies people and their billing guardian, but cannot represent AFA membership. Staff need a July–June membership period that reflects fully paid dues, or a persistent manual family flag when configured.

## What changes
- Introduce `afa_membership`, depending on `afa_family`, `account`, and `product`; MEM-1 provides family-period links, but no effective membership claim before MEM-2/3.
- Support invoice mode later: a currently fully paid invoice qualifies for its entire linked period while today is inside it; loss of full payment removes current eligibility. No payment-date start or historical backdating is claimed.
- Support configured manual mode: a manager-controlled family flag that does not reset each year. Switching modes does not discard invoice history or overwrite the flag.
- Select the current family billing guardian at invoice issuance; never retroactively rewrite issued billing partners.
- Extend the isolated Odoo 19 test stack and addon tests/documentation with the behavior.

## Scope and risk
MEM-1 is limited to the installable period/link domain, manager security, basic UI, tests and isolated stack mount. Invoice issuance, effective membership and settings remain future work. Historical invoice recipient rewrites and unrelated invoices are out of scope. Exact qualifying invoice criteria and refund semantics require confirmation; see [design](design.md). The ODD recovery checklist is at `odd/tasks/afa-membership-issue-2.md`.
