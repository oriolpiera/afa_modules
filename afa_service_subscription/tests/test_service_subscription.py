from datetime import date
from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestServiceSubscription(TransactionCase):
    def setUp(self):
        super().setUp()
        self.today = date(2026, 9, 10)
        self.env['account.chart.template'].try_loading('generic_coa', self.env.company)
        guardian = self.env['res.partner'].create(
            {'name': 'Billing Guardian', 'afa_family_role': 'guardian'}
        )
        self.family = self.env['afa.family'].create(
            {'name': 'Billing Family', 'billing_partner_id': guardian.id}
        )
        self.student = self.env['res.partner'].create(
            {
                'name': 'Student One',
                'afa_family_id': self.family.id,
                'afa_family_role': 'student',
            }
        )
        period = self.env['afa.membership.period'].create(
            {
                'name': '2026/27',
                'date_start': '2026-07-01',
                'date_end': '2027-06-30',
            }
        )
        self.service = self.env['afa.service'].create(
            {
                'name': 'Morning Care',
                'period_id': period.id,
                'date_start': '2026-09-01',
                'date_end': '2027-06-30',
                'product_id': self.env['product.product']
                .create(
                    {
                        'name': 'Morning Care',
                        'list_price': 45.0,
                    }
                )
                .id,
                'member_price': 30,
                'nonmember_price': 45,
            }
        )
        self.join = self.env['afa.service.window'].create(
            {
                'service_id': self.service.id,
                'kind': 'join',
                'date_start': '2026-09-01',
                'date_end': '2026-09-30',
                'effective_month': '2026-10-01',
            }
        )
        self.leave = self.env['afa.service.window'].create(
            {
                'service_id': self.service.id,
                'kind': 'leave',
                'date_start': '2026-09-01',
                'date_end': '2026-09-30',
                'effective_month': '2027-01-01',
            }
        )

    def _subscribe(self, service=None, window=None):
        with patch('odoo.fields.Date.context_today', return_value=self.today):
            return self.env['afa.service.subscription'].create(
                {
                    'student_id': self.student.id,
                    'service_id': (service or self.service).id,
                    'join_window_id': (window or self.join).id,
                }
            )

    def _preview(self, month='2026-10-01'):
        wizard = self.env['afa.service.billing'].create({'month': month})
        wizard.action_preview()
        return wizard

    def test_window_enrollment_overlap_and_effective_withdrawal(self):
        subscription = self._subscribe()
        self.assertEqual(subscription.join_requested_on, self.today)
        self.assertEqual(subscription.start_month, date(2026, 10, 1))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._subscribe()
        with (
            patch('odoo.fields.Date.context_today', return_value=date(2026, 10, 1)),
            self.assertRaises(ValidationError),
            self.cr.savepoint(),
        ):
            self.env['afa.service.subscription'].create(
                {
                    'student_id': self.student.id,
                    'service_id': self.service.id,
                    'join_window_id': self.join.id,
                }
            )
        with patch('odoo.fields.Date.context_today', return_value=self.today):
            subscription.action_leave(self.leave)
        self.assertEqual(subscription.end_month, date(2027, 1, 1))
        self.assertEqual(subscription.leave_requested_on, self.today)
        self.assertEqual(self._preview('2026-12-01').line_ids.subscription_id, subscription)
        self.assertFalse(self._preview('2027-01-01').line_ids)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.student.write({'afa_family_role': 'guardian'})

    def test_withdrawal_requires_canceling_prebilled_months(self):
        subscription = self._subscribe()
        invoice_id = self._preview('2027-01-01').action_generate()['domain'][0][2][0]
        with (
            patch('odoo.fields.Date.context_today', return_value=self.today),
            self.assertRaises(ValidationError),
            self.cr.savepoint(),
        ):
            subscription.action_leave(self.leave)
        self.env['account.move'].browse(invoice_id).button_cancel()
        with patch('odoo.fields.Date.context_today', return_value=self.today):
            subscription.action_leave(self.leave)
        self.assertFalse(self._preview('2027-01-01').line_ids)

    def test_second_withdrawal_cannot_replace_first(self):
        subscription = self._subscribe()
        other = self.env['afa.service.window'].create(
            {
                'service_id': self.service.id,
                'kind': 'leave',
                'date_start': '2026-12-01',
                'date_end': '2026-12-31',
                'effective_month': '2027-02-01',
            }
        )
        with patch('odoo.fields.Date.context_today', return_value=self.today):
            subscription.action_leave(self.leave)
        with (
            patch('odoo.fields.Date.context_today', return_value=date(2026, 12, 10)),
            self.assertRaises(ValidationError),
            self.cr.savepoint(),
        ):
            subscription.action_leave(other)
        self.assertEqual(subscription.end_month, date(2027, 1, 1))

    def test_outdated_preview_cannot_bill_after_withdrawal(self):
        subscription = self._subscribe()
        wizard = self._preview('2027-01-01')
        with patch('odoo.fields.Date.context_today', return_value=self.today):
            subscription.action_leave(self.leave)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            wizard.action_generate()

    def test_service_period_changes_revalidate_existing_windows(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.service.write({'date_start': '2026-11-01'})
        self.assertEqual(self.service.date_start, date(2026, 9, 1))

    def test_family_cannot_mix_companies_in_same_school_year(self):
        self._subscribe()
        other_company = self.env['res.company'].create({'name': 'Second AFA Company'})
        other_service = self.service.copy(
            {
                'name': 'Other Company Service',
                'company_id': other_company.id,
            }
        )
        other_window = self.env['afa.service.window'].create(
            {
                'service_id': other_service.id,
                'kind': 'join',
                'date_start': '2026-09-01',
                'date_end': '2026-09-30',
                'effective_month': '2026-10-01',
            }
        )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._subscribe(other_service, other_window)

    def test_duplicate_preview_lines_are_rejected_before_invoicing(self):
        self._subscribe()
        wizard = self._preview()
        line = wizard.line_ids
        self.env['afa.service.billing.line'].create(
            {
                'wizard_id': wizard.id,
                'subscription_id': line.subscription_id.id,
                'month': wizard.month,
                'family_id': self.family.id,
                'payer_id': line.payer_id.id,
                'include': True,
            }
        )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            wizard.action_generate()
        self.assertFalse(
            self.env['account.move'].search(
                [
                    ('afa_service_family_id', '=', self.family.id),
                    ('afa_service_month', '=', wizard.month),
                ]
            )
        )

    def test_family_invoice_aggregates_services_and_does_not_duplicate(self):
        first = self._subscribe()
        second_service = self.service.copy({'name': 'Lunch'})
        second_window = self.env['afa.service.window'].create(
            {
                'service_id': second_service.id,
                'kind': 'join',
                'date_start': '2026-09-01',
                'date_end': '2026-09-30',
                'effective_month': '2026-10-01',
            }
        )
        second = self._subscribe(second_service, second_window)
        wizard = self._preview()
        self.assertEqual(set(wizard.line_ids.mapped('subscription_id').ids), {first.id, second.id})
        result = wizard.action_generate()
        invoice = self.env['account.move'].browse(result['domain'][0][2][0])
        self.assertEqual(invoice.partner_id, self.family.billing_partner_id)
        self.assertEqual(len(invoice.afa_service_charge_ids), 2)
        self.assertEqual(len(invoice.invoice_line_ids), 2)
        self.assertEqual(sorted(invoice.invoice_line_ids.mapped('price_unit')), [45, 45])
        self.assertTrue(all(invoice.afa_service_charge_ids.mapped('active')))
        wizard.action_preview()
        self.assertFalse(any(wizard.line_ids.mapped('include')))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            wizard.action_generate()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            first.charge_ids.invoice_line_id.write({'price_unit': 9})

    def test_cancel_and_regenerate_preserves_original_history(self):
        subscription = self._subscribe()
        original_id = self._preview().action_generate()['domain'][0][2][0]
        original = self.env['account.move'].browse(original_id)
        original.button_cancel()
        self.assertFalse(subscription.charge_ids.active)
        replacement_id = self._preview().action_generate()['domain'][0][2][0]
        replacement = self.env['account.move'].browse(replacement_id)
        self.assertNotEqual(original, replacement)
        self.assertEqual(len(subscription.with_context(active_test=False).charge_ids), 2)
        self.assertEqual(subscription.charge_ids.filtered('active').invoice_id, replacement)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            original.button_draft()

    def test_preview_exclusions_and_stale_prices(self):
        self._subscribe()
        wizard = self._preview()
        self.assertEqual(wizard.line_ids.price, 45)
        wizard.line_ids.include = False
        with self.assertRaises(ValidationError), self.cr.savepoint():
            wizard.action_generate()
        wizard.line_ids.include = True
        self.service.nonmember_price = 50
        with self.assertRaises(ValidationError), self.cr.savepoint():
            wizard.action_generate()
        wizard.action_preview()
        self.assertEqual(wizard.line_ids.price, 50)
        invoice = self.env['account.move'].browse(wizard.action_generate()['domain'][0][2][0])
        self.service.nonmember_price = 60
        self.assertEqual(invoice.afa_service_charge_ids.price, 50)
        self.assertEqual(invoice.invoice_line_ids.price_unit, 50)

    def test_member_tariff_uses_selected_school_year_not_today(self):
        self._subscribe()
        self.env['ir.config_parameter'].sudo().set_param('afa_membership.mode', 'manual')
        self.family.manual_member = True
        wizard = self._preview()
        self.assertTrue(wizard.line_ids.member)
        self.assertEqual(wizard.line_ids.price, 30)
        invoice = self.env['account.move'].browse(wizard.action_generate()['domain'][0][2][0])
        self.family.manual_member = False
        self.assertEqual(invoice.afa_service_charge_ids.price, 30)
        self.assertTrue(invoice.afa_service_charge_ids.member)

    def test_posted_invoice_keeps_payer_and_price_after_family_change(self):
        self._subscribe()
        invoice_id = self._preview().action_generate()['domain'][0][2][0]
        invoice = self.env['account.move'].browse(invoice_id)
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(invoice.afa_service_charge_ids.family_id, self.family)
        new_guardian = self.env['res.partner'].create(
            {
                'name': 'New Guardian',
                'afa_family_id': self.family.id,
                'afa_family_role': 'guardian',
            }
        )
        self.family.billing_partner_id = new_guardian
        self.service.nonmember_price = 70
        self.assertNotEqual(invoice.partner_id, new_guardian)
        self.assertEqual(invoice.afa_service_charge_ids.price, 45)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            invoice.write({'partner_id': new_guardian.id})

    def test_later_service_joins_existing_draft_family_invoice(self):
        first = self._subscribe()
        invoice_id = self._preview().action_generate()['domain'][0][2][0]
        service = self.service.copy({'name': 'After School'})
        window = self.env['afa.service.window'].create(
            {
                'service_id': service.id,
                'kind': 'join',
                'date_start': '2026-09-01',
                'date_end': '2026-09-30',
                'effective_month': '2026-10-01',
            }
        )
        second = self._subscribe(service, window)
        wizard = self._preview()
        self.assertEqual(wizard.line_ids.filtered('include').subscription_id, second)
        excluded = wizard.line_ids.filtered(lambda line: not line.include)
        self.assertEqual(excluded.subscription_id, first)
        self.assertEqual(wizard.action_generate()['domain'][0][2], [invoice_id])
        invoice = self.env['account.move'].browse(invoice_id)
        self.assertEqual(len(invoice.afa_service_charge_ids), 2)
        invoice.action_post()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['afa.service.subscription'].create(
                {
                    'student_id': self.student.id,
                    'service_id': self.service.id,
                    'join_window_id': self.join.id,
                }
            )

    def test_manager_only_and_window_validation(self):
        user = self.env['res.users'].create(
            {
                'name': 'No family access',
                'login': 'service-no-family',
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
            }
        )
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env['afa.service'].with_user(user).create(
                {
                    'name': 'Forbidden',
                    'period_id': self.service.period_id.id,
                    'date_start': '2026-09-01',
                    'date_end': '2027-06-30',
                    'product_id': self.service.product_id.id,
                }
            )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['afa.service.window'].create(
                {
                    'service_id': self.service.id,
                    'kind': 'join',
                    'date_start': '2026-09-15',
                    'date_end': '2026-10-15',
                    'effective_month': '2026-11-01',
                }
            )

    def test_unassigned_student_cannot_enroll(self):
        student = self.env['res.partner'].create(
            {
                'name': 'Student Without Family',
                'afa_family_role': 'student',
            }
        )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['afa.service.subscription'].create(
                {
                    'student_id': student.id,
                    'service_id': self.service.id,
                    'join_window_id': self.join.id,
                }
            )

    def test_staff_with_accounting_can_generate_and_cancel(self):
        self._subscribe()
        staff = self.env['res.users'].create(
            {
                'name': 'Service Billing Staff',
                'login': 'service-billing-staff',
                'group_ids': [
                    (
                        6,
                        0,
                        [
                            self.env.ref('afa_family.group_family_manager').id,
                            self.env.ref('account.group_account_user').id,
                        ],
                    )
                ],
            }
        )
        wizard = self.env['afa.service.billing'].with_user(staff).create({'month': '2026-10-01'})
        wizard.action_preview()
        invoice_id = wizard.action_generate()['domain'][0][2][0]
        invoice = self.env['account.move'].with_user(staff).browse(invoice_id)
        self.assertEqual(invoice.afa_service_charge_ids.price, 45)
        invoice.button_cancel()
        self.assertFalse(invoice.with_context(active_test=False).afa_service_charge_ids.active)
