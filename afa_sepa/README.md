# AFA SEPA collections

`afa_sepa` prepares family-linked **SEPA Core direct debits** from posted EUR
customer invoices in Odoo 19 Community. OCA bank-payment generates and
XSD-validates the `pain.008` file; the bank's accepted version still needs
confirmation. The existing `pain.001.001.03` used for outgoing transfers does
not determine the direct-debit version.

## Setup

1. Install `afa_sepa` and its OCA dependencies from the pinned bank-payment
   and account-payment 19.0 revisions documented in the repository README. This
   includes the ISO 20022 payment-return importer for PAIN.002.001.03. Assign
   the operator **AFA Family Manager**, **Accounting User**, and OCA **Payment
   Orders** access. When Acollida and extracurricular billing are installed,
   `afa_sepa_return_fee` is auto-installed as their return-fee integration.
   Recording a return requires **Accounting Manager**.
2. Configure a bank journal with the creditor IBAN and SEPA direct debit
   inbound method, and enter the SEPA creditor identifier on the company or
   payment mode. Create an inbound SEPA Core payment mode using that journal;
   **disable Group Lines** so a return can be traced to one invoice.
3. Create a signed, valid SEPA Core mandate attached to an IBAN belonging to
   the **same person billed on the invoice**. Post the dues invoice.
4. From **AFA Families → Collections → Prepare SEPA Collections**, select invoices
   and choose **Check Eligibility**. Excluded invoices show a reason. **Create
   Debit Order** opens the OCA order; confirm, generate the XML, and upload it to
   the bank.
   If another operator reserves an invoice after preview, the wizard shows the
   new exclusion and keeps the other invoices in the order. Use **Open Debit
   Order** to continue with those invoices. If the invoice selection changes,
   check eligibility again; the previous order remains in OCA's debit orders.
   Rechecking the same selection retains the link to its prepared order.
   After a return, recheck eligibility to prepare a replacement order; the
   wizard will open that new order rather than the uploaded one.

## Families with multiple payer IBANs

Most families need no additional setup: when exactly one usable mandate exists,
the collection wizard uses it. For a family with multiple valid mandates, open
the family and add assignments on **SEPA Mandates**, per company:

- **Default** applies to billing types without a specific assignment.
- **Acollida** and **Extracurricular Activities** override the default for those
  invoices.

If an assigned mandate is no longer valid, the affected invoice is excluded; the
wizard never redirects it to another IBAN. If multiple valid mandates exist but
the invoice has no unambiguous assignment, the wizard asks for configuration.
When a family has a specific extracurricular assignment, monthly service billing
separates those charges from other services. An Acollida assignment is billed on
its own invoice. This keeps ordinary families' invoices grouped while ensuring
the exceptional family's invoices can use the intended mandates. Any existing
invoice containing types assigned to different mandates must be canceled and
rebilled into separate invoices before collection.

The pinned OCA module defaults to `pain.008.001.02`; its payment method allows
other supported `pain.008` versions. Verify the version, creditor identifier,
requested collection date, and a sample file with the actual bank before use.
Passing OCA's XSD validation does not mean the bank accepted a file.

## Bank result and returns

OCA posts a payment and reconciles the invoice when the order is marked **File
Successfully Uploaded**. This is earlier than bank confirmation. Import the
bank's credit statement and reconcile its outstanding entry against the order
payment. For a returned debit, open its line and use **Record Return**: this
cancels that payment, unreconciles and reopens the invoice, and releases its
balance for a future order. Import the bank's debit statement as well and
reconcile it against the original bank credit as appropriate. Do not cancel an
uploaded order while it contains unresolved AFA debits. If the bank applies
fees, account for them separately.

Recording a returned annual dues debit suspends the family's membership while
that dues invoice remains unpaid. A later successful payment of the same invoice
restores membership. Returned course or service debits do not change membership.

The OCA **Import Payment Return** wizard can read PAIN.002.001.03 files. Import
creates a draft return for review; when confirming a return whose every line
matches one full AFA debit, AFA runs the same **Record Return** action. This
cancels the payment, reopens the invoice, releases its reservation, and applies
the membership return rules. Mixed or unmatched returns, partial amounts, and
bank charges are rejected for AFA processing; split or handle those separately.
The importer does not create a generic return journal entry for an AFA return.
Account for the bank debit through the bank statement.

After a return is successfully recorded, Odoo queues one email per invoice
payer, grouping that payer's returned invoices from the same operation. It
states that the original invoices are open again and, when applicable, that the
return fee will appear on a future eligible invoice. The payer must have an
email address on their contact record.

The return fee is configured per company under **Accounting → Settings → AFA
SEPA**. It defaults to 4.00 in the company's currency; setting it to zero
disables new fees. The amount is saved on each return and added as a separate,
untaxed line to the next Acollida or extracurricular invoice generated for the
same family, payer, and company. If an invoice is cancelled, the fee remains
pending for a later invoice. Accountants can review fees under **Invoicing →
Customers → SEPA Return Fees**, with pending fees shown by default. Fees that
should not be charged — for example a return caused by the association's own
bank data — can be cancelled from the fee form with **Cancel Fee**. Cancelled
fees stay out of future invoices, remain in history, and can be restored with
**Set Pending Again**; managers can only change fees belonging to companies
they are allowed to access. Fees are auditable history and cannot be deleted;
cancellation is the supported way to disable one.

Each line keeps its original invoice, family, payer, mandate, and order.
Uploaded lines remain reserved even if the invoice is manually unreconciled;
only **Record Return** releases them. The AFA views hide the debtor bank account
from non-accounting managers. Bank data in OCA's other views and downloads
remains subject to Odoo accounting access permissions.

## Local verification

Clone OCA bank-payment 19.0 into `.oca-bank-payment` at the revision in the
repository README, then use an unused test database:

```sh
docker compose -f compose.test.yaml run --rm odoo -d afa_sepa_fresh_example -i afa_family,afa_membership,afa_sepa_return_fee --test-enable --test-tags /afa_sepa --stop-after-init --log-level=test --db_host=db --db_user=odoo --db_password=odoo
```

Check the final `odoo.tests.result` line; Odoo may return success even when a
test failed. The tests exercise invoice eligibility, payer/mandate validation,
XML generation, duplicate reservation, bank statement matching and a returned
debit reopening the invoice.
