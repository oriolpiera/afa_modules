# Membership delta specification

## ADDED requirements

### Requirement: A school year runs from July 1 through June 30
The system SHALL use an inclusive July 1–June 30 school year for dated family membership. The 2026/27 year SHALL start on 2026-07-01 and end on 2027-06-30.

#### Scenario: Boundaries
- **WHEN** membership for 2026/27 is evaluated on 2026-06-30, 2026-07-01 or 2027-06-30
- **THEN** only dates from 2026-07-01 through 2027-06-30 are inside that year.

### Requirement: Invoice mode depends on full payment
In invoice mode, the system SHALL recognize a family's qualifying invoice for its linked school year only while it is currently fully paid and today lies inside that period. Current full payment qualifies for the entire linked period, regardless of when payment arrived; this SHALL NOT imply historical backdating. A reversal or refund that removes full payment SHALL deactivate current entitlement; partial payment SHALL NOT activate it.

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

### Requirement: Periods and family links are valid (MEM-1)
Each period SHALL run exactly from July 1 to the following June 30, and periods SHALL NOT overlap. A family MAY be linked to a period, but SHALL NOT have duplicate or overlapping active links. An active link alone SHALL NOT claim the family is paid or currently a member.

#### Scenario: Invalid or conflicting links
- **WHEN** an invalid/overlapping period or duplicate active family-period link is created or edited
- **THEN** the change is rejected without modifying the valid records.

### Requirement: Configurable manual mode retains family flag
An Odoo setting SHALL select invoice or manual mode. In manual mode an authorized family manager SHALL be able to change the family Boolean membership flag; that value SHALL persist across school years until manually changed. The effective membership read surface SHALL follow the selected mode, without clearing the stored manual flag on a mode change.

#### Scenario: Manual state survives a new school year
- **GIVEN** the family flag is true and manual mode is selected
- **WHEN** the school year changes or the mode is switched away and back
- **THEN** the manually stored flag is still true unless a manager changed it.

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
- Which invoices qualify as AFA dues and whether credit notes settle or reduce their entitlement need confirmation; unrelated invoices must not count.
- Current payment-state semantics for refunds/reversals and behavior for multiple qualifying invoices need validation against Odoo 19 and product intent; historical payment timestamps are not required.
- The manual flag is undated and global per family; the setting is assumed database-wide and defaults to invoice mode. Confirm the intended UI/read surface before implementation.
