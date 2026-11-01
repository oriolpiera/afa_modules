# AFA Invoice Receipts

Customer invoice PDFs keep Odoo's standard report action and email attachment,
but present posted invoices as receipts. The report omits tax breakdowns and
shows the total amount; this does not change the invoice's accounting or tax data.

For a valid SEPA Core mandate, the PDF and email show the payer bank name (when
configured) and a masked IBAN with only its last four characters. Without a
usable mandate, they ask the payer to provide bank details or transfer payment
to the company's bank account configured on the invoice, using the invoice
number as the transfer reference.

Install or upgrade this addon together with its `afa_sepa` dependency. The
production company bank account must be configured in Odoo for transfer
instructions to include its IBAN.
