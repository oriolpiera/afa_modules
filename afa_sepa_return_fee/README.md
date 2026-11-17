# AFA SEPA return fee billing

When an AFA SEPA debit is returned, `afa_sepa` records the configured fee amount
against that debit. If the fee is still pending when Acollida or extracurricular
billing generates a family invoice, this addon adds it as a separate invoice
line, without taxes. The line identifies the original invoice.

The fee amount is configured per company under **Accounting → Settings → AFA
SEPA**. The default is 4.00 in the company's currency; setting it to zero disables
new fees. The amount is snapshotted when a return is recorded, so changing the
setting does not alter already-recorded fees.

Accountants can review them under **Invoicing → Customers → SEPA Return Fees**.
The list opens with **Pending** selected; use **Invoiced** to review fees already
attached to an invoice.

Only draft invoices for the same family, payer, and company, dated on or after
the return, can receive a pending fee. If a generated invoice is later cancelled
or deleted, its fee becomes pending again for a future invoice.

The fee invoice line is explicitly created without taxes. Confirm the applicable
tax treatment and the authorization to recover the fee with the association's
accountant before charging families.
