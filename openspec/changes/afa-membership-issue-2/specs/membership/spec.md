# Membership delta specification

## ADDED requirements

### Requirement: A school year runs from July 1 through June 30
The system SHALL use an inclusive July 1–June 30 school year for dated family membership. The 2026/27 year SHALL start on 2026-07-01 and end on 2027-06-30.

#### Scenario: Boundaries
- **WHEN** membership for 2026/27 is evaluated on 2026-06-30, 2026-07-01 or 2027-06-30
- **THEN** only dates from 2026-07-01 through 2027-06-30 are inside that year.

### Requirement: Invoice mode depends on full payment
In invoice mode, the system SHALL recognize a family's qualifying invoice for its linked school year only while it is currently fully paid and today lies inside that period. Current full payment qualifies for the entire linked period, regardless of when payment arrived; this SHALL NOT imply historical backdating. A reversal or refund that removes full payment SHALL deactivate current entitlement; partial payment SHALL NOT activate it. A posted customer credit note whose native reversal link points to the exact dues invoice SHALL also revoke eligibility even when the original invoice remains `paid`.

MEM-2 SHALL only treat a positive-total, posted customer invoice created for that family-period link as qualifying. A draft invoice, unrelated partner invoice, fully credited/reversed invoice or invoice with `payment_state` other than `paid` SHALL NOT qualify; one link SHALL have at most one authoritative dues invoice.

#### Scenario: Payment arrives during the year
- **GIVEN** a qualifying 2026/27 invoice is only partially paid on 2026-08-01
- **WHEN** full payment is achieved on 2026-09-10
- **THEN** the family qualifies for the entire linked 2026/27 period while fully paid, and is currently a member on 2026-09-10; no past status before payment is asserted.

#### Scenario: Payment precedes year start
- **WHEN** a qualifying 2026/27 invoice is fully paid on 2026-06-15
- **THEN** the family is a member on 2026-07-01 while payment remains full, but not outside the linked period.

#### Scenario: Payment is undone or arrives too late
- **WHEN** a refund/reversal removes full payment, or today is after 2027-06-30 even though full payment arrived late
- **THEN** that invoice does not make the family a current member.

#### Scenario: Separately posted credit note
- **GIVEN** the dues invoice remains `paid` and a customer credit note has `reversed_entry_id` pointing to it
- **WHEN** the linked note is posted
- **THEN** the family is no longer invoice-mode eligible; a draft or canceled note does not revoke it.
- **AND WHEN** a posted credit note instead reverses an unrelated invoice to the same guardian
- **THEN** it does not affect the dues entitlement.

### Requirement: Periods and family links are valid (MEM-1)
Each period SHALL run exactly from July 1 to the following June 30, and periods SHALL NOT overlap. A family MAY be linked to a period, but SHALL NOT have duplicate or overlapping active links. An active link alone SHALL NOT claim the family is paid or currently a member.

Each link SHALL expose read-only validity dates derived from its period and a non-stored invoice-link state: `pending` before the period or while dues are unpaid, `active` during the period only while the authoritative posted invoice qualifies, `expired` after the period, and `canceled` when the link is archived. `active` remains the administrative Boolean enforcing unique active family-period links; manual family mode does not change the invoice-link state.

#### Scenario: Invalid or conflicting links
- **WHEN** an invalid/overlapping period or duplicate active family-period link is created or edited
- **THEN** the change is rejected without modifying the valid records.

#### Scenario: Link state changes without manual edits
- **GIVEN** an active family-period link for 2026/27
- **WHEN** the evaluation day is before July 1, inside the year without full payment, inside the year with a qualifying paid invoice, or after June 30
- **THEN** the derived state is respectively `pending`, `pending`, `active`, or `expired`.
- **AND WHEN** the link is archived or a posted credit note reverses its paid invoice
- **THEN** the state is respectively `canceled` or `pending`; attempts to write the derived state/dates are rejected.

### Requirement: Configurable manual mode retains family flag
An Odoo setting SHALL select invoice or manual mode. In manual mode an authorized family manager SHALL be able to change the family Boolean membership flag; that value SHALL persist across school years until manually changed. The effective membership read surface SHALL follow the selected mode, without clearing the stored manual flag on a mode change.

The default mode SHALL be invoice when unset. Only a system administrator SHALL be able to change the mode. The family SHALL expose read-only derived membership status, mode and current school-year period/invoice when relevant. These date-dependent fields SHALL be recomputed when read in a new Odoo environment, not stored with a time-insensitive dependency. Same-environment changes to the manual flag, active links, invoice payment and linked credit-note state SHALL invalidate cached derived status; saving a mode change SHALL also invalidate it. Archived links SHALL never supply the current invoice, even under `active_test=False`.

#### Scenario: Manual state survives a new school year
- **GIVEN** the family flag is true and manual mode is selected
- **WHEN** the school year changes or the mode is switched away and back
- **THEN** the manually stored flag is still true unless a manager changed it.

#### Scenario: Manual mode does not depend on billing
- **GIVEN** manual mode is selected and a family has no period link or its dues invoice is unpaid
- **WHEN** a manager sets the family flag to true
- **THEN** its derived membership is true through the next July 1 until a manager changes the flag.

#### Scenario: Only authorized settings and flags can be changed
- **WHEN** an ordinary user attempts to change the family manual flag or membership mode, or any user attempts to write a derived status
- **THEN** the write is denied and stored state is not changed.

#### Scenario: Same-request changes and archived replacement
- **GIVEN** the derived family status has already been read in the current Odoo environment
- **WHEN** a manager changes the manual flag, the admin switches mode, an invoice becomes paid, a linked credit note is posted/drafted, or an active link is archived and replaced
- **THEN** the next same-date read reflects the changed status and selects only the active link without a global cache reset.

### Requirement: Issued invoice recipient remains a snapshot
At issuance the system SHALL associate each qualifying invoice with its family and year and use the then-designated guardian as billing partner. A later change to `afa.family.billing_partner_id` SHALL NOT rewrite an already issued invoice's partner or reassign its membership to a different family.

#### Scenario: Guardian is reassigned after issuance
- **GIVEN** a qualifying invoice was issued to guardian A for family F
- **WHEN** the family designates guardian B as its new billing partner
- **THEN** that invoice still bills A and is still attributed to F; future issuance may bill B.

### Requirement: Membership edits are authorized
Manual changes to family membership and invoice-family/year linkage SHALL be protected by server-side permissions, not only by hidden interface controls. Existing student-contact access restrictions SHALL remain intact.

#### Scenario: Unprivileged edit
- **WHEN** a user without family-management authority attempts to change a membership flag or linkage
- **THEN** the write is denied without changing the stored state.

## Open assumptions (not authorized product decisions)
- MEM-2 explicitly creates one product-backed dues invoice for each link. Only a posted credit note carrying Odoo's native `reversed_entry_id` to that exact invoice revokes paid entitlement; arbitrary unlinked credit notes do not.
- Only current Odoo payment status is used. Historical payment timestamps are not required.
- The manual flag is undated and global per family; the database-wide setting defaults to invoice mode. The inherited family form shows the manager-only flag in manual mode and relevant invoice-period context in invoice mode.
