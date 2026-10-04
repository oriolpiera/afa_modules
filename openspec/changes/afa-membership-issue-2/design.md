# Membership implementation design (provisional)

## Starting point
`afa_family/models/afa_family.py` has a required `billing_partner_id`; partners have a single `afa_family_id` and manager-only membership/role edits. `afa_family` depends on `base` and `contacts`, not `account`. `compose.test.yaml` mounts only `afa_family`, so the proposed addon cannot yet install in that stack. The Issue #1 payer test verifies only an old ID reference, not `account.move` behavior.

## Proposed boundaries
| Boundary | Intended responsibility |
| --- | --- |
| `afa_membership` addon | Depend on `afa_family`, `account` and `product`; MEM-1 owns shared July–June periods and manager-controlled family-period links. Avoid adding dependencies to the base family addon. |
| `afa.family` extension | MEM-1 exposes links for managers, not an `is_member` placeholder. MEM-3 adds the persistent manual flag and MEM-2/3 add effective state from current status/date. |
| `account.move` extension | Record family and school year with a qualifying dues invoice when issued, select the then-current billing guardian, and preserve posted/issued partner and family association on later family changes. Do not infer past family from a guardian's current assignment. |
| Settings/security/UI | `res.config.settings` selection backed by `ir.config_parameter` (assumed database-wide); server-side protection for flag/link edits; contextual form/list display for managers. |
| Test harness | Mount the new addon read-only in the existing isolated Odoo 19 Compose stack and install both addons on a fresh database; assert actual Odoo test summaries, not process exit alone. |

## Date and state logic
Identify a school year by its July 1 start and following June 30 end. MEM-1 rejects invalid dates, overlapping global periods and duplicate/overlapping active family-period links. Link `active` is administrative state, **not** paid/member state. In later invoice mode, membership is currently effective if a qualifying linked invoice is fully paid now and today falls inside the linked period; paying during the year qualifies for the whole period without asserting historical backdating. Re-evaluate current payment state after refunds/reversals. Manual mode later reads its stored family flag without year-based mutation.

## Decisions deferred to evidence
- Confirm Odoo 19 current payment state, credit notes and reversals in integration tests before selecting computed fields vs explicit linkage/event model. No historical paid date is required for the authorized current-membership rule.
- Confirm how dues are identified (explicit flag/product/invoice origin), how multiple dues invoices combine, and whether partial refunds can leave full payment. Require a product decision if tests cannot uniquely determine the intended result.
- Confirm setting default/scope, UI placement and whether an undated manual flag is the complete desired experience. A standard `res.config.settings` pattern is a proposal, not proof of Odoo 19 API compatibility.

## Verification and rollback
Test first with `TransactionCase` for period boundaries, link validation and manager permissions, then in MEM-2/3 add account/flag integration scenarios. The planned fresh-database Compose runner requires the new mount. Rollback MEM-1 by removing its addon and isolated test mount; leave `afa_family` identity and existing invoices intact. Runtime evidence must be recorded after an actual run.
