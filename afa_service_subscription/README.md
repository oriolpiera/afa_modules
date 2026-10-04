# Monthly service subscriptions

Staff can enroll students in monthly AFA services and review charges before creating
one draft customer invoice per family and billing month. This module depends on
`afa_membership` and is independent of annual membership dues.

## Configure and bill

1. Give staff the **AFA Family Manager** group. Generating invoices also requires
   **Accounting** access. Install `afa_service_subscription`.
2. Create a school year, then **Monthly Services**. Select a saleable service product,
   complete-month start/end dates and member/non-member monthly prices (before tax).
3. Add join and leave windows with request dates and an effective month. For example,
   September requests can take effect in October; December withdrawal requests can
   take effect in January. Configure dates for each service rather than assuming
   these examples apply everywhere.
4. Under **Service Subscriptions**, create a student enrollment while its join
   window is open. Use **Request Withdrawal** on the subscription to select an open
   leave window. Dates are recorded when the staff action occurs. A withdrawal
   effective in January bills December but not January.
5. Under **Monthly Service Billing**, select the first day of a month and click
   **Refresh Preview**. Review student, service, family, payer, membership tariff,
   unit price (before tax), and any exclusion reason. Uncheck unwanted charges,
   then click **Generate Draft Invoices**. Review and post the Odoo invoices normally.

## Billing rules

- A subscription bills one full month if active on its first day and its service
  covers that month. There is no proration.
- Because each family receives a single invoice per month, its services in the
  same school year must belong to the same Odoo company. Enrollment rejects
  cross-company combinations before they can become unbillable.
- Invoice-mode membership checks the paid, unreversed annual dues link for the
  selected school year when generating; manual mode checks the current family
  manual-member flag. A later change does not change an existing invoice.
- The invoice keeps the billing guardian, price, membership decision, and each
  service charge. Odoo computes taxes from the configured product/fiscal position.
- Repeated billing skips charged subscriptions. New charges for the same family
  and month can be added to its **draft** invoice; after posting, cancel that invoice
  before regenerating the month. Canceled invoices and their original charges
  remain in the history and cannot be reopened. Cancellation uses Odoo's normal
  accounting rules; paid invoices may need reversing/reconciliation first.
- If a future month was already invoiced, cancel its invoice before recording
  a withdrawal effective in that month or earlier.
- Posted unpaid EUR invoices can be collected by `afa_sepa` when the payer has a
  valid mandate and its other eligibility requirements are met.

Run the Odoo 19 test stack as described in the repository README, including
`afa_service_subscription` in the installation list and `/afa_service_subscription`
in `--test-tags`.
