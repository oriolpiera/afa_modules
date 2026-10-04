from datetime import date
from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestMembershipSettings(TransactionCase):
    def setUp(self):
        super().setUp()
        guardian = self.env['res.partner'].create(
            {'name': 'Settings Guardian', 'afa_family_role': 'guardian'}
        )
        self.family = self.env['afa.family'].create(
            {'name': 'Settings Family', 'billing_partner_id': guardian.id}
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
                family.membership_mode,
            )

    def _read_same_date(self, day, family=None):
        with patch('odoo.fields.Date.context_today', return_value=day):
            record = family or self.family
            return record.is_member, record.membership_state, record.current_dues_invoice_id

    def test_cached_manual_status_reacts_to_flag_and_setting_without_global_invalidation(self):
        day = date(2026, 9, 1)
        self.assertEqual(self._read_same_date(day)[:2], (False, 'inactive'))
        self.env['res.config.settings'].create({'afa_membership_mode': 'manual'}).set_values()
        self.assertEqual(self._read_same_date(day)[:2], (False, 'inactive'))
        self.family.manual_member = True
        self.assertEqual(self._read_same_date(day)[:2], (True, 'manual'))
        self.family.manual_member = False
        self.assertEqual(self._read_same_date(day)[:2], (False, 'inactive'))
        self.family.manual_member = True
        self.env['res.config.settings'].create({'afa_membership_mode': 'invoice'}).set_values()
        self.assertEqual(self._read_same_date(day)[:2], (False, 'inactive'))
        self.env['res.config.settings'].create({'afa_membership_mode': 'manual'}).set_values()
        self.assertEqual(self._read_same_date(day)[:2], (True, 'manual'))

    def test_archived_links_never_supply_current_invoice_even_with_active_test_disabled(self):
        product = self.env['product.product'].create({'name': 'Archived dues', 'list_price': 10})
        self.env['account.chart.template'].try_loading('generic_coa', self.env.company)
        invoice = self.link.action_create_dues_invoice(product)
        day = date(2026, 9, 1)
        family = self.family.with_context(active_test=False)
        self.assertEqual(self._read_same_date(day, family)[2], invoice)
        self.link.active = False
        self.assertFalse(self._read_same_date(day, family)[2])
        replacement = self.env['afa.membership'].create(
            {'family_id': self.family.id, 'period_id': self.period.id}
        )
        self.assertFalse(self._read_same_date(day, family)[2])
        replacement.active = False
        self.assertFalse(self._read_same_date(day, family)[2])

    def test_default_invoice_mode_and_school_year_rollover(self):
        self.assertEqual(self._read_on(date(2026, 6, 30))[:2], (False, 'inactive'))
        self.assertEqual(self._read_on(date(2026, 7, 1))[2], self.period)
        self.assertFalse(self._read_on(date(2027, 6, 30))[0])
        self.assertFalse(self._read_on(date(2027, 7, 1))[0])
        self.assertEqual(self._read_on(date(2026, 9, 1))[4], 'invoice')

    def test_manual_mode_persists_through_july_and_mode_switch(self):
        self.env['res.config.settings'].create({'afa_membership_mode': 'manual'}).set_values()
        self.family.manual_member = True
        another_guardian = self.env['res.partner'].create(
            {'name': 'No-Link Guardian', 'afa_family_role': 'guardian'}
        )
        no_link = self.env['afa.family'].create(
            {'name': 'No-Link Family', 'billing_partner_id': another_guardian.id}
        )
        no_link.manual_member = True
        self.assertTrue(no_link.is_member)
        for day in (date(2026, 6, 30), date(2026, 7, 1), date(2027, 7, 1)):
            self.assertEqual(self._read_on(day)[:2], (True, 'manual'))
        self.env['res.config.settings'].create({'afa_membership_mode': 'invoice'}).set_values()
        self.assertFalse(self._read_on(date(2026, 9, 1))[0])
        self.assertTrue(self.family.manual_member)
        self.env['res.config.settings'].create({'afa_membership_mode': 'manual'}).set_values()
        self.assertTrue(self._read_on(date(2027, 7, 1))[0])

    def test_manual_flag_requires_family_manager_and_state_is_read_only(self):
        staff = self.env['res.users'].create(
            {
                'name': 'Settings Staff',
                'login': 'membership-settings-staff',
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
            }
        )
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.family.with_user(staff).write({'manual_member': True})
        for field in ('is_member', 'membership_state', 'current_period_id'):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self.family.write({field: False})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env['res.config.settings'].with_user(staff).create(
                {'afa_membership_mode': 'manual'}
            ).set_values()
        settings = self.env['res.config.settings'].create({'afa_membership_mode': 'manual'})
        with self.assertRaises(AccessError), self.cr.savepoint():
            settings.with_user(staff).set_values()
        manager = self.env['res.users'].create(
            {
                'name': 'Membership Manager',
                'login': 'membership-settings-manager',
                'group_ids': [(6, 0, [self.env.ref('afa_family.group_family_manager').id])],
            }
        )
        self.family.with_user(manager).write({'manual_member': True})
        self.assertTrue(self.family.manual_member)
        self.assertNotIn('manual_member', self.env['res.partner']._fields)

    def test_family_views_show_status_without_partner_flag(self):
        form = self.env.ref('afa_membership.view_afa_family_membership_form')
        settings = self.env.ref('afa_membership.view_res_config_settings_afa_membership')
        self.assertIn('manual_member', form.arch_db)
        self.assertIn('current_dues_invoice_id', form.arch_db)
        self.assertIn('afa_membership_mode', settings.arch_db)

    def test_invoice_mode_follows_paid_invoice_and_linked_credit(self):
        self.env['account.chart.template'].try_loading('generic_coa', self.env.company)
        cash_account = self.env['account.account'].search(
            [('account_type', '=', 'asset_cash')], limit=1
        )
        journal = self.env['account.journal'].create(
            {
                'name': 'Settings Test Cash',
                'code': 'AFAS',
                'type': 'cash',
                'default_account_id': cash_account.id,
            }
        )
        product = self.env['product.product'].create({'name': 'Settings Dues', 'list_price': 100})
        invoice = self.link.action_create_dues_invoice(product)
        self.assertEqual(self._read_on(date(2026, 7, 1))[3], invoice)
        self.assertFalse(self._read_on(date(2026, 7, 1))[0])
        invoice.action_post()
        register = (
            self.env['account.payment.register']
            .with_context(active_model='account.move', active_ids=invoice.ids)
            .create({'journal_id': journal.id, 'amount': invoice.amount_residual})
        )
        register.action_create_payments()
        self.assertEqual(self._read_on(date(2026, 7, 1))[:2], (True, 'paid'))
        manager = self.env['res.users'].create(
            {
                'name': 'Status Manager',
                'login': 'membership-status-manager',
                'group_ids': [(6, 0, [self.env.ref('afa_family.group_family_manager').id])],
            }
        )
        with patch('odoo.fields.Date.context_today', return_value=date(2026, 9, 1)):
            self.env.invalidate_all()
            status = self.family.with_user(manager).read(
                ['is_member', 'membership_state', 'current_period_id', 'current_dues_invoice_id']
            )[0]
            self.assertTrue(status['is_member'])
            self.assertEqual(status['current_dues_invoice_id'][0], invoice.id)
        self.env['res.config.settings'].create({'afa_membership_mode': 'manual'}).set_values()
        self.assertFalse(self._read_on(date(2026, 9, 1))[0])
        self.family.manual_member = True
        self.assertEqual(self._read_on(date(2026, 9, 1))[:2], (True, 'manual'))
        self.env['res.config.settings'].create({'afa_membership_mode': 'invoice'}).set_values()
        self.assertTrue(self._read_on(date(2027, 6, 30))[0])
        self.assertFalse(self._read_on(date(2027, 7, 1))[0])
        credit = invoice._reverse_moves(cancel=False)
        credit.action_post()
        self.assertEqual(invoice.payment_state, 'paid')
        self.assertFalse(self._read_on(date(2026, 9, 1))[0])

    def test_cached_invoice_status_reacts_to_payment_and_credit_note_lifecycle(self):
        self.env['account.chart.template'].try_loading('generic_coa', self.env.company)
        cash_account = self.env['account.account'].search(
            [('account_type', '=', 'asset_cash')], limit=1
        )
        journal = self.env['account.journal'].create(
            {
                'name': 'Cache Test Cash',
                'code': 'AFAT',
                'type': 'cash',
                'default_account_id': cash_account.id,
            }
        )
        product = self.env['product.product'].create({'name': 'Cache Dues', 'list_price': 100})
        day = date(2026, 9, 1)
        self.assertEqual(self._read_same_date(day)[:2], (False, 'inactive'))
        invoice = self.link.action_create_dues_invoice(product)
        self.assertEqual(self._read_same_date(day)[2], invoice)
        invoice.action_post()
        self.assertFalse(self._read_same_date(day)[0])
        register = (
            self.env['account.payment.register']
            .with_context(active_model='account.move', active_ids=invoice.ids)
            .create({'journal_id': journal.id, 'amount': invoice.amount_residual})
        )
        register.action_create_payments()
        self.assertEqual(invoice.payment_state, 'paid')
        self.assertEqual(self._read_same_date(day)[:2], (True, 'paid'))
        credit = invoice._reverse_moves(cancel=False)
        self.assertTrue(self._read_same_date(day)[0])
        credit.action_post()
        self.assertFalse(self._read_same_date(day)[0])
        credit.button_draft()
        self.assertTrue(self._read_same_date(day)[0])
