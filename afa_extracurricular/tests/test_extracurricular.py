import base64
from datetime import date
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestExtracurricular(TransactionCase):
    def setUp(self):
        super().setUp()
        self.today = date(2026, 9, 10)
        self.env['account.chart.template'].try_loading('generic_coa', self.env.company)
        self.invoice_journal = self.env['account.journal'].search(
            [('company_id', '=', self.env.company.id), ('type', '=', 'sale')], limit=1
        )
        inbound_method = self.env['account.payment.method'].search(
            [('payment_type', '=', 'inbound')], limit=1
        )
        self.payment_mode = self.env['account.payment.mode'].create(
            {
                'name': 'Extracurricular Direct Debit',
                'company_id': self.env.company.id,
                'payment_method_id': inbound_method.id,
                'bank_account_link': 'variable',
            }
        )
        guardian = self.env['res.partner'].create(
            {'name': 'Billing Guardian', 'afa_family_role': 'guardian'}
        )
        self.family = self.env['afa.family'].create(
            {'name': 'Billing Family', 'billing_partner_id': guardian.id}
        )
        self.sponsor = self.env['res.partner'].create(
            {'name': 'Consell Comarcal', 'is_company': True}
        )
        self.student = self._student('Student One')
        self.other_student = self._student('Student Two')
        self.period = self.env['afa.membership.period'].create(
            {
                'name': '2026/27',
                'date_start': '2026-07-01',
                'date_end': '2027-06-30',
            }
        )
        self.product = self.env['product.product'].create(
            {'name': 'Activity Fee', 'list_price': 25.0}
        )
        self.chess = self._activity(
            'Chess',
            enrollment=('2026-09-05', '2026-09-08'),
            member_price=25,
            nonmember_price=35,
        )
        self.chess_a = self._group(
            self.chess, 'Chess A', capacity=1, slots=[('1', 12.5, 13.5), ('3', 12.5, 13.5)]
        )
        self.chess_b = self._group(self.chess, 'Chess B', capacity=5, slots=[('2', 16.0, 17.0)])
        self.robotics = self._activity(
            'Robotics',
            enrollment=('2026-09-10', '2026-09-20'),
            member_price=40,
            nonmember_price=50,
        )
        self.robotics_a = self._group(
            self.robotics, 'Robotics A', capacity=3, slots=[('1', 12.5, 13.5)]
        )
        self.generic = self.env['afa.service'].create(
            {
                'name': 'Morning Care',
                'period_id': self.period.id,
                'date_start': '2026-09-01',
                'date_end': '2027-06-30',
                'product_id': self.product.id,
                'invoice_journal_id': self.invoice_journal.id,
                'payment_mode_id': self.payment_mode.id,
                'member_price': 30,
                'nonmember_price': 45,
            }
        )
        self.chess_join = self._window(self.chess)
        self.robotics_join = self._window(self.robotics)
        self.generic_join = self._window(self.generic)

    def _student(self, name):
        return self.env['res.partner'].create(
            {
                'name': name,
                'afa_family_id': self.family.id,
                'afa_family_role': 'student',
            }
        )

    def _activity(self, name, enrollment, **prices):
        return self.env['afa.service'].create(
            {
                'name': name,
                'period_id': self.period.id,
                'date_start': '2026-10-01',
                'date_end': '2027-05-31',
                'product_id': self.product.id,
                'invoice_journal_id': self.invoice_journal.id,
                'payment_mode_id': self.payment_mode.id,
                'is_extracurricular': True,
                'enrollment_date_start': enrollment[0],
                'enrollment_date_end': enrollment[1],
                **prices,
            }
        )

    def _window(self, service):
        return self.env['afa.service.window'].create(
            {
                'service_id': service.id,
                'kind': 'join',
                'date_start': '2026-09-01',
                'date_end': '2026-09-30',
                'effective_month': '2026-10-01',
            }
        )

    def _group(self, service, name, slots, **kwargs):
        group = self.env['afa.service.group'].create(
            {'service_id': service.id, 'name': name, **kwargs}
        )
        for weekday, hour_from, hour_to in slots:
            self.env['afa.service.group.schedule'].create(
                {
                    'group_id': group.id,
                    'weekday': weekday,
                    'hour_from': hour_from,
                    'hour_to': hour_to,
                }
            )
        return group

    def _join_window(self, service):
        return self.env['afa.service.window'].search(
            [('service_id', '=', service.id), ('kind', '=', 'join')], limit=1
        )

    def _enroll(self, student=None, service=None, group=None):
        service = service or self.chess
        with patch('odoo.fields.Date.context_today', return_value=self.today):
            return self.env['afa.service.subscription'].create(
                {
                    'student_id': (student or self.student).id,
                    'service_id': service.id,
                    'join_window_id': self._join_window(service).id,
                    'group_id': group.id if group else False,
                }
            )

    def _preview(self, month='2026-10-01'):
        wizard = self.env['afa.service.billing'].create({'month': month})
        wizard.action_preview()
        return wizard

    def _aid(self, family=None, period=None, percent=40, tariff_basis='member'):
        return self.env['afa.extracurricular.aid'].create(
            {
                'family_id': (family or self.family).id,
                'period_id': (period or self.period).id,
                'sponsor_id': self.sponsor.id,
                'subsidy_percent': percent,
                'tariff_basis': tariff_basis,
            }
        )

    def _import_wizard(self, content):
        return self.env['afa.extracurricular.import.wizard'].create(
            {
                'filename': 'enrollments.csv',
                'file': base64.b64encode(content.encode()),
            }
        )

    def test_activity_configuration_and_schedule_validation(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._activity(
                'No Period',
                enrollment=(False, False),
                member_price=10,
                nonmember_price=15,
            )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._activity(
                'Wrong Period Order',
                enrollment=('2026-09-20', '2026-09-10'),
                member_price=10,
                nonmember_price=15,
            )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['afa.service.group'].create(
                {'service_id': self.generic.id, 'name': 'Not An Activity'}
            )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['afa.service.group'].create(
                {'service_id': self.chess.id, 'name': 'Negative', 'capacity': -1}
            )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._group(self.chess, 'Duplicated', slots=[('2', 12.0, 13.0), ('2', 15.0, 16.0)])
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._group(self.chess, 'Bad Hours', slots=[('4', 13.5, 12.0)])
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._group(self.chess, 'Bad Hours', slots=[('4', -1.0, 12.0)])
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._group(self.chess, 'Bad Hours', slots=[('4', 12.0, 25.0)])
        self.env['afa.service.group'].create({'service_id': self.chess.id, 'name': 'Chess C'})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['afa.service.group'].create({'service_id': self.chess.id, 'name': 'Chess A'})
        other = self._activity(
            'Crafts',
            enrollment=('2026-09-10', '2026-09-20'),
            member_price=10,
            nonmember_price=15,
        )
        self.env['afa.service.group'].create({'service_id': other.id, 'name': 'Chess A'})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.chess.write({'is_extracurricular': False})

    def test_unassigned_student_group_permissions(self):
        user = self.env['res.users'].create(
            {
                'name': 'No family access',
                'login': 'extracurricular-no-family',
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
            }
        )
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env['afa.service.group'].with_user(user).create(
                {'service_id': self.chess.id, 'name': 'Forbidden'}
            )
        student = self.env['res.partner'].create(
            {'name': 'Unassigned', 'afa_family_role': 'student'}
        )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._enroll(student=student)

    def test_enrollment_needs_matching_group_and_one_group_per_activity(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._enroll(group=False)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._enroll(group=self.robotics_a)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['afa.service.subscription'].create(
                {
                    'student_id': self.other_student.id,
                    'service_id': self.generic.id,
                    'join_window_id': self.generic_join.id,
                    'group_id': self.chess_a.id,
                }
            )
        first = self._enroll(group=self.chess_a)
        self.assertEqual(first.group_id, self.chess_a)
        self.assertTrue(first.is_extracurricular)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            first.write({'group_id': self.chess_b.id})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._enroll(student=self.student, group=self.chess_b)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.chess_a.unlink()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.chess_a.write({'service_id': self.robotics.id})

    def test_informative_window_and_capacity_never_block(self):
        first = self._enroll(group=self.chess_a)
        self.assertEqual(first.start_month, date(2026, 10, 1))
        second = self._enroll(student=self.other_student, group=self.chess_a)
        self.assertEqual(second.group_id, self.chess_a)
        with patch('odoo.fields.Date.context_today', return_value=date(2026, 11, 1)):
            self.assertEqual(self.chess_a.enrolled_count, 2)
            self.assertGreater(self.chess_a.enrolled_count, self.chess_a.capacity)

    def test_overlapping_schedules_across_activities_are_allowed(self):
        chess = self._enroll(group=self.chess_a)
        robotics = self._enroll(service=self.robotics, group=self.robotics_a)
        self.assertEqual(chess.service_id, self.chess)
        self.assertEqual(robotics.service_id, self.robotics)
        self.assertEqual(self.chess.enrollment_count, 1)
        self.assertEqual(self.robotics.enrollment_count, 1)

    def test_schedule_summary_refreshes_after_slot_edit(self):
        self.assertEqual(self.chess_b.schedule_summary, 'Tue 16:00-17:00')
        self.chess_b.schedule_ids.write({'hour_from': 15.0, 'hour_to': 16.5})
        self.assertEqual(self.chess_b.schedule_summary, 'Tue 15:00-16:30')

    def test_schedule_summary_normalises_rollover_minutes(self):
        group = self._group(self.chess, 'Roll', slots=[('4', 12.999, 14.0)])
        self.assertEqual(group.schedule_summary, 'Thu 13:00-14:00')

    def test_billing_covers_only_activity_months_with_tariffs_and_no_duplicates(self):
        self._enroll(group=self.chess_a)
        september = self._preview('2026-09-01')
        self.assertFalse(september.line_ids)
        october = self._preview('2026-10-01')
        self.assertEqual(october.line_ids.service_id, self.chess)
        self.assertFalse(october.line_ids.member)
        self.assertEqual(october.line_ids.price, 35)
        invoice = self.env['account.move'].browse(october.action_generate()['domain'][0][2][0])
        self.assertEqual(invoice.afa_service_charge_ids.price, 35)
        self.assertEqual(invoice.afa_service_charge_ids.subscription_id.group_id, self.chess_a)
        october.action_preview()
        self.assertFalse(any(october.line_ids.mapped('include')))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            october.action_generate()
        june = self._preview('2027-06-01')
        self.assertFalse(june.line_ids)

    def test_member_tariff_uses_family_membership_intention(self):
        self._enroll(group=self.chess_a)
        self.family.manual_member = True
        wizard = self._preview()
        self.assertTrue(wizard.line_ids.member)
        self.assertEqual(wizard.line_ids.price, 25)

    def test_scholarships_split_invoices_per_family_and_month(self):
        self._enroll(group=self.chess_a)
        self._enroll(
            student=self.other_student,
            service=self.robotics,
            group=self.robotics_a,
        )
        other_guardian = self.env['res.partner'].create(
            {'name': 'Second Billing Guardian', 'afa_family_role': 'guardian'}
        )
        other_family = self.env['afa.family'].create(
            {'name': 'Second Family', 'billing_partner_id': other_guardian.id}
        )
        other_student = self._student('Student Three')
        other_student.write({'afa_family_id': other_family.id})
        self._enroll(student=other_student, group=self.chess_a)
        self._aid(percent=40, tariff_basis='member')
        self._aid(family=other_family, percent=50, tariff_basis='membership')

        wizard = self._preview()
        first_family_lines = wizard.line_ids.filtered(lambda line: line.family_id == self.family)
        other_family_line = wizard.line_ids.filtered(lambda line: line.family_id == other_family)
        self.assertEqual(len(first_family_lines), 2)
        self.assertTrue(all(not line.member for line in wizard.line_ids))
        self.assertEqual(set(first_family_lines.mapped('price')), {25, 40})
        self.assertEqual(set(first_family_lines.mapped('family_price')), {15, 24})
        self.assertEqual(set(first_family_lines.mapped('sponsor_price')), {10, 16})
        self.assertEqual(other_family_line.price, 35)
        self.assertEqual(other_family_line.family_price, 17.5)
        self.assertEqual(other_family_line.sponsor_price, 17.5)

        result = wizard.action_generate()
        invoices = self.env['account.move'].browse(result['domain'][0][2])
        family_invoices = invoices.filtered(
            lambda invoice: invoice.partner_id in (self.family.billing_partner_id, other_guardian)
        )
        sponsor_invoices = invoices.filtered(lambda invoice: invoice.partner_id == self.sponsor)
        self.assertEqual(len(invoices), 4)
        self.assertEqual(len(family_invoices), 2)
        self.assertEqual(len(sponsor_invoices), 2)
        self.assertEqual(
            {invoice.afa_service_family_id.id for invoice in sponsor_invoices},
            {self.family.id, other_family.id},
        )
        self.assertTrue(all(not invoice.payment_mode_id for invoice in sponsor_invoices))
        self.assertEqual(
            sorted(
                family_invoices.filtered(
                    lambda invoice: invoice.afa_service_family_id == self.family
                ).invoice_line_ids.mapped('price_unit')
            ),
            [15, 24],
        )
        self.assertEqual(
            sorted(
                sponsor_invoices.filtered(
                    lambda invoice: invoice.afa_service_family_id == self.family
                ).invoice_line_ids.mapped('price_unit')
            ),
            [10, 16],
        )
        self.assertEqual(
            family_invoices.filtered(
                lambda invoice: invoice.afa_service_family_id == other_family
            ).invoice_line_ids.price_unit,
            17.5,
        )
        self.assertEqual(
            sponsor_invoices.filtered(
                lambda invoice: invoice.afa_service_family_id == other_family
            ).invoice_line_ids.price_unit,
            17.5,
        )
        charges = self.env['afa.service.charge'].search(
            [
                ('month', '=', wizard.month),
                ('subscription_id', 'in', wizard.line_ids.subscription_id.ids),
            ]
        )
        self.assertEqual(len(charges), 3)
        self.assertEqual(set(charges.mapped('price')), {25, 35, 40})
        self.assertEqual(set(charges.mapped('tariff_basis')), {'member', 'membership'})
        self.assertTrue(
            all(charge.family_price + charge.sponsor_price == charge.price for charge in charges)
        )
        self.assertTrue(all(charge.sponsor_invoice_id for charge in charges))

    def test_scholarship_does_not_change_family_membership_and_is_snapshot(self):
        self._enroll(group=self.chess_a)
        aid = self._aid(percent=40, tariff_basis='member')
        wizard = self._preview()
        line = wizard.line_ids
        self.assertFalse(line.member)
        self.assertEqual(line.tariff_basis, 'member')
        self.assertEqual(line.family_price, 15)
        self.assertEqual(line.sponsor_price, 10)

        aid.subsidy_percent = 50
        with self.assertRaises(ValidationError), self.cr.savepoint():
            wizard.action_generate()

        wizard.action_preview()
        invoices = self.env['account.move'].browse(wizard.action_generate()['domain'][0][2])
        charge = self.env['afa.service.charge'].search(
            [
                ('subscription_id', '=', wizard.line_ids.subscription_id.id),
                ('month', '=', wizard.month),
            ]
        )
        self.assertEqual(charge.aid_id, aid)
        self.assertEqual(charge.price, 25)
        self.assertEqual(charge.family_price, 12.5)
        self.assertEqual(charge.sponsor_price, 12.5)
        self.assertFalse(self.family.is_member_on(wizard.month))

        aid.subsidy_percent = 60
        self.assertEqual(charge.family_price, 12.5)
        self.assertEqual(charge.sponsor_price, 12.5)
        self.assertEqual(
            sorted(invoices.mapped('invoice_line_ids.price_unit')),
            [12.5, 12.5],
        )
        next_month = self._preview('2026-11-01')
        self.assertEqual(next_month.line_ids.family_price, 10)
        self.assertEqual(next_month.line_ids.sponsor_price, 15)

    def test_full_scholarship_generates_only_sponsor_invoice(self):
        self._enroll(group=self.chess_a)
        self._aid(percent=100, tariff_basis='member')

        wizard = self._preview()
        self.assertEqual(wizard.line_ids.family_price, 0)
        self.assertEqual(wizard.line_ids.sponsor_price, 25)
        invoice_ids = wizard.action_generate()['domain'][0][2]

        self.assertEqual(len(invoice_ids), 1)
        invoice = self.env['account.move'].browse(invoice_ids)
        self.assertEqual(invoice.partner_id, self.sponsor)
        charge = invoice.afa_service_sponsor_charge_ids
        self.assertEqual(len(charge), 1)
        self.assertFalse(charge.invoice_line_id)
        self.assertEqual(charge.family_price, 0)

    def test_scholarship_does_not_apply_to_non_extracurricular_services(self):
        self._enroll(service=self.generic)
        self._aid(percent=40, tariff_basis='member')

        line = self._preview().line_ids

        self.assertFalse(line.service_id.is_extracurricular)
        self.assertEqual(line.price, 45)
        self.assertEqual(line.family_price, 45)
        self.assertFalse(line.sponsor_id)
        self.assertEqual(line.sponsor_price, 0)

    def test_scholarship_requires_valid_percentage_and_unique_family_period(self):
        aid = self._aid()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._aid()
        next_period = self.env['afa.membership.period'].create(
            {
                'name': '2027/28',
                'date_start': '2027-07-01',
                'date_end': '2028-06-30',
            }
        )
        self._aid(period=next_period, percent=20)
        self.assertEqual(len(self.family.extracurricular_aid_ids), 2)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            aid.write({'subsidy_percent': 100.01})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            aid.write({'sponsor_id': self.family.billing_partner_id.id})

    def test_pair_invoices_must_both_be_canceled_before_regeneration(self):
        self._enroll(group=self.chess_a)
        self._aid(percent=40, tariff_basis='member')
        wizard = self._preview()
        invoices = self.env['account.move'].browse(wizard.action_generate()['domain'][0][2])
        family_invoice = invoices.filtered(
            lambda invoice: invoice.partner_id == self.family.billing_partner_id
        )
        sponsor_invoice = invoices.filtered(lambda invoice: invoice.partner_id == self.sponsor)

        family_invoice.button_cancel()
        sponsor_line = sponsor_invoice.invoice_line_ids
        with self.assertRaises(ValidationError), self.cr.savepoint():
            sponsor_line.write({'price_unit': 0})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            sponsor_line.unlink()

        blocked = self._preview()
        self.assertFalse(blocked.line_ids.include)
        self.assertIn('Cancel all family and sponsor invoices', blocked.line_ids.reason)

        sponsor_invoice.button_cancel()
        retry = self._preview()
        self.assertTrue(retry.line_ids.include)
        new_invoices = self.env['account.move'].browse(retry.action_generate()['domain'][0][2])
        self.assertEqual(len(new_invoices), 2)
        charges = (
            self.env['afa.service.charge']
            .with_context(active_test=False)
            .search(
                [
                    ('subscription_id', '=', retry.line_ids.subscription_id.id),
                    ('month', '=', retry.month),
                ]
            )
        )
        self.assertEqual(len(charges), 2)
        self.assertEqual(len(charges.filtered('active')), 1)

    def test_withdrawal_waits_until_both_scholarship_invoices_are_canceled(self):
        subscription = self._enroll(group=self.chess_a)
        self._aid(percent=40, tariff_basis='member')
        leave = self.env['afa.service.window'].create(
            {
                'service_id': self.chess.id,
                'kind': 'leave',
                'date_start': '2026-09-01',
                'date_end': '2026-09-30',
                'effective_month': '2027-01-01',
            }
        )
        invoices = self.env['account.move'].browse(
            self._preview('2027-01-01').action_generate()['domain'][0][2]
        )
        family_invoice = invoices.filtered(
            lambda invoice: invoice.partner_id == self.family.billing_partner_id
        )
        sponsor_invoice = invoices.filtered(lambda invoice: invoice.partner_id == self.sponsor)

        family_invoice.button_cancel()
        with (
            patch('odoo.fields.Date.context_today', return_value=self.today),
            self.assertRaises(ValidationError),
            self.cr.savepoint(),
        ):
            subscription.action_leave(leave)

        sponsor_invoice.button_cancel()
        with patch('odoo.fields.Date.context_today', return_value=self.today):
            subscription.action_leave(leave)
        self.assertEqual(subscription.end_month, date(2027, 1, 1))

    def test_enrollments_are_visible_from_student_family_and_activity(self):
        self._enroll(group=self.chess_a)
        self._enroll(student=self.other_student, service=self.robotics, group=self.robotics_a)
        generic = self._enroll(service=self.generic)
        self.assertFalse(generic.group_id)  # non-extracurricular keeps no group
        self.assertEqual(self.student.afa_extracurricular_count, 1)
        self.assertEqual(self.other_student.afa_extracurricular_count, 1)
        self.assertEqual(self.family.afa_extracurricular_count, 2)
        self.assertEqual(self.chess.enrollment_count, 1)
        self.assertEqual(self.robotics.enrollment_count, 1)
        student_action = self.student.action_open_afa_extracurriculars()
        self.assertEqual(
            student_action['domain'],
            [('student_id', '=', self.student.id), ('service_id.is_extracurricular', '=', True)],
        )
        family_action = self.family.action_open_afa_extracurriculars()
        self.assertEqual(
            family_action['domain'],
            [('family_id', '=', self.family.id), ('service_id.is_extracurricular', '=', True)],
        )
        activity_action = self.chess.action_open_enrollments()
        self.assertEqual(activity_action['domain'], [('service_id', '=', self.chess.id)])
        self.assertTrue(self.chess.group_ids)
        self.assertEqual(self.chess_a.schedule_ids.mapped('weekday'), ['1', '3'])

    def test_new_records_compute_counts_without_saved_id(self):
        new_family = self.env['afa.family'].new({})
        self.assertEqual(new_family.afa_extracurricular_count, 0)
        new_student = self.env['res.partner'].new({'name': 'Draft Student'})
        self.assertEqual(new_student.afa_extracurricular_count, 0)
        new_group = self.env['afa.service.group'].new({})
        self.assertEqual(new_group.enrolled_count, 0)

    def test_csv_import_enrolls_in_named_groups_with_one_or_many_groups(self):
        course = self.env['afa.school.course'].create({'name': 'i4', 'sequence': 900})
        self.student.afa_course_id = course
        crafts = self._activity(
            'Crafts',
            enrollment=('2026-09-10', '2026-09-20'),
            member_price=20,
            nonmember_price=30,
        )
        self._window(crafts)
        crafts_groups = [
            self._group(crafts, f'Crafts {letter}', slots=[])
            for letter in ('A', 'B', 'C', 'D', 'E')
        ]
        content = (
            'curs,nen,telefon,extraescolar,grup\n'
            'i4,Student One,666666666,Robotics,Robotics A\n'
            'i4,Student One,666666666,Chess,Chess A\n'
            f'i4,Student One,666666666,Crafts,{crafts_groups[4].name}\n'
        )
        wizard = self._import_wizard(content)

        with patch('odoo.fields.Date.context_today', return_value=self.today):
            wizard.action_load()
            self.assertEqual(wizard.line_ids.mapped('action'), ['create', 'create', 'create'])
            wizard.action_confirm()

        subscriptions = self.env['afa.service.subscription'].search(
            [('student_id', '=', self.student.id)]
        )
        self.assertEqual(len(subscriptions), 3)
        self.assertEqual(
            set(subscriptions.mapped('group_id').ids),
            {self.robotics_a.id, self.chess_a.id, crafts_groups[4].id},
        )
        self.assertFalse(self.student.phone)

    def test_csv_import_blocks_confirmation_when_any_row_has_an_error(self):
        course = self.env['afa.school.course'].create({'name': 'i4', 'sequence': 901})
        self.student.afa_course_id = course
        content = (
            'curs,nen,telefon,extraescolar,grup\n'
            'i4,Student One,666666666,Robotics,Robotics A\n'
            'i4,Missing Student,000000000,Chess,Chess A\n'
        )
        wizard = self._import_wizard(content)

        with patch('odoo.fields.Date.context_today', return_value=self.today):
            wizard.action_load()
            self.assertEqual(wizard.line_ids.mapped('action'), ['create', 'error'])
            action = wizard.action_confirm()

        self.assertEqual(action['res_id'], wizard.id)
        self.assertFalse(
            self.env['afa.service.subscription'].search(
                [('student_id', '=', self.student.id), ('service_id', '=', self.robotics.id)]
            )
        )

    def test_csv_import_invalidates_preview_when_file_changes(self):
        course = self.env['afa.school.course'].create({'name': 'i4', 'sequence': 903})
        self.student.afa_course_id = course
        first_file = 'curs,nen,extraescolar,grup\ni4,Student One,Chess,Chess A\n'
        replacement_file = 'curs,nen,extraescolar,grup\ni4,Student One,Chess,Chess B\n'
        wizard = self._import_wizard(first_file)

        with patch('odoo.fields.Date.context_today', return_value=self.today):
            wizard.action_load()
            old_checksum = wizard.preview_checksum
            wizard.write({'file': base64.b64encode(replacement_file.encode())})
            action = wizard.action_confirm()

            self.assertEqual(action['res_id'], wizard.id)
            self.assertFalse(wizard.line_ids)
            self.assertFalse(wizard.preview_checksum)
            self.assertTrue(wizard.preview_message)
            self.assertFalse(
                self.env['afa.service.subscription'].search(
                    [('student_id', '=', self.student.id), ('service_id', '=', self.chess.id)]
                )
            )

            wizard.action_load()
            self.assertNotEqual(wizard.preview_checksum, old_checksum)
            wizard.action_confirm()

        subscription = self.env['afa.service.subscription'].search(
            [('student_id', '=', self.student.id), ('service_id', '=', self.chess.id)]
        )
        self.assertEqual(subscription.group_id, self.chess_b)

    def test_csv_import_detects_existing_future_enrollment_conflict(self):
        course = self.env['afa.school.course'].create({'name': 'i4', 'sequence': 904})
        self.student.afa_course_id = course
        crafts = self._activity(
            'Crafts',
            enrollment=('2026-09-01', '2026-09-20'),
            member_price=20,
            nonmember_price=30,
        )
        future_window = self.env['afa.service.window'].create(
            {
                'service_id': crafts.id,
                'kind': 'join',
                'date_start': '2026-09-01',
                'date_end': '2026-09-05',
                'effective_month': '2026-11-01',
            }
        )
        self.env['afa.service.window'].create(
            {
                'service_id': crafts.id,
                'kind': 'join',
                'date_start': '2026-09-06',
                'date_end': '2026-09-20',
                'effective_month': '2026-10-01',
            }
        )
        crafts_a = self._group(crafts, 'Crafts A', slots=[])
        self._group(crafts, 'Crafts B', slots=[])
        with patch('odoo.fields.Date.context_today', return_value=date(2026, 9, 3)):
            self.env['afa.service.subscription'].create(
                {
                    'student_id': self.student.id,
                    'service_id': crafts.id,
                    'group_id': crafts_a.id,
                    'join_window_id': future_window.id,
                }
            )

        wizard = self._import_wizard('curs,nen,extraescolar,grup\ni4,Student One,Crafts,Crafts B\n')
        with patch('odoo.fields.Date.context_today', return_value=self.today):
            wizard.action_load()
            self.assertEqual(wizard.line_ids.action, 'error')
            self.assertIn('conflicts with this group', wizard.line_ids.error)
            wizard.action_confirm()

        subscriptions = self.env['afa.service.subscription'].search(
            [('student_id', '=', self.student.id), ('service_id', '=', crafts.id)]
        )
        self.assertEqual(len(subscriptions), 1)
        self.assertEqual(subscriptions.start_month, date(2026, 11, 1))

    def test_csv_import_skips_existing_same_group_and_rejects_duplicate_students(self):
        course = self.env['afa.school.course'].create({'name': 'i4', 'sequence': 902})
        self.student.afa_course_id = course
        content = 'curs,nen,extraescolar,grup\ni4,Student One,Chess,Chess A\n'
        wizard = self._import_wizard(content)

        with patch('odoo.fields.Date.context_today', return_value=self.today):
            wizard.action_load()
            wizard.action_confirm()
            second_import = self._import_wizard(content)
            second_import.action_load()
            self.assertEqual(second_import.line_ids.action, 'skip')
            with self.assertRaises(UserError):
                second_import.action_confirm()

        duplicate = self._student('Student One')
        duplicate.afa_course_id = course
        ambiguous_import = self._import_wizard(content)
        with patch('odoo.fields.Date.context_today', return_value=self.today):
            ambiguous_import.action_load()
        self.assertEqual(ambiguous_import.line_ids.action, 'error')
        self.assertIn('More than one student', ambiguous_import.line_ids.error)
