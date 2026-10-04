from datetime import date
from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestSchoolPromotion(TransactionCase):
    def setUp(self):
        super().setUp()
        self.today = date(2027, 6, 15)
        self.env['account.chart.template'].try_loading('generic_coa', self.env.company)
        self.product = self.env['product.product'].search([('sale_ok', '=', True)], limit=1)
        guardian = self.env['res.partner'].create(
            {'name': 'Guardian', 'afa_family_role': 'guardian'}
        )
        self.family = self.env['afa.family'].create(
            {'name': 'Family', 'billing_partner_id': guardian.id}
        )
        self.first = self.env['afa.school.course'].create({'name': 'First', 'sequence': 1})
        self.last = self.env['afa.school.course'].create({'name': 'Last', 'sequence': 2})
        self.first.next_course_id = self.last
        self.younger = self._student('Younger', self.first)
        self.graduate = self._student('Graduate', self.last)
        # Demo students have no configured course; keep this test cohort isolated.
        self.env['res.partner'].search(
            [
                ('afa_family_role', '=', 'student'),
                ('id', 'not in', (self.younger | self.graduate).ids),
            ]
        ).write({'active': False})
        self.period = self.env['afa.membership.period'].create(
            {'name': '2026/27', 'date_start': '2026-07-01', 'date_end': '2027-06-30'}
        )

    def _student(self, name, course):
        return self.env['res.partner'].create(
            {
                'name': name,
                'afa_family_role': 'student',
                'afa_family_id': self.family.id,
                'afa_course_id': course.id,
            }
        )

    def _wizard(self):
        wizard = self.env['afa.school.promotion.wizard'].create({'period_id': self.period.id})
        wizard.action_preview()
        return wizard

    def _subscription(self, leave=True):
        service = self.env['afa.service'].create(
            {
                'name': 'Care',
                'period_id': self.period.id,
                'date_start': '2026-09-01',
                'date_end': '2027-06-30',
                'product_id': self.product.id,
                'member_price': 10,
                'nonmember_price': 20,
            }
        )
        join = self.env['afa.service.window'].create(
            {
                'service_id': service.id,
                'kind': 'join',
                'date_start': '2027-06-01',
                'date_end': '2027-06-20',
                'effective_month': '2027-06-01',
            }
        )
        if leave:
            self.env['afa.service.window'].create(
                {
                    'service_id': service.id,
                    'kind': 'leave',
                    'date_start': '2027-06-01',
                    'date_end': '2027-06-30',
                    'effective_month': '2027-07-01',
                }
            )
        with patch('odoo.fields.Date.context_today', return_value=self.today):
            return self.env['afa.service.subscription'].create(
                {
                    'student_id': self.graduate.id,
                    'service_id': service.id,
                    'join_window_id': join.id,
                }
            )

    def test_advances_every_active_student_and_archives_graduates(self):
        archived = self._student('Previously archived', self.first)
        archived.active = False
        wizard = self._wizard()
        self.assertEqual(
            set(wizard.line_ids.mapped('student_id').ids), {self.younger.id, self.graduate.id}
        )
        with patch('odoo.fields.Date.context_today', return_value=self.today):
            wizard.action_confirm()
        self.assertEqual(self.younger.afa_course_id, self.last)
        self.assertFalse(self.graduate.active)
        self.assertEqual(self.graduate.afa_family_id, self.family)
        self.assertTrue(self.family.active)
        self.assertEqual(archived.afa_course_id, self.first)
        record = self.env['afa.school.promotion'].search([('period_id', '=', self.period.id)])
        self.assertEqual((record.promoted_count, record.graduated_count), (1, 1))
        with self.assertRaises(ValidationError):
            wizard.action_confirm()

    def test_withdraws_services_before_archiving(self):
        subscription = self._subscription()
        with patch('odoo.fields.Date.context_today', return_value=self.today):
            self._wizard().action_confirm()
        self.assertEqual(subscription.end_month, date(2027, 7, 1))
        self.assertTrue(subscription.leave_window_id)
        self.assertFalse(self.graduate.active)

    def test_missing_window_rolls_back_all_student_changes(self):
        subscription = self._subscription(leave=False)
        wizard = self._wizard()
        with (
            patch('odoo.fields.Date.context_today', return_value=self.today),
            self.assertRaisesRegex(ValidationError, 'withdrawal window'),
            self.cr.savepoint(),
        ):
            wizard.action_confirm()
        self.assertEqual(self.younger.afa_course_id, self.first)
        self.assertTrue(self.graduate.active)
        self.assertFalse(subscription.leave_window_id)
        self.assertFalse(self.env['afa.school.promotion'].search([]))

    def test_later_withdrawal_failure_rolls_back_earlier_withdrawal(self):
        first_subscription = self._subscription()
        second_graduate = self._student('Second graduate', self.last)
        self.graduate = second_graduate
        second_subscription = self._subscription(leave=False)
        wizard = self._wizard()
        with (
            patch('odoo.fields.Date.context_today', return_value=self.today),
            self.assertRaisesRegex(ValidationError, 'withdrawal window'),
            self.cr.savepoint(),
        ):
            wizard.action_confirm()
        self.assertFalse(first_subscription.leave_window_id)
        self.assertFalse(second_subscription.leave_window_id)
        self.assertTrue(second_graduate.active)
        self.assertEqual(self.younger.afa_course_id, self.first)

    def test_future_subscription_blocks_graduation(self):
        future_period = self.env['afa.membership.period'].create(
            {'name': '2027/28', 'date_start': '2027-07-01', 'date_end': '2028-06-30'}
        )
        service = self.env['afa.service'].create(
            {
                'name': 'Next year care',
                'period_id': future_period.id,
                'date_start': '2027-07-01',
                'date_end': '2028-06-30',
                'product_id': self.product.id,
                'member_price': 10,
                'nonmember_price': 20,
            }
        )
        join = self.env['afa.service.window'].create(
            {
                'service_id': service.id,
                'kind': 'join',
                'date_start': '2027-07-01',
                'date_end': '2027-07-31',
                'effective_month': '2027-08-01',
            }
        )
        with patch('odoo.fields.Date.context_today', return_value=date(2027, 7, 10)):
            self.env['afa.service.subscription'].create(
                {
                    'student_id': self.graduate.id,
                    'service_id': service.id,
                    'join_window_id': join.id,
                }
            )
        wizard = self._wizard()
        with self.assertRaisesRegex(ValidationError, 'future subscription'):
            wizard.action_confirm()
        self.assertTrue(self.graduate.active)
        self.assertEqual(self.younger.afa_course_id, self.first)

    def test_stale_preview_and_missing_course_do_not_promote(self):
        wizard = self._wizard()
        self.younger.afa_course_id = self.last
        with self.assertRaises(ValidationError):
            wizard.action_confirm()
        self.younger.afa_course_id = False
        with self.assertRaises(ValidationError):
            wizard.action_preview()

    def test_ladder_and_student_role_are_validated(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.last.next_course_id = self.first
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.family.billing_partner_id.afa_course_id = self.first
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.last.sequence = 1

    def test_disconnected_course_ladder_blocks_preview(self):
        self.env['afa.school.course'].create({'name': 'Disconnected', 'sequence': 3})
        with self.assertRaisesRegex(ValidationError, 'connected course ladder'):
            self._wizard()

    def test_manager_can_confirm_without_permission_to_create_history_directly(self):
        manager = self.env['res.users'].create(
            {
                'name': 'Course Manager',
                'login': 'course_manager',
                'group_ids': [
                    (
                        6,
                        0,
                        [
                            self.env.ref('base.group_user').id,
                            self.env.ref('afa_family.group_family_manager').id,
                        ],
                    )
                ],
            }
        )
        wizard = (
            self.env['afa.school.promotion.wizard']
            .with_user(manager)
            .create({'period_id': self.period.id})
        )
        wizard.action_preview()
        wizard.action_confirm()
        self.assertFalse(self.graduate.active)
        with self.assertRaises(AccessError):
            self.env['afa.school.promotion'].with_user(manager).create(
                {'period_id': self.period.id}
            )

    def test_staff_cannot_run_promotion_even_with_direct_method_call(self):
        user = self.env['res.users'].create(
            {
                'name': 'Staff',
                'login': 'course_staff',
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
            }
        )
        wizard = self.env['afa.school.promotion.wizard'].create({'period_id': self.period.id})
        with self.assertRaises(AccessError):
            wizard.with_user(user).action_preview()
        with self.assertRaises(AccessError):
            wizard.with_user(user).action_confirm()
