import base64
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from lxml import etree

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
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

    def _import_payment_return(self, payment, amount=None):
        amount = payment.amount if amount is None else amount
        creditor_iban = self.journal.bank_account_id.acc_number.replace(' ', '')
        debtor_iban = self.mandate.partner_bank_id.acc_number.replace(' ', '')
        today = fields.Date.to_string(fields.Date.today())
        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.002.001.03">
  <CstmrPmtStsRpt>
    <GrpHdr>
      <MsgId>AFA-RETURN-{payment.id}</MsgId>
      <CreDtTm>{today}T12:00:00</CreDtTm>
    </GrpHdr>
    <OrgnlPmtInfAndSts>
      <TxInfAndSts>
        <OrgnlEndToEndId>{payment.id}</OrgnlEndToEndId>
        <TxSts>RJCT</TxSts>
        <StsRsnInf><Rsn><Cd>AM04</Cd></Rsn></StsRsnInf>
        <OrgnlTxRef>
          <Amt><InstdAmt Ccy="EUR">{amount:.2f}</InstdAmt></Amt>
          <ReqdColltnDt>{today}</ReqdColltnDt>
          <RmtInf><Ustrd>{self.invoice.name}</Ustrd></RmtInf>
          <Dbtr><Nm>{self.invoice.partner_id.name}</Nm></Dbtr>
          <DbtrAcct><Id><IBAN>{debtor_iban}</IBAN></Id></DbtrAcct>
          <CdtrAcct><Id><IBAN>{creditor_iban}</IBAN></Id></CdtrAcct>
        </OrgnlTxRef>
      </TxInfAndSts>
    </OrgnlPmtInfAndSts>
  </CstmrPmtStsRpt>
