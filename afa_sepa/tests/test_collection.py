import base64

from lxml import etree

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestAfaSepa(TransactionCase):
    def setUp(self):
        super().setUp()
        company = self.env['res.company'].create(
            {
                'name': 'AFA SEPA test company',
                'currency_id': self.env.ref('base.EUR').id,
                'sepa_creditor_identifier': 'FR78ZZZ424242',
            }
        )
        self.env.user.write(
            {
                'company_ids': [(4, company.id)],
                'company_id': company.id,
            }
        )
        self.env = self.env(context=dict(self.env.context, allowed_company_ids=[company.id]))
        self.assertEqual(self.env.company, company)
        self.env['account.chart.template'].try_loading('generic_coa', self.env.company)
        self.env.user.group_ids |= self.env.ref('afa_family.group_family_manager')
        self.env.user.group_ids |= self.env.ref('account.group_account_user')
        self.env.user.group_ids |= self.env.ref('account_payment_order.group_account_payment')
        self.env.user.group_ids |= self.env.ref('account.group_account_manager')
        receivable = self.env['account.account'].search(
            [('account_type', '=', 'asset_receivable')], limit=1
        )
        self.assertTrue(receivable)
        outstanding = self.env['account.account'].create(
            {
                'name': 'AFA outstanding collections',
                'code': 'AFAS01',
                'account_type': 'asset_current',
                'reconcile': True,
            }
        )
        guardian = self.env['res.partner'].create(
            {
                'name': 'AFA payer',
                'afa_family_role': 'guardian',
                'property_account_receivable_id': receivable.id,
            }
        )
        self.family = self.env['afa.family'].create(
            {
                'name': 'SEPA test family',
                'billing_partner_id': guardian.id,
            }
        )
        bank = self.env['res.bank'].create({'name': 'Test bank', 'bic': 'PSSTFRPPXXX'})
        creditor_bank = self.env['res.partner.bank'].create(
            {
                'partner_id': self.env.company.partner_id.id,
                'acc_number': 'ES52 0182 2782 5688 3882 1868',
                'bank_id': bank.id,
            }
        )
        payer_bank = self.env['res.partner.bank'].create(
            {
                'partner_id': guardian.id,
                'acc_number': 'FR76 3000 6000 0112 3456 7890 189',
                'bank_id': bank.id,
            }
        )
        payer_bank._compute_acc_type()
        method = self.env.ref('account_banking_sepa_direct_debit.sepa_direct_debit')
        self.journal = self.env['account.journal'].create(
            {
                'name': 'AFA SEPA test bank',
                'code': 'AFAB',
                'type': 'bank',
                'bank_account_id': creditor_bank.id,
                'suspense_account_id': outstanding.id,
                'inbound_payment_method_line_ids': [
                    (
                        0,
                        0,
                        {
                            'payment_method_id': method.id,
                            'payment_account_id': outstanding.id,
                        },
                    )
                ],
            }
        )
        self.mode = self.env['account.payment.mode'].create(
            {
                'name': 'AFA SEPA Core',
                'bank_account_link': 'fixed',
                'fixed_journal_id': self.journal.id,
                'payment_method_id': method.id,
                'group_lines': False,
            }
        )
        self.mandate = self.env['account.banking.mandate'].create(
            {
                'format': 'sepa',
                'type': 'recurrent',
                'scheme': 'CORE',
                'signature_date': fields.Date.today(),
                'partner_bank_id': payer_bank.id,
                'state': 'valid',
                'unique_mandate_reference': 'AFA-TEST-01',
            }
        )
        product = self.env['product.product'].create(
            {
                'name': 'SEPA dues',
                'list_price': 120,
            }
        )
        period = self.env['afa.membership.period'].create(
            {
                'name': 'SEPA test period',
                'date_start': '2026-07-01',
                'date_end': '2027-06-30',
            }
        )
        link = self.env['afa.membership'].create(
            {
                'family_id': self.family.id,
                'period_id': period.id,
            }
        )
        self.invoice = link.action_create_dues_invoice(product)
        self.invoice.currency_id = self.env.ref('base.EUR')
        self.invoice.action_post()
        self.wizard = self.env['afa.sepa.wizard'].create(
            {
                'invoice_ids': [(6, 0, self.invoice.ids)],
                'payment_mode_id': self.mode.id,
                'journal_id': self.journal.id,
            }
        )
        self.assertEqual(self.mandate.partner_bank_id.acc_type, 'iban')

    def test_xml_duplicate_and_return(self):
        self.wizard.action_preview()
        self.assertTrue(self.wizard.line_ids.eligible, self.wizard.line_ids.reason)
        action = self.wizard.action_prepare()
        order = self.env['account.payment.order'].browse(action['res_id'])
        line = order.payment_line_ids
        self.assertEqual(line.afa_family_id, self.family)
        self.assertEqual(line.move_line_id.move_id, self.invoice)
        self.assertEqual(line.mandate_id, self.mandate)
        self.assertEqual(line.partner_bank_id, self.mandate.partner_bank_id)
        self.wizard.action_preview()
        self.assertFalse(self.wizard.line_ids.eligible)
        self.assertIn('already', self.wizard.line_ids.reason)
        order.draft2open()
        action = order.open2generated()
        attachment = self.env['ir.attachment'].browse(action['res_id'])
        xml = base64.b64decode(attachment.datas)
        root = etree.fromstring(xml)
        self.assertIn('pain.008.001.02', root.nsmap[None])
        self.assertIn(b'AFA-TEST-01', xml)
        self.assertIn(
            f'<InstdAmt Ccy="EUR">{self.invoice.amount_residual:.2f}</InstdAmt>'.encode(),
            xml,
        )
        order.generated2uploaded()
        self.assertIn(self.invoice.payment_state, ('paid', 'in_payment'))
        with self.assertRaises(UserError):
            order.action_cancel()
        with self.assertRaises(UserError):
            order.write({'state': 'cancel'})
        line.move_line_id.remove_move_reconcile()
        self.wizard.action_preview()
        self.assertFalse(self.wizard.line_ids.eligible)
        self.assertIn('already', self.wizard.line_ids.reason)
        line.action_record_return()
        self.assertTrue(line.afa_returned)
        self.assertGreater(self.invoice.amount_residual, 0)
        self.assertNotEqual(self.invoice.payment_state, 'paid')
        replacement = self.env['account.payment.order'].browse(
            self.wizard.action_prepare()['res_id']
        )
        self.assertEqual(replacement.payment_line_ids.move_line_id, line.move_line_id)
        self.assertNotEqual(replacement, order)

    def test_wrong_payer_and_invalid_mandate_are_excluded(self):
        other = self.env['res.partner'].create({'name': 'Different debtor'})
        self.mandate.partner_bank_id.partner_id = other
        self.wizard.action_preview()
        self.assertFalse(self.wizard.line_ids.eligible)
        self.assertIn('mandate', self.wizard.line_ids.reason)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            order = self.env['account.payment.order'].create(
                {
                    'payment_mode_id': self.mode.id,
                    'journal_id': self.journal.id,
                }
            )
            move_line = self.invoice.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
            )
            self.env['account.payment.line'].create(
                {
                    **move_line._prepare_payment_line_vals(order),
                    'mandate_id': self.mandate.id,
                    'partner_id': self.invoice.partner_id.id,
                    'partner_bank_id': self.mandate.partner_bank_id.id,
                }
            )

    def test_no_mandate_does_not_create_an_order(self):
        self.mandate.state = 'cancel'
        self.wizard.action_preview()
        self.assertFalse(self.wizard.line_ids.eligible)
        result = self.wizard.action_prepare()
        self.assertEqual(result['res_model'], 'afa.sepa.wizard')

    def test_cancelled_invoice_mandate_uses_valid_replacement(self):
        self.invoice.mandate_id = self.mandate
        self.mandate.state = 'cancel'
        replacement = self.mandate.copy(
            {
                'state': 'valid',
                'unique_mandate_reference': 'AFA-TEST-02',
                'signature_date': fields.Date.today(),
            }
        )
        self.wizard.action_preview()
        self.assertTrue(self.wizard.line_ids.eligible, self.wizard.line_ids.reason)
        order = self.env['account.payment.order'].browse(self.wizard.action_prepare()['res_id'])
        self.assertEqual(order.payment_line_ids.mandate_id, replacement)
        self.assertEqual(self.invoice.mandate_id, self.mandate)

    def test_imported_bank_credit_reconciles_with_order_payment(self):
        self.wizard.action_preview()
        order = self.env['account.payment.order'].browse(self.wizard.action_prepare()['res_id'])
        order.draft2open()
        order.open2generated()
        order.generated2uploaded()
        payment = order.payment_ids
        statement = self.env['account.bank.statement.line'].create(
            {
                'journal_id': self.journal.id,
                'date': fields.Date.today(),
                'payment_ref': order.name,
                'partner_id': self.invoice.partner_id.id,
                'amount': payment.amount,
            }
        )
        outstanding = payment.move_id.line_ids.filtered(
            lambda l: l.account_id == self.journal.suspense_account_id and not l.reconciled
        )
        statement_outstanding = statement.move_id.line_ids.filtered(
            lambda l: l.account_id == self.journal.suspense_account_id and not l.reconciled
        )
        self.assertEqual(len(outstanding), 1)
        self.assertEqual(len(statement_outstanding), 1)
        (outstanding + statement_outstanding).reconcile()
        self.assertTrue(outstanding.reconciled)
        self.assertTrue(statement_outstanding.reconciled)
        order.payment_line_ids.action_record_return()
        self.assertGreater(self.invoice.amount_residual, 0)
        returned_statement = self.env['account.bank.statement.line'].create(
            {
                'journal_id': self.journal.id,
                'date': fields.Date.today(),
                'payment_ref': f'{order.name} returned',
                'partner_id': self.invoice.partner_id.id,
                'amount': -payment.amount,
            }
        )
        return_outstanding = returned_statement.move_id.line_ids.filtered(
            lambda l: l.account_id == self.journal.suspense_account_id and not l.reconciled
        )
        self.assertEqual(len(return_outstanding), 1)
        self.assertFalse(statement_outstanding.reconciled)
        (statement_outstanding + return_outstanding).reconcile()
        self.assertTrue(return_outstanding.reconciled)
        self.assertNotEqual(self.invoice.payment_state, 'paid')
