from odoo import fields
from odoo.tests.common import TransactionCase


class TestInvoiceReceipt(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['account.chart.template'].try_loading('generic_coa', cls.env.company)
        cls.sales_journal = cls.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', cls.env.company.id)], limit=1
        )
        cls.bank = cls.env['res.bank'].create({'name': 'Receipt Test Bank'})
        cls.partner = cls.env['res.partner'].create({'name': 'Receipt Payer'})
        cls.company_bank = cls.env['res.partner.bank'].create(
            {
                'partner_id': cls.env.company.partner_id.id,
                'acc_number': 'ES1200000000000000000000',
                'bank_id': cls.bank.id,
            }
        )
        cls.payer_bank = cls.env['res.partner.bank'].create(
            {
                'partner_id': cls.partner.id,
                'acc_number': 'ES52 0182 2782 5688 3882 1868',
                'bank_id': cls.bank.id,
            }
        )
        cls.invoice = cls.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'journal_id': cls.sales_journal.id,
                'partner_id': cls.partner.id,
                'partner_bank_id': cls.company_bank.id,
                'invoice_line_ids': [
                    (0, 0, {'name': 'Family dues', 'quantity': 1, 'price_unit': 120})
                ],
            }
        )

    def test_valid_mandate_exposes_masked_payer_account_and_bank(self):
        mandate = self.env['account.banking.mandate'].create(
            {
                'format': 'sepa',
                'type': 'recurrent',
                'scheme': 'CORE',
                'signature_date': fields.Date.today(),
                'partner_bank_id': self.payer_bank.id,
                'state': 'valid',
                'unique_mandate_reference': 'RECEIPT-TEST-01',
            }
        )

        self.invoice._compute_afa_receipt_bank_details()

        self.assertEqual(self.invoice._afa_receipt_get_mandate(), mandate)
        self.assertEqual(self.invoice.afa_receipt_payer_iban, '****1868')
        self.assertEqual(self.invoice.afa_receipt_payer_bank, 'Receipt Test Bank')
        self.assertFalse(self.invoice.afa_receipt_transfer_iban)

    def test_missing_valid_mandate_uses_company_transfer_account(self):
        self.invoice._compute_afa_receipt_bank_details()

        self.assertFalse(self.invoice.afa_receipt_payer_iban)
        self.assertFalse(self.invoice.afa_receipt_payer_bank)
        self.assertEqual(self.invoice.afa_receipt_transfer_iban, self.company_bank.acc_number)

    def test_customer_invoice_uses_receipt_email_template(self):
        template = self.invoice._get_mail_template()

        self.assertEqual(template, self.env.ref('afa_invoice_receipt.email_template_edi_receipt'))

    def test_customer_report_hides_tax_breakdown_and_shows_transfer_guidance(self):
        self.env.company.vat = 'ES12345678'
        self.partner.vat = 'ES87654321'
        tax = self.env['account.tax'].search(
            [('type_tax_use', '=', 'sale'), ('amount', '>', 0)], limit=1
        )
        if tax:
            self.invoice.invoice_line_ids.tax_ids = [(6, 0, tax.ids)]

        report = self.env.ref('account.account_invoices')
        html, _content_type = report._render_qweb_html('account.account_invoices', self.invoice.ids)
        rendered = html.decode()

        self.assertIn('No tenim un compte bancari on girar-vos el rebut.', rendered)
        self.assertIn(self.company_bank.acc_number, rendered)
        self.assertNotIn('Untaxed Amount', rendered)
        self.assertNotIn('Taxes', rendered)
        self.assertNotIn('ES87654321', rendered)
