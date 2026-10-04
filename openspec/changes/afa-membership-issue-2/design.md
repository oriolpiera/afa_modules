# Membership implementation design (provisional)

## Starting point
`afa_family/models/afa_family.py` has a required `billing_partner_id`; partners have a single `afa_family_id`. MEM-1 installed family-period links and the isolated Compose addon mount; `afa_family` remains independent of `account`. The Issue #1 payer test verifies only an old ID reference, not `account.move` behavior.

## Proposed boundaries
| Boundary | Intended responsibility |
| --- | --- |
| `afa_membership` addon | Depend on `afa_family`, `account` and `product`; MEM-1 owns shared July–June periods and manager-controlled family-period links. Avoid adding dependencies to the base family addon. |
| MEM-4 link display | Expose non-stored, read-only `state` and related period `date_start`/`date_end` on the invoice link. Keep administrative `active` for the database partial uniqueness rule; manual mode affects only family effective status. |
| `afa.family` extension | MEM-3 adds a stored manager-only manual flag and non-stored, read-only family membership status, mode, current school year and linked invoice. In invoice mode, status uses the MEM-2 per-link check; manual mode ignores invoice payment and period eligibility. No partner flag. |
| `account.move` extension | MEM-2 creates exactly one authoritative, product-backed invoice from the active family-period link, snapshots its selected guardian, and stores an indexed invoice-to-link reference. No arbitrary partner invoice counts; the issued invoice cannot be reassigned to another family-period link. |
| Settings/security/UI | `res.config.settings` selection backed by database-wide `ir.config_parameter`, default invoice when unset; only system administrators may save mode changes. Server-side family mutation guards plus field groups restrict manual editing to family managers; inherited family form shows current status/period/invoice, with manual flag only in manual mode. |
| Test harness | Mount the new addon read-only in the existing isolated Odoo 19 Compose stack and install both addons on a fresh database; assert actual Odoo test summaries, not process exit alone. |

## Date and state logic
Identify a school year by its July 1 start and following June 30 end. MEM-1 rejects invalid dates, overlapping global periods and duplicate/overlapping active family-period links. Link `active` is administrative state, **not** paid/member state. MEM-2 per-link invoice eligibility requires a posted positive-total customer invoice with current `payment_state == 'paid'`, evaluation date inside the inclusive period, and no posted customer credit note with `reversed_entry_id` to that invoice. MEM-3 computes family `is_member` without storing it: in invoice mode find today's **explicitly active** family-period link and evaluate its invoice; in manual mode read the stored Boolean unchanged across July 1 even without a link. Odoo 19 accepted `@api.depends` paths for the manual flag, family links/period dates, invoice state/payment state and invoice reversal moves/state; these invalidate cached status in the same environment after writes. Admin mode changes explicitly invalidate derived family fields after `set_values`. A new Odoo request/environment reads today's date again; tests invalidate cache only when simulating a different day. No stored date dependency or daily cron.

MEM-4 adds a separate per-link invoice state: archived links are `canceled`; an open link after its period is `expired`; otherwise an in-period qualifying invoice is `active` and all other open links are `pending`. Related validity dates come only from the school year. `@api.depends` on invoice/payment/reversal state invalidates the link state on accounting changes; reading in a new request handles day rollovers. This link state never reads the manual family flag.

## Decisions deferred to evidence
- MEM-2 integration tests use Odoo 19 `generic_coa` and a cash journal, testing partial/full payment, unreconciliation and full credit-note reversal. Eligibility reads the current invoice state; no historical paid date is required.
- A dues invoice is identified by creation from the link with a positive-price product, not by scanning partner invoices. A separately posted credit note with Odoo's verified `reversed_entry_id` to the dues invoice revokes eligibility even if that invoice stays `paid`. Draft/canceled linked notes and posted notes reversing unrelated invoices do not revoke; no duplicate credit-note linkage is stored.
- MEM-3 implements a database-wide mode with invoice fallback and a persistent, undated family flag as requested. Configuration is exposed only to system administrators, family fields only to managers; the combined status is non-stored to prevent stale July rollovers. Focused tests verify Odoo 19 settings persistence and inherited view loading.

## Verification and rollback
Test first with `TransactionCase` for period boundaries, link validation and manager permissions, then in MEM-2/3 add account/flag integration scenarios. The planned fresh-database Compose runner requires the new mount. Rollback MEM-1 by removing its addon and isolated test mount; leave `afa_family` identity and existing invoices intact. Runtime evidence must be recorded after an actual run.
