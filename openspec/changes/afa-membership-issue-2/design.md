# Membership implementation design (provisional)

## Starting point
`afa_family/models/afa_family.py` has a required `billing_partner_id`; partners have a single `afa_family_id`. MEM-1 installed family-period links and the isolated Compose addon mount; `afa_family` remains independent of `account`. The Issue #1 payer test verifies only an old ID reference, not `account.move` behavior.

## Proposed boundaries
| Boundary | Intended responsibility |
| --- | --- |
| `afa_membership` addon | Depend on `afa_family`, `account` and `product`; MEM-1 owns shared July–June periods and manager-controlled family-period links. Avoid adding dependencies to the base family addon. |
| `afa.family` extension | MEM-1 exposes links for managers, not an `is_member` placeholder. MEM-3 adds the persistent manual flag and MEM-2/3 add effective state from current status/date. |
| `account.move` extension | MEM-2 creates exactly one authoritative, product-backed invoice from the active family-period link, snapshots its selected guardian, and stores an indexed invoice-to-link reference. No arbitrary partner invoice counts; the issued invoice cannot be reassigned to another family-period link. |
| Settings/security/UI | `res.config.settings` selection backed by `ir.config_parameter` (assumed database-wide); server-side protection for flag/link edits; contextual form/list display for managers. |
| Test harness | Mount the new addon read-only in the existing isolated Odoo 19 Compose stack and install both addons on a fresh database; assert actual Odoo test summaries, not process exit alone. |

## Date and state logic
Identify a school year by its July 1 start and following June 30 end. MEM-1 rejects invalid dates, overlapping global periods and duplicate/overlapping active family-period links. Link `active` is administrative state, **not** paid/member state. MEM-2 exposes only a per-link invoice eligibility check, not a global `is_member` flag: linked invoice must be a posted customer invoice with positive total and current `payment_state == 'paid'`, evaluation date must lie inside the inclusive period, and no posted customer credit note may have `reversed_entry_id` pointing to this exact dues invoice. Partial, draft, unreconciled, canceled and reversed payments do not qualify. A current paid invoice qualifies for the entire period without historical backdating. MEM-3 later controls manual mode.

## Decisions deferred to evidence
- MEM-2 integration tests use Odoo 19 `generic_coa` and a cash journal, testing partial/full payment, unreconciliation and full credit-note reversal. Eligibility reads the current invoice state; no historical paid date is required.
- A dues invoice is identified by creation from the link with a positive-price product, not by scanning partner invoices. A separately posted credit note with Odoo's verified `reversed_entry_id` to the dues invoice revokes eligibility even if that invoice stays `paid`. Draft/canceled linked notes and posted notes reversing unrelated invoices do not revoke; no duplicate credit-note linkage is stored.
- Confirm setting default/scope, UI placement and whether an undated manual flag is the complete desired experience. A standard `res.config.settings` pattern is a proposal, not proof of Odoo 19 API compatibility.

## Verification and rollback
Test first with `TransactionCase` for period boundaries, link validation and manager permissions, then in MEM-2/3 add account/flag integration scenarios. The planned fresh-database Compose runner requires the new mount. Rollback MEM-1 by removing its addon and isolated test mount; leave `afa_family` identity and existing invoices intact. Runtime evidence must be recorded after an actual run.
