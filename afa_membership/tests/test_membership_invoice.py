from datetime import date
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestMembershipInvoice(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env['account.chart.template'].try_loading('generic_coa', self.env.company)
        cash_account = self.env['account.account'].search(
            [('account_type', '=', 'asset_cash')], limit=1
        )
        self.cash_journal = self.env['account.journal'].create(
            {
                'name': 'Membership Test Cash',
                'code': 'AFAC',
                'type': 'cash',
                'default_account_id': cash_account.id,
            }
        )
        guardian = self.env['res.partner'].create(
            {'name': 'Dues Guardian', 'afa_family_role': 'guardian'}
        )
        self.family = self.env['afa.family'].create(
            {'name': 'Dues Family', 'billing_partner_id': guardian.id}
        )
        period = self.env['afa.membership.period'].create(
            {'name': '2026/27', 'date_start': '2026-07-01', 'date_end': '2027-06-30'}
        )
        self.link = self.env['afa.membership'].create(
            {'family_id': self.family.id, 'period_id': period.id}
        )
        self.product = self.env['product.product'].create(
            {'name': 'Family dues', 'list_price': 120.0}
        )

    def test_dues_invoice_is_bound_to_family_period_and_has_positive_product_line(self):
        invoice = self.link.action_create_dues_invoice(self.product)
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.partner_id, self.family.billing_partner_id)
        self.assertEqual(invoice.afa_membership_id, self.link)
        self.assertEqual(self.link.invoice_id, invoice)
        self.assertEqual(invoice.invoice_line_ids.product_id, self.product)
        self.assertGreater(invoice.amount_total, 0)
        self.assertFalse(self.link.is_invoice_member_on(date(2026, 9, 1)))

    def test_invoice_recreation_and_zero_price_are_rejected(self):
        free_product = self.env['product.product'].create({'name': 'Free dues', 'list_price': 0})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.link.action_create_dues_invoice(free_product)
        self.link.action_create_dues_invoice(self.product)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.link.action_create_dues_invoice(self.product)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.link.write({'invoice_id': False})

    def test_configured_product_button_and_invoice_action(self):
        self.link.dues_product_id = self.product
        invoice = self.link.action_create_dues_invoice()
        action = self.link.action_open_dues_invoice()
        self.assertEqual(action['res_model'], 'account.move')
        self.assertEqual(action['res_id'], invoice.id)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            invoice.write({'afa_membership_id': False})
        self.assertFalse(invoice.copy().afa_membership_id)

    def test_posted_invoice_requires_full_payment_and_period_bounds(self):
        invoice = self.link.action_create_dues_invoice(self.product)
        self.assertFalse(self.link.is_invoice_member_on(date(2026, 7, 1)))
        invoice.action_post()
        self.assertFalse(self.link.is_invoice_member_on(date(2026, 7, 1)))
        self._pay(invoice, 60)
        self.assertFalse(self.link.is_invoice_member_on(date(2026, 9, 1)))
        self._pay(invoice, invoice.amount_residual)
        self.assertEqual(invoice.payment_state, 'paid')
        for day in (date(2026, 7, 1), date(2026, 9, 1), date(2027, 6, 30)):
            self.assertTrue(self.link.is_invoice_member_on(day))
        for day in (date(2026, 6, 30), date(2027, 7, 1)):
            self.assertFalse(self.link.is_invoice_member_on(day))
        invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable'
        ).remove_move_reconcile()
        self.assertNotEqual(invoice.payment_state, 'paid')
        self.assertFalse(self.link.is_invoice_member_on(date(2026, 9, 1)))

    def test_derived_link_state_tracks_payment_refund_and_archival(self):
        invoice = self.link.action_create_dues_invoice(self.product)
        with patch('odoo.fields.Date.context_today', return_value=date(2026, 9, 1)):
            self.assertEqual(self.link.state, 'pending')
            invoice.action_post()
            self.assertEqual(self.link.state, 'pending')
            self._pay(invoice, invoice.amount_residual)
            self.assertEqual(invoice.payment_state, 'paid')
            self.assertEqual(self.link.state, 'active')
            credit_note = invoice._reverse_moves(cancel=False)
            self.assertEqual(self.link.state, 'active')
            credit_note.action_post()
            self.assertEqual(invoice.payment_state, 'paid')
            self.assertEqual(self.link.state, 'pending')
            credit_note.button_draft()
            self.assertEqual(self.link.state, 'active')
            self.link.active = False
            self.assertEqual(self.link.state, 'canceled')
        for day, expected in (
            (date(2026, 6, 30), 'pending'),
            (date(2027, 6, 30), 'active'),
            (date(2027, 7, 1), 'expired'),
        ):
            self.link.active = True
            with patch('odoo.fields.Date.context_today', return_value=day):
                self.env.invalidate_all()
                self.assertEqual(self.link.state, expected)

    def test_billing_guardian_snapshot_and_unrelated_invoice_do_not_qualify(self):
        invoice = self.link.action_create_dues_invoice(self.product)
        old_guardian = invoice.partner_id
        new_guardian = self.env['res.partner'].create(
            {
                'name': 'Later Guardian',
                'afa_family_id': self.family.id,
                'afa_family_role': 'guardian',
            }
        )
        self.family.billing_partner_id = new_guardian
        self.assertEqual(invoice.partner_id, old_guardian)
        self.assertEqual(invoice.afa_membership_id, self.link)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.link.write({'family_id': False})
        invoice.action_post()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            invoice.write({'partner_id': new_guardian.id})
        unrelated = self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': new_guardian.id,
                'invoice_line_ids': [
                    (0, 0, {'product_id': self.product.id, 'quantity': 1, 'price_unit': 120})
                ],
            }
        )
        unrelated.action_post()
        self._pay(unrelated, unrelated.amount_residual)
        self.assertFalse(self.link.is_invoice_member_on(date(2026, 9, 1)))

    def test_full_credit_note_reversal_removes_entitlement(self):
        invoice = self.link.action_create_dues_invoice(self.product)
        invoice.action_post()
        self._pay(invoice, invoice.amount_residual)
        self.assertTrue(self.link.is_invoice_member_on(date(2026, 9, 1)))
        credit_note = invoice._reverse_moves(cancel=True)
        self.assertEqual(credit_note.move_type, 'out_refund')
        self.assertNotEqual(invoice.payment_state, 'paid')
        self.assertFalse(self.link.is_invoice_member_on(date(2026, 9, 1)))

    def test_linked_credit_note_revokes_without_changing_paid_invoice(self):
        invoice = self.link.action_create_dues_invoice(self.product)
        invoice.action_post()
        self._pay(invoice, invoice.amount_residual)
        unrelated = self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': invoice.partner_id.id,
                'invoice_line_ids': [
                    (0, 0, {'product_id': self.product.id, 'quantity': 1, 'price_unit': 120})
                ],
            }
        )
        unrelated.action_post()
        unrelated_credit = unrelated._reverse_moves(cancel=False)
        self.assertEqual(unrelated_credit.reversed_entry_id, unrelated)
        unrelated_credit.action_post()
        self.assertEqual(invoice.payment_state, 'paid')
        self.assertTrue(self.link.is_invoice_member_on(date(2026, 9, 1)))

        credit_note = invoice._reverse_moves(cancel=False)
        self.assertEqual(credit_note.reversed_entry_id, invoice)
        self.assertFalse(credit_note.afa_membership_id)
        self.assertTrue(self.link.is_invoice_member_on(date(2026, 9, 1)))
        credit_note.action_post()
        self.assertEqual(invoice.payment_state, 'paid')
        self.assertFalse(self.link.is_invoice_member_on(date(2026, 9, 1)))
        credit_note.button_draft()
        self.assertTrue(self.link.is_invoice_member_on(date(2026, 9, 1)))
        credit_note.button_cancel()
        self.assertEqual(credit_note.state, 'cancel')
        self.assertTrue(self.link.is_invoice_member_on(date(2026, 9, 1)))

    def _pay(self, invoice, amount):
        register = (
            self.env['account.payment.register']
            .with_context(active_model='account.move', active_ids=invoice.ids)
            .create({'journal_id': self.cash_journal.id, 'amount': amount})
        )
        register.action_create_payments()
