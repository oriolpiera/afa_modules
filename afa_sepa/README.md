# AFA SEPA collections

`afa_sepa` prepares family-linked **SEPA Core direct debits** from posted EUR
customer invoices in Odoo 19 Community. OCA bank-payment generates and
XSD-validates the `pain.008` file; the bank's accepted version still needs
confirmation. The existing `pain.001.001.03` used for outgoing transfers does
not determine the direct-debit version.

## Setup

1. Install `afa_sepa` and its OCA dependencies from the pinned bank-payment
   19.0 revision documented in the repository README. Assign the operator
   **AFA Family Manager**, **Accounting User**, and OCA **Payment Orders** access.
   Recording a return requires **Accounting Manager**.
2. Configure a bank journal with the creditor IBAN and SEPA direct debit
   inbound method, and enter the SEPA creditor identifier on the company or
   payment mode. Create an inbound SEPA Core payment mode using that journal;
   **disable Group Lines** so a return can be traced to one invoice.
3. Create a signed, valid SEPA Core mandate attached to an IBAN belonging to
   the **same person billed on the invoice**. Post the dues invoice.
4. From **AFA Families → Prepare SEPA Collections**, select invoices and choose
   **Check Eligibility**. Excluded invoices show a reason. **Create Debit Order**
   opens the OCA order; confirm, generate the XML, and upload it to the bank.
   If another operator reserves an invoice after preview, the wizard shows the
   new exclusion and keeps the other invoices in the order. Use **Open Debit
   Order** to continue with those invoices. If the invoice selection changes,
   check eligibility again; the previous order remains in OCA's debit orders.
   Rechecking the same selection retains the link to its prepared order.
   After a return, recheck eligibility to prepare a replacement order; the
   wizard will open that new order rather than the uploaded one.

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

Each line keeps its original invoice, family, payer, mandate, and order.
Uploaded lines remain reserved even if the invoice is manually unreconciled;
only **Record Return** releases them. The AFA views hide the debtor bank account
from non-accounting managers. Bank data in OCA's other views and downloads
remains subject to Odoo accounting access permissions.

## Local verification

Clone OCA bank-payment 19.0 into `.oca-bank-payment` at the revision in the
repository README, then use an unused test database:

```sh
docker compose -f compose.test.yaml run --rm odoo -d afa_sepa_fresh_example -i afa_family,afa_membership,afa_sepa --test-enable --test-tags /afa_sepa --stop-after-init --log-level=test --db_host=db --db_user=odoo --db_password=odoo
```

Check the final `odoo.tests.result` line; Odoo may return success even when a
test failed. The tests exercise invoice eligibility, payer/mandate validation,
XML generation, duplicate reservation, bank statement matching and a returned
debit reopening the invoice.