</Document>"""
        importer = self.env['payment.return.import'].create(
            {'data_file': base64.b64encode(xml.encode())}
        )
        action = importer.import_file()
        return self.env['payment.return'].browse(action['res_id'])

    def _record_returned_debit(self):
        self.wizard.action_preview()
        order = self.env['account.payment.order'].browse(self.wizard.action_prepare()['res_id'])
        order.draft2open()
        order.open2generated()
        order.generated2uploaded()
        line = order.payment_line_ids.ensure_one()
        line.action_record_return()
        return line, self.env['afa.sepa.return.fee'].search([('payment_line_id', '=', line.id)])

    def _skip_if_return_fee_billing_is_not_installed(self):
        module = self.env['ir.module.module'].search(
            [('name', '=', 'afa_sepa_return_fee'), ('state', '=', 'installed')], limit=1
        )
        if not module:
            self.skipTest('afa_sepa_return_fee is not installed')

    def test_wizard_preserves_orm_access_check_signature(self):
        operator = self.env['res.users'].create(
            {
                'name': 'SEPA Operator',
                'login': 'afa_sepa_operator',
                'group_ids': [
                    (
                        6,
                        0,
                        [
                            self.env.ref('afa_family.group_family_manager').id,
                            self.env.ref('account.group_account_user').id,
                            self.env.ref('account_payment_order.group_account_payment').id,
                        ],
                    )
                ],
            }
        )
        self.env['afa.sepa.wizard'].with_user(operator).check_access('read')

    def test_xml_duplicate_and_return(self):
        self.family.manual_member = True
        self.assertTrue(self.family.is_member)
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
        self.assertEqual(self.invoice.afa_membership_id.returned_dues_invoice_id, self.invoice)
        self.assertFalse(self.family.is_member)

        replacement = self.env['account.payment.order'].browse(
            self.wizard.action_prepare()['res_id']
        )
        self.assertEqual(replacement.payment_line_ids.move_line_id, line.move_line_id)
        self.assertNotEqual(replacement, order)

    def test_imported_pain_return_runs_afa_return_action(self):
        self.wizard.action_preview()
        order = self.env['account.payment.order'].browse(self.wizard.action_prepare()['res_id'])
        order.draft2open()
        order.open2generated()
        order.generated2uploaded()
        payment = order.payment_ids.ensure_one()
        line = order.payment_line_ids.ensure_one()
        self.invoice.partner_id.email = 'payer@example.test'

        payment_return = self._import_payment_return(payment)

        self.assertEqual(payment_return.state, 'draft')
        self.assertSetEqual(
            set(payment_return.line_ids.move_line_ids.ids),
            set(
                payment.move_id.line_ids.filtered(
                    lambda aml: (
                        aml.account_id == payment.destination_account_id
                        and aml.partner_id == payment.partner_id
                    )
                ).ids
            ),
        )
        payment_return.action_confirm()

        self.assertEqual(payment_return.state, 'done')
        self.assertTrue(payment_return.afa_processed)
        self.assertFalse(payment_return.move_id)
        self.assertEqual(payment.state, 'canceled')
        self.assertFalse(line.move_line_id.reconciled)
        self.assertEqual(self.invoice.amount_residual, self.invoice.amount_total)
        self.assertTrue(line.afa_returned)
        fee = self.env['afa.sepa.return.fee'].search([('payment_line_id', '=', line.id)], limit=1)
        self.assertEqual(fee.amount, 4)
        notification = self.env['afa.sepa.return.notification'].search(
            [('payment_return_id', '=', payment_return.id)]
        )
        self.assertEqual(len(notification), 1)
        self.assertEqual(notification.state, 'queued')
        mail = self.env['mail.mail'].search(
            [
                ('model', '=', 'afa.sepa.return.notification'),
                ('res_id', '=', notification.id),
            ],
            limit=1,
        )
        self.assertEqual(mail.email_to, 'payer@example.test')
        self.assertIn(self.invoice.name, mail.body_html)
        self.assertIn('4.0', mail.body_html)
        self.assertEqual(self.invoice.afa_membership_id.returned_dues_invoice_id, self.invoice)
        self.assertFalse(self.family.is_member)
        with self.assertRaises(UserError):
            payment_return.action_cancel()
        with self.assertRaises(UserError):
            payment_return.action_draft()

    def test_imported_partial_afa_return_is_rejected_before_processing(self):
        self.wizard.action_preview()
        order = self.env['account.payment.order'].browse(self.wizard.action_prepare()['res_id'])
        order.draft2open()
        order.open2generated()
        order.generated2uploaded()
        payment = order.payment_ids.ensure_one()
        line = order.payment_line_ids.ensure_one()
        payment_return = self._import_payment_return(payment, payment.amount - 1)

        with self.assertRaises(UserError):
            payment_return.action_confirm()

        self.assertEqual(payment_return.state, 'draft')
        self.assertFalse(payment_return.afa_processed)
        self.assertNotEqual(payment.state, 'canceled')
        self.assertTrue(line.move_line_id.reconciled)
        self.assertEqual(self.invoice.amount_residual, 0)
        self.assertFalse(line.afa_returned)

    def test_return_email_groups_multiple_returns_for_the_same_payer(self):
        self.invoice.partner_id.email = 'payer@example.test'
        product = self.env['product.product'].create(
            {'name': 'Second SEPA test dues', 'list_price': 45}
        )
        second_invoice = self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.invoice.partner_id.id,
                'company_id': self.env.company.id,
                'currency_id': self.env.ref('base.EUR').id,
                'invoice_line_ids': [
                    (0, 0, {'product_id': product.id, 'quantity': 1, 'price_unit': 45})
                ],
            }
        )
        second_invoice.action_post()
        self.wizard.invoice_ids = [(6, 0, (self.invoice | second_invoice).ids)]
        self.wizard.action_preview()
        order = self.env['account.payment.order'].browse(self.wizard.action_prepare()['res_id'])
        order.draft2open()
        order.open2generated()
        order.generated2uploaded()

        return_lines = []
        for payment in order.payment_ids:
            payment_line = payment.payment_line_ids.ensure_one()
            receivable = payment.move_id.line_ids.filtered(
                lambda line, payment=payment: (
                    line.account_id == payment.destination_account_id
                    and line.partner_id == payment.partner_id
                )
            )
            return_lines.append(
                (
                    0,
                    0,
                    {
                        'reference': str(payment.id),
                        'partner_id': payment.partner_id.id,
                        'amount': payment.amount,
                        'move_line_ids': [(6, 0, receivable.ids)],
                    },
                )
            )
            self.assertEqual(payment_line.partner_id, self.invoice.partner_id)
        payment_return = self.env['payment.return'].create(
            {
                'company_id': self.env.company.id,
                'journal_id': self.journal.id,
                'line_ids': return_lines,
            }
        )

        payment_return.action_confirm()

        notification = self.env['afa.sepa.return.notification'].search(
            [('payment_return_id', '=', payment_return.id)]
        )
        self.assertEqual(len(notification), 1)
        self.assertEqual(len(notification.line_ids), 2)
        self.assertEqual(notification.total_fee_amount, 8)
        mail = self.env['mail.mail'].search(
            [
                ('model', '=', 'afa.sepa.return.notification'),
                ('res_id', '=', notification.id),
            ],
            limit=1,
        )
        self.assertEqual(mail.email_to, 'payer@example.test')
        self.assertIn(self.invoice.name, mail.body_html)
        self.assertIn(second_invoice.name, mail.body_html)

    def test_return_fee_uses_company_setting_and_snapshots_amount(self):
        settings = self.env['res.config.settings'].create(
            {
                'company_id': self.env.company.id,
                'afa_sepa_return_fee_amount': 6.5,
            }
        )
        settings.set_values()

        line, fee = self._record_returned_debit()

        self.assertEqual(self.env.company.afa_sepa_return_fee_amount, 6.5)
        self.assertEqual(len(fee), 1)
        self.assertEqual(fee.amount, 6.5)
        self.assertEqual(fee.currency_id, line.company_id.currency_id)
        self.assertEqual(fee.state, 'pending')

    def test_zero_return_fee_setting_disables_new_fees(self):
        self.env.company.afa_sepa_return_fee_amount = 0

        line, fee = self._record_returned_debit()

        self.assertTrue(line.afa_returned)
        self.assertFalse(fee)

    def test_return_fee_menu_has_pending_and_invoiced_filters(self):
        action = self.env.ref('afa_sepa.action_afa_sepa_return_fee')
        menu = self.env.ref('afa_sepa.menu_afa_sepa_return_fee')
        search_view = self.env.ref('afa_sepa.view_afa_sepa_return_fee_search')

        self.assertEqual(menu.action, action)
        self.assertIn('search_default_filter_pending', action.context)
        self.assertIn('filter_pending', search_view.arch_db)
        self.assertIn('filter_invoiced', search_view.arch_db)
        self.assertIn('filter_cancelled', search_view.arch_db)

    def test_return_fee_cancellation_skips_billing_and_keeps_history(self):
        line, fee = self._record_returned_debit()
        self.assertEqual(fee.state, 'pending')

        fee.action_cancel()

        self.assertEqual(fee.state, 'cancelled')
        self.assertEqual(fee.cancel_date, fields.Date.context_today(fee))
        self.assertNotIn(fee, self.env['afa.sepa.return.fee'].search([('state', '=', 'pending')]))
        self.assertEqual(self.env['afa.sepa.return.fee'].sudo().register_return(line), fee)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            fee.action_cancel()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            fee.write({'cancel_date': False})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            fee.unlink()
        self.assertTrue(fee.exists())

        fee.action_set_pending()

        self.assertEqual(fee.state, 'pending')
        self.assertFalse(fee.cancel_date)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            fee.action_set_pending()

    def test_invoiced_return_fee_cannot_be_cancelled(self):
        _line, fee = self._record_returned_debit()
        income = self.invoice.invoice_line_ids.account_id.ensure_one()
        invoice = (
            self.env['account.move']
            .with_context(_afa_generate_service_invoices=True)
            .create(
                {
                    'move_type': 'out_invoice',
                    'partner_id': fee.partner_id.id,
                    'company_id': fee.company_id.id,
                    'invoice_date': fee.returned_date,
                    'afa_service_family_id': fee.family_id.id,
                    'invoice_line_ids': [
                        (
                            0,
                            0,
                            {
                                'product_id': self.env.ref(
                                    'afa_sepa.product_sepa_return_fee'
                                ).product_variant_id.id,
                                'account_id': income.id,
                                'quantity': 1,
                                'price_unit': fee.amount,
                                'tax_ids': [(6, 0, [])],
                            },
                        )
                    ],
                }
            )
        )
        fee_line = invoice.invoice_line_ids.ensure_one()
        fee.with_context(_afa_link_sepa_return_fee=True).write({'invoice_line_id': fee_line.id})
        self.assertEqual(fee.state, 'invoiced')

        with self.assertRaises(ValidationError), self.cr.savepoint():
            fee.action_cancel()
        self.assertEqual(fee.state, 'invoiced')

        invoice.button_cancel()
        self.assertEqual(fee.state, 'pending')
        fee.action_cancel()
        self.assertEqual(fee.state, 'cancelled')
        with self.assertRaises(ValidationError), self.cr.savepoint():
            fee.with_context(_afa_link_sepa_return_fee=True).write({'invoice_line_id': fee_line.id})

    def test_non_manager_cannot_change_return_fee_state(self):
        _line, fee = self._record_returned_debit()
        accountant = self.env['res.users'].create(
            {
                'name': 'SEPA Accountant',
                'login': 'afa_sepa_accountant',
                'group_ids': [
                    (
                        6,
                        0,
                        [
                            self.env.ref('account.group_account_user').id,
                            self.env.ref('account_payment_order.group_account_payment').id,
                        ],
                    )
                ],
            }
        )

        with self.assertRaises(AccessError), self.cr.savepoint():
            fee.with_user(accountant).action_cancel()
        self.assertEqual(fee.state, 'pending')

    def test_return_fee_actions_need_company_access(self):
        _line, fee = self._record_returned_debit()
        outsider = (
            self.env['res.users']
            .with_context(allowed_company_ids=[self.env.ref('base.main_company').id])
            .create(
                {
                    'name': 'Foreign SEPA Manager',
                    'login': 'afa_sepa_foreign_manager',
                    'company_ids': [(6, 0, [self.env.ref('base.main_company').id])],
                    'group_ids': [
                        (
                            6,
                            0,
                            [
                                self.env.ref('base.group_user').id,
                                self.env.ref('account.group_account_manager').id,
                            ],
                        )
                    ],
                }
            )
        )

        with self.assertRaises(AccessError), self.cr.savepoint():
            fee.with_user(outsider).action_cancel()
        with self.assertRaises(AccessError), self.cr.savepoint():
            fee.with_user(outsider).with_context(_afa_cancel_sepa_return_fee=True).write(
                {'cancel_date': fields.Date.today()}
            )
        self.assertEqual(fee.state, 'pending')

    def test_cancelled_return_fee_skips_the_billing_pipeline_until_reopened(self):
        _line, fee = self._record_returned_debit()
        income = self.invoice.invoice_line_ids.account_id.ensure_one()
        self.env.ref('afa_sepa.product_sepa_return_fee').property_account_income_id = income
        fee.action_cancel()
        invoice = (
            self.env['account.move']
            .with_context(_afa_generate_service_invoices=True)
            .create(
                {
                    'move_type': 'out_invoice',
                    'partner_id': fee.partner_id.id,
                    'company_id': fee.company_id.id,
                    'invoice_date': fee.returned_date,
                    'afa_service_family_id': fee.family_id.id,
                }
            )
        )

        fee_model = type(fee)
        with patch.object(fee_model, '_is_return_fee_invoice', return_value=True):
            self.env['afa.sepa.return.fee'].sudo().invoice_pending_fees(invoice)

        self.assertEqual(fee.state, 'cancelled')
        self.assertFalse(fee.invoice_line_id)
        invoice.invalidate_recordset(['invoice_line_ids'])
        self.assertFalse(invoice.invoice_line_ids.filtered('product_id'))

        fee.action_set_pending()
        with patch.object(fee_model, '_is_return_fee_invoice', return_value=True):
            self.env['afa.sepa.return.fee'].sudo().invoice_pending_fees(invoice)

        self.assertEqual(fee.state, 'invoiced')
        self.assertEqual(fee.invoice_line_id.move_id, invoice)
        self.assertEqual(fee.invoice_line_id.price_unit, fee.amount)
        self.assertFalse(fee.invoice_line_id.tax_ids)

    def test_return_fee_is_added_untaxed_to_next_acollida_invoice(self):
        self._skip_if_return_fee_billing_is_not_installed()
        _payment_line, fee = self._record_returned_debit()
        sale_journal = self.env['account.journal'].search(
            [('company_id', '=', self.env.company.id), ('type', '=', 'sale')], limit=1
        )
        product = self.env['product.product'].create(
            {'name': 'Acollida return-fee test charge', 'type': 'service'}
        )
        product.with_company(
            self.env.company
        ).property_account_income_id = sale_journal.default_account_id
        period = self.invoice.afa_membership_id.period_id
        config = self.env['afa.acollida.config'].create(
            {
                'period_id': period.id,
                'product_id': product.id,
                'invoice_journal_id': sale_journal.id,
                'payment_mode_id': self.mode.id,
                'company_id': self.env.company.id,
            }
        )
        self.env['afa.acollida.charge'].with_context(_afa_import_acollida_charges=True).create(
            {
                'config_id': config.id,
                'family_id': self.family.id,
                'month': '2026-12-01',
                'amount': 18,
            }
        )
        billing = self.env['afa.acollida.billing'].create({'month': '2026-12-01'})
        billing.action_preview()
        self.assertEqual(fee.state, 'pending')

        result = billing.action_generate()
        invoice = self.env['account.move'].browse(result['domain'][0][2][0])

        fee.invalidate_recordset(['invoice_line_id', 'state'])
        self.assertEqual(len(fee), 1)
        self.assertEqual(fee.state, 'invoiced')
        self.assertEqual(fee.family_id, invoice.afa_service_family_id)
        self.assertEqual(fee.partner_id, invoice.partner_id)
        self.assertEqual(fee.company_id, invoice.company_id)
        self.assertEqual(fee.currency_id, invoice.currency_id)
        self.assertEqual(fee.invoice_line_id.move_id, invoice)
        self.assertGreaterEqual(invoice.invoice_date, fee.returned_date)
        self.env['afa.sepa.return.fee'].sudo().invoice_pending_fees(invoice)
        invoice.invalidate_recordset(['invoice_line_ids'])
        self.assertEqual(sorted(invoice.invoice_line_ids.mapped('price_unit')), [4, 18])
        self.assertFalse(fee.invoice_line_id.tax_ids)
        self.assertIn(self.invoice.name, fee.invoice_line_id.name)

    def test_return_fee_is_added_untaxed_to_next_extracurricular_invoice(self):
        self._skip_if_return_fee_billing_is_not_installed()
        _payment_line, fee = self._record_returned_debit()
        sale_journal = self.env['account.journal'].search(
            [('company_id', '=', self.env.company.id), ('type', '=', 'sale')], limit=1
        )
        product = self.env['product.product'].create(
            {'name': 'Extracurricular return-fee test charge', 'type': 'service'}
        )
        product.with_company(
            self.env.company
        ).property_account_income_id = sale_journal.default_account_id
        period = self.invoice.afa_membership_id.period_id
        service = self.env['afa.service'].create(
            {
                'name': 'Return Fee Test Activity',
                'period_id': period.id,
                'date_start': '2026-11-01',
                'date_end': '2027-06-30',
                'product_id': product.id,
                'invoice_journal_id': sale_journal.id,
                'payment_mode_id': self.mode.id,
                'member_price': 20,
                'nonmember_price': 20,
                'is_extracurricular': True,
                'enrollment_date_start': '2026-11-01',
                'enrollment_date_end': '2026-11-30',
            }
        )
        group = self.env['afa.service.group'].create(
            {'service_id': service.id, 'name': 'Return Fee Test Group', 'capacity': 5}
        )
        self.env['afa.service.group.schedule'].create(
            {
                'group_id': group.id,
                'weekday': '3',
                'hour_from': 12.5,
                'hour_to': 13.5,
            }
        )
        window = self.env['afa.service.window'].create(
            {
                'service_id': service.id,
                'kind': 'join',
                'date_start': '2026-11-01',
                'date_end': '2026-11-30',
                'effective_month': '2026-11-01',
            }
        )
        student = self.env['res.partner'].create(
            {
                'name': 'Return Fee Test Student',
                'afa_family_id': self.family.id,
                'afa_family_role': 'student',
            }
        )
        with patch('odoo.fields.Date.context_today', return_value=date(2026, 11, 17)):
            self.env['afa.service.subscription'].create(
                {
                    'service_id': service.id,
                    'student_id': student.id,
                    'join_window_id': window.id,
                    'group_id': group.id,
                }
            )
        self.env['afa.sepa.mandate.rule'].create(
            {
                'family_id': self.family.id,
                'company_id': self.env.company.id,
                'purpose': 'extracurricular',
                'mandate_id': self.mandate.id,
            }
        )
        regular_invoice = (
            self.env['account.move']
            .with_context(_afa_generate_service_invoices=True)
            .create(
                {
                    'move_type': 'out_invoice',
                    'partner_id': self.family.billing_partner_id.id,
                    'company_id': self.env.company.id,
                    'journal_id': sale_journal.id,
                    'payment_mode_id': self.mode.id,
                    'date': '2026-11-30',
                    'invoice_date': fields.Date.context_today(self),
                    'afa_service_month': '2026-11-01',
                    'afa_service_family_id': self.family.id,
                    'afa_service_billing_type': 'service',
                }
            )
        )
        regular_service = self.env['afa.service'].create(
            {
                'name': 'Return Fee Test Regular Service',
                'period_id': period.id,
                'date_start': '2026-11-01',
                'date_end': '2027-06-30',
                'product_id': product.id,
                'invoice_journal_id': sale_journal.id,
                'payment_mode_id': self.mode.id,
                'member_price': 12,
                'nonmember_price': 12,
            }
        )
        regular_window = self.env['afa.service.window'].create(
            {
                'service_id': regular_service.id,
                'kind': 'join',
                'date_start': '2026-11-01',
                'date_end': '2026-11-30',
                'effective_month': '2026-11-01',
            }
        )
        with patch('odoo.fields.Date.context_today', return_value=date(2026, 11, 17)):
            self.env['afa.service.subscription'].create(
                {
                    'service_id': regular_service.id,
                    'student_id': student.id,
                    'join_window_id': regular_window.id,
                }
            )
        billing = self.env['afa.service.billing'].create({'month': '2026-11-01'})
        billing.action_preview()
        self.assertEqual(fee.state, 'pending')

        result = billing.action_generate()
        invoices = self.env['account.move'].browse(result['domain'][0][2])
        invoice = invoices.filtered(lambda move: move.afa_service_billing_type == 'extracurricular')
        self.assertEqual(len(invoice), 1)
        regular_invoice.invalidate_recordset(['invoice_line_ids'])
        self.assertEqual(regular_invoice.invoice_line_ids.mapped('price_unit'), [12])

        fee.invalidate_recordset(['invoice_line_id', 'state'])
        self.assertEqual(fee.invoice_line_id.move_id, invoice)
        self.assertEqual(fee.state, 'invoiced')
        self.assertGreaterEqual(invoice.invoice_date, fee.returned_date)
        invoice.invalidate_recordset(['invoice_line_ids'])
        self.assertEqual(sorted(invoice.invoice_line_ids.mapped('price_unit')), [4, 20])
        self.assertFalse(fee.invoice_line_id.tax_ids)
        self.assertIn(self.invoice.name, fee.invoice_line_id.name)

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

    def _create_second_mandate(self, reference='AFA-TEST-02'):
        payer_bank = self.env['res.partner.bank'].create(
            {
                'partner_id': self.invoice.partner_id.id,
                'acc_number': 'ES9121000418450200051332',
            }
        )
        payer_bank._compute_acc_type()
        return self.env['account.banking.mandate'].create(
            {
                'format': 'sepa',
                'type': 'recurrent',
                'scheme': 'CORE',
                'signature_date': fields.Date.today(),
                'partner_bank_id': payer_bank.id,
                'state': 'valid',
                'unique_mandate_reference': reference,
            }
        )

    def test_multiple_valid_mandates_need_assignment_instead_of_first_match(self):
        self._create_second_mandate()

        self.wizard.action_preview()

        self.assertFalse(self.wizard.line_ids.eligible)
        self.assertIn('Multiple valid SEPA mandates', self.wizard.line_ids.reason)

    def test_family_default_mandate_is_used_for_all_unmapped_purposes(self):
        second = self._create_second_mandate()
        self.env['afa.sepa.mandate.rule'].create(
            {
                'family_id': self.family.id,
                'company_id': self.env.company.id,
                'purpose': 'default',
                'mandate_id': second.id,
            }
        )

        self.wizard.action_preview()
        action = self.wizard.action_prepare()
        order = self.env['account.payment.order'].browse(action['res_id'])

        self.assertTrue(self.wizard.line_ids.eligible, self.wizard.line_ids.reason)
        self.assertEqual(order.payment_line_ids.mandate_id, second)

    def test_invalid_service_assignment_does_not_fall_back_to_another_mandate(self):
        assigned = self._create_second_mandate()
        self.env['afa.sepa.mandate.rule'].create(
            {
                'family_id': self.family.id,
                'company_id': self.env.company.id,
                'purpose': 'acollida',
                'mandate_id': assigned.id,
            }
        )
        assigned.state = 'cancel'
        self.invoice.mandate_id = self.mandate
        account_move_class = type(self.invoice)
        with patch.object(
            account_move_class, '_afa_sepa_mandate_purposes', return_value={'acollida'}
        ):
            self.wizard.action_preview()

        self.assertFalse(self.wizard.line_ids.eligible)
        self.assertIn('no longer valid', self.wizard.line_ids.reason)

    def test_service_specific_mandate_is_not_an_implicit_default(self):
        other = self._create_second_mandate()
        self.env['afa.sepa.mandate.rule'].create(
            {
                'family_id': self.family.id,
                'company_id': self.env.company.id,
                'purpose': 'acollida',
                'mandate_id': self.mandate.id,
            }
        )
        other.state = 'cancel'
        account_move_class = type(self.invoice)
        with patch.object(
            account_move_class, '_afa_sepa_mandate_purposes', return_value={'default'}
        ):
            self.wizard.action_preview()

        self.assertFalse(self.wizard.line_ids.eligible)
        self.assertIn('No default SEPA mandate', self.wizard.line_ids.reason)

    def test_invoice_with_different_purpose_mandates_must_be_split(self):
        second = self._create_second_mandate()
        self.env['afa.sepa.mandate.rule'].create(
            [
                {
                    'family_id': self.family.id,
                    'company_id': self.env.company.id,
                    'purpose': 'default',
                    'mandate_id': self.mandate.id,
                },
                {
                    'family_id': self.family.id,
                    'company_id': self.env.company.id,
                    'purpose': 'extracurricular',
                    'mandate_id': second.id,
                },
            ]
        )
        account_move_class = type(self.invoice)
        with patch.object(
            account_move_class,
            '_afa_sepa_mandate_purposes',
            return_value={'default', 'extracurricular'},
        ):
            self.wizard.action_preview()

        self.assertFalse(self.wizard.line_ids.eligible)
        self.assertIn('split the invoice', self.wizard.line_ids.reason)

    def test_extracurricular_assignment_splits_monthly_service_billing(self):
        billing = self.env['afa.service.billing'].create({})
        subscription = SimpleNamespace(
            family_id=self.family,
            service_id=SimpleNamespace(
                _fields={'is_extracurricular': object()},
                company_id=self.env.company,
                is_extracurricular=True,
            ),
        )
        self.assertEqual(
            billing._invoice_group_extra(subscription, {}),
            ('service',),
        )
        self.env['afa.sepa.mandate.rule'].create(
            {
                'family_id': self.family.id,
                'company_id': self.env.company.id,
                'purpose': 'extracurricular',
                'mandate_id': self.mandate.id,
            }
        )

        self.assertEqual(
            billing._invoice_group_extra(subscription, {}),
            ('extracurricular',),
        )
        subscription.service_id.is_extracurricular = False
        self.assertEqual(
            billing._invoice_group_extra(subscription, {}),
            ('service',),
        )

    def test_invoice_billing_type_resolves_the_sepa_mandate_purpose(self):
        self.invoice.afa_service_billing_type = 'acollida'

        self.assertEqual(self.invoice._afa_sepa_mandate_purposes(), {'acollida'})

        self.invoice.afa_service_billing_type = 'extracurricular'
        self.assertEqual(self.invoice._afa_sepa_mandate_purposes(), {'extracurricular'})

    def test_acollida_only_legacy_invoice_does_not_gain_default_purpose(self):
        self.invoice.afa_service_billing_type = 'service'
        account_move_class = type(self.invoice)
        with patch.object(account_move_class, '_afa_sepa_has_acollida_charges', return_value=True):
            self.assertEqual(self.invoice._afa_sepa_mandate_purposes(), {'acollida'})

    def test_order_revalidates_mandate_assignment_before_file_generation(self):
        replacement = self._create_second_mandate()
        rule = self.env['afa.sepa.mandate.rule'].create(
            {
                'family_id': self.family.id,
                'company_id': self.env.company.id,
                'purpose': 'default',
                'mandate_id': self.mandate.id,
            }
        )
        self.wizard.action_preview()
        action = self.wizard.action_prepare()
        order = self.env['account.payment.order'].browse(action['res_id'])
        order.draft2open()
        rule.mandate_id = replacement

        with self.assertRaises(ValidationError):
            order.open2generated()

    def test_acollida_assignment_does_not_reuse_monthly_service_invoice(self):
        if 'afa.acollida.billing' not in self.env.registry.models:
            self.skipTest('afa_acollida is not installed')
        self.env['account.move'].with_context(_afa_generate_service_invoices=True).create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.invoice.partner_id.id,
                'company_id': self.env.company.id,
                'journal_id': self.env['account.journal']
                .search([('company_id', '=', self.env.company.id), ('type', '=', 'sale')], limit=1)
                .id,
                'payment_mode_id': self.mode.id,
                'date': '2026-10-31',
                'invoice_date': '2026-10-31',
                'afa_service_month': '2026-10-01',
                'afa_service_family_id': self.family.id,
                'afa_service_billing_type': 'service',
            }
        )
        self.env['afa.sepa.mandate.rule'].create(
            {
                'family_id': self.family.id,
                'company_id': self.env.company.id,
                'purpose': 'acollida',
                'mandate_id': self.mandate.id,
            }
        )
        billing = self.env['afa.acollida.billing'].create({'month': '2026-10-01'})

        invoice = billing._existing_invoice(
            self.family,
            self.env['account.journal'].search(
                [('company_id', '=', self.env.company.id), ('type', '=', 'sale')], limit=1
            ),
            self.mode,
        )

        self.assertFalse(invoice)

    def test_non_iban_creditor_account_is_excluded(self):
        bank_account = self.env['res.partner.bank'].create(
            {'partner_id': self.env.company.partner_id.id, 'acc_number': '1234567890'}
        )
        self.assertEqual(bank_account.acc_type, 'bank')
        self.journal.bank_account_id = bank_account
        self.wizard.action_preview()
        self.assertFalse(self.wizard.line_ids.eligible)
        self.assertIn('creditor IBAN', self.wizard.line_ids.reason)
        self.assertEqual(self.wizard.action_prepare()['res_model'], 'afa.sepa.wizard')

    def test_stale_reservation_excludes_only_conflicting_invoice(self):
        next_period = self.env['afa.membership.period'].create(
            {'name': 'Next SEPA year', 'date_start': '2027-07-01', 'date_end': '2028-06-30'}
        )
        next_link = self.env['afa.membership'].create(
            {'family_id': self.family.id, 'period_id': next_period.id}
        )
        next_invoice = next_link.action_create_dues_invoice(
            self.invoice.invoice_line_ids.product_id
        )
        next_invoice.currency_id = self.env.ref('base.EUR')
        next_invoice.action_post()
        self.wizard.invoice_ids = self.invoice | next_invoice
        self.wizard.action_preview()
        self.assertEqual(len(self.wizard.line_ids.filtered('eligible')), 2)

        competing_order = self.env['account.payment.order'].create(
            {'payment_mode_id': self.mode.id, 'journal_id': self.journal.id}
        )
        receivable = self.invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable'
        )
        vals = receivable._prepare_payment_line_vals(competing_order)
        vals.update(
            {
                'mandate_id': self.mandate.id,
                'partner_bank_id': self.mandate.partner_bank_id.id,
                'partner_id': self.invoice.partner_id.id,
            }
        )
        self.env['account.payment.line'].create(vals)

        original = type(self.wizard)._evaluate

        def stale_preview(wizard, invoice):
            if invoice == self.invoice:
                return self.mandate, False
            return original(wizard, invoice)

        with patch.object(type(self.wizard), '_evaluate', stale_preview):
            action = self.wizard.action_prepare()

        self.assertEqual(action['res_model'], 'afa.sepa.wizard')
        self.assertEqual(self.wizard.order_id.payment_line_ids.move_line_id.move_id, next_invoice)
        excluded = self.wizard.line_ids.filtered(lambda line: line.invoice_id == self.invoice)
        self.assertFalse(excluded.eligible)
        self.assertIn('already', excluded.reason)
        self.assertEqual(self.wizard.action_open_order()['res_id'], self.wizard.order_id.id)
        partial_order = self.wizard.order_id
        self.wizard.action_preview()
        self.assertEqual(self.wizard.order_id, partial_order)
        self.assertEqual(self.wizard.action_open_order()['res_id'], partial_order.id)
        partial_order.draft2open()
        partial_order.open2generated()
        partial_order.generated2uploaded()
        partial_order.payment_line_ids.action_record_return()
        self.wizard.action_preview()
        self.assertFalse(self.wizard.order_id)
        replacement_action = self.wizard.action_prepare()
        replacement_order = self.env['account.payment.order'].browse(replacement_action['res_id'])
        self.assertNotEqual(replacement_order, partial_order)
        self.assertEqual(self.wizard.order_id, replacement_order)
        self.assertEqual(self.wizard.action_open_order()['res_id'], replacement_order.id)
        self.wizard.invoice_ids = next_invoice
        with self.assertRaises(UserError):
            self.wizard.action_open_order()
        self.wizard.action_preview()
        self.assertFalse(self.wizard.order_id)
        self.assertTrue(partial_order.exists())

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

    def test_return_reopens_reconciled_invoice_without_manual_unreconciliation(self):
        self.invoice.partner_id.email = 'payer@example.test'
        self.wizard.action_preview()
        order = self.env['account.payment.order'].browse(self.wizard.action_prepare()['res_id'])
        order.draft2open()
        order.open2generated()
        order.generated2uploaded()
        line = order.payment_line_ids
        receivable = line.move_line_id
        self.assertTrue(receivable.reconciled)
        self.assertEqual(self.invoice.amount_residual, 0)

        line.action_record_return()

        self.assertEqual(order.payment_ids.state, 'canceled')
        self.assertFalse(receivable.reconciled)
        self.assertEqual(self.invoice.amount_residual, self.invoice.amount_total)
        self.assertTrue(line.afa_returned)
        notification = self.env['afa.sepa.return.notification'].search(
            [('line_ids.payment_line_id', '=', line.id)], limit=1
        )
        self.assertEqual(notification.state, 'queued')
        self.assertEqual(notification.mail_id.email_to, 'payer@example.test')

    def test_returned_service_invoice_does_not_revoke_membership(self):
        self.family.manual_member = True
        service_invoice = self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.family.billing_partner_id.id,
                'currency_id': self.env.ref('base.EUR').id,
                'invoice_line_ids': [
                    (
                        0,
                        0,
                        {
                            'product_id': self.invoice.invoice_line_ids.product_id.id,
                            'quantity': 1,
                            'price_unit': 25,
                        },
                    )
                ],
            }
        )
        service_invoice.action_post()
        wizard = self.env['afa.sepa.wizard'].create(
            {
                'invoice_ids': [(6, 0, service_invoice.ids)],
                'payment_mode_id': self.mode.id,
                'journal_id': self.journal.id,
            }
        )
        wizard.action_preview()
        self.assertTrue(wizard.line_ids.eligible, wizard.line_ids.reason)
        action = wizard.action_prepare()
        self.assertEqual(action['res_model'], 'account.payment.order')
        order = self.env['account.payment.order'].browse(action['res_id'])
        order.draft2open()
        order.open2generated()
        order.generated2uploaded()

        order.payment_line_ids.action_record_return()

        self.assertTrue(self.family.is_member)
