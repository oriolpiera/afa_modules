from datetime import date
from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestMembershipIntent(TransactionCase):
    def setUp(self):
        super().setUp()
        guardian = self.env['res.partner'].create(
            {'name': 'Intent Guardian', 'afa_family_role': 'guardian'}
        )
        self.family = self.env['afa.family'].create(
            {'name': 'Intent Family', 'billing_partner_id': guardian.id}
        )
        self.period = self.env['afa.membership.period'].create(
            {'name': '2026/27', 'date_start': '2026-07-01', 'date_end': '2027-06-30'}
        )
        self.link = self.env['afa.membership'].create(
            {'family_id': self.family.id, 'period_id': self.period.id}
        )

    def _read_on(self, day):
        with patch('odoo.fields.Date.context_today', return_value=day):
            self.env.invalidate_all()
            family = self.env['afa.family'].browse(self.family.id)
            return (
                family.is_member,
                family.membership_state,
                family.current_period_id,
                family.current_dues_invoice_id,
            )

    def test_family_intent_grants_membership_before_invoice_and_persists(self):
        self.assertEqual(self._read_on(date(2026, 9, 1))[:2], (False, 'inactive'))

        self.family.manual_member = True

        self.assertEqual(self._read_on(date(2026, 9, 1))[:2], (True, 'member'))
        self.assertEqual(self._read_on(date(2027, 7, 1))[:2], (True, 'member'))
        self.family.manual_member = False
        self.assertEqual(self._read_on(date(2026, 9, 1))[:2], (False, 'inactive'))

    def test_contact_membership_column_projects_effective_family_status(self):
        guardian = self.family.billing_partner_id
        student = self.env['res.partner'].create(
            {
                'name': 'Intent Student',
                'afa_family_id': self.family.id,
                'afa_family_role': 'student',
            }
        )
        self.assertFalse(guardian.afa_is_member)
        self.assertFalse(student.afa_is_member)

        self.family.manual_member = True

        self.assertTrue(guardian.afa_is_member)
        self.assertTrue(student.afa_is_member)

        self.family.manual_member = False

        self.assertFalse(guardian.afa_is_member)
        self.assertFalse(student.afa_is_member)

    def test_unpaid_returned_dues_suspend_membership_until_paid(self):
        self.env['account.chart.template'].try_loading('generic_coa', self.env.company)
        product = self.env['product.product'].create({'name': 'Intent dues', 'list_price': 100})
        invoice = self.link.action_create_dues_invoice(product)
        invoice.action_post()
        self.family.manual_member = True
        self.assertEqual(self._read_on(date(2026, 9, 1))[:2], (True, 'member'))
        self.assertTrue(self.family.billing_partner_id.afa_is_member)

        self.link._record_returned_dues(invoice)
        self.assertEqual(self._read_on(date(2026, 9, 1))[:2], (False, 'inactive'))
        self.assertFalse(self.family.billing_partner_id.afa_is_member)
        self.assertFalse(self.family.is_member_on(date(2027, 7, 1)))

        cash_account = self.env['account.account'].search(
            [('account_type', '=', 'asset_cash')], limit=1
        )
        journal = self.env['account.journal'].create(
            {
                'name': 'Intent Test Cash',
                'code': 'AFAI',
                'type': 'cash',
                'default_account_id': cash_account.id,
            }
        )
        register = (
            self.env['account.payment.register']
            .with_context(active_model='account.move', active_ids=invoice.ids)
            .create({'journal_id': journal.id, 'amount': invoice.amount_residual})
        )
        register.action_create_payments()

        self.assertEqual(invoice.payment_state, 'paid')
        self.assertEqual(self._read_on(date(2026, 9, 1))[:2], (True, 'member'))
        self.assertTrue(self.family.billing_partner_id.afa_is_member)
        self.assertTrue(self.family.is_member_on(date(2027, 7, 1)))

    def test_posted_linked_credit_note_still_revokes_membership(self):
        self.env['account.chart.template'].try_loading('generic_coa', self.env.company)
        cash_account = self.env['account.account'].search(
            [('account_type', '=', 'asset_cash')], limit=1
        )
        journal = self.env['account.journal'].create(
            {
                'name': 'Intent Refund Cash',
                'code': 'AFAR',
                'type': 'cash',
                'default_account_id': cash_account.id,
            }
        )
        product = self.env['product.product'].create(
            {'name': 'Intent refund dues', 'list_price': 100}
        )
        invoice = self.link.action_create_dues_invoice(product)
        invoice.action_post()
        register = (
            self.env['account.payment.register']
            .with_context(active_model='account.move', active_ids=invoice.ids)
            .create({'journal_id': journal.id, 'amount': invoice.amount_residual})
        )
        register.action_create_payments()
        self.family.manual_member = True
        self.assertEqual(self._read_on(date(2026, 9, 1))[:2], (True, 'member'))

        credit = invoice._reverse_moves(cancel=False)
        credit.action_post()

        self.assertFalse(self._read_on(date(2026, 9, 1))[0])

    def test_archived_link_does_not_change_persistent_intent(self):
        self.env['account.chart.template'].try_loading('generic_coa', self.env.company)
        product = self.env['product.product'].create(
            {'name': 'Archived intent dues', 'list_price': 10}
        )
        invoice = self.link.action_create_dues_invoice(product)
        self.family.manual_member = True
        family = self.family.with_context(active_test=False)
        self.assertEqual(self._read_on(date(2026, 9, 1))[3], invoice)

        self.link.active = False

        self.assertEqual(self._read_on(date(2026, 9, 1))[:2], (True, 'member'))
        self.assertFalse(family.current_dues_invoice_id)

    def test_only_family_managers_can_edit_intention_and_status_is_read_only(self):
        staff = self.env['res.users'].create(
            {
                'name': 'Intent Staff',
                'login': 'membership-intent-staff',
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
            }
        )
        with self.assertRaises(AccessError):
            self.family.billing_partner_id.with_user(staff).read(['afa_is_member'])
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.family.with_user(staff).write({'manual_member': True})
        for field in (
            'is_member',
            'membership_state',
            'current_period_id',
            'current_dues_invoice_reference',
        ):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self.family.write({field: False})

        manager = self.env['res.users'].create(
            {
                'name': 'Intent Manager',
                'login': 'membership-intent-manager',
                'group_ids': [(6, 0, [self.env.ref('afa_family.group_family_manager').id])],
            }
        )
        self.family.with_user(manager).write({'manual_member': True})
        self.assertTrue(self.family.manual_member)

    def test_family_form_displays_persistent_intention(self):
        form = self.env.ref('afa_membership.view_afa_family_membership_form')
        self.assertIn('manual_member', form.arch_db)
        self.assertIn('current_dues_invoice_reference', form.arch_db)
        self.assertNotIn('membership_mode', form.arch_db)
        self.assertNotIn('<field name="current_dues_invoice_id"', form.arch_db)

        contact_list = self.env.ref('afa_membership.view_partner_list_afa_membership')
        self.assertIn('afa_is_member', contact_list.arch_db)
        self.assertIn('afa_family.group_family_manager', contact_list.arch_db)
