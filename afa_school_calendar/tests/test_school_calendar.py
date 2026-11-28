from datetime import date, datetime, time

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase

TERMS = [
    ('1r trimestre', date(2026, 9, 8), date(2026, 12, 21)),
    ('2n trimestre', date(2027, 1, 8), date(2027, 4, 1)),
    ('3t trimestre', date(2027, 4, 18), date(2027, 6, 20)),
]

MANDATORY_DAY_COLOR = 11  # Keep in sync with the model constant.

GAPS = [
    (date(2026, 7, 1), date(2026, 9, 7)),
    (date(2026, 12, 22), date(2027, 1, 7)),
    (date(2027, 4, 2), date(2027, 4, 17)),
    (date(2027, 6, 21), date(2027, 6, 30)),
]


class TestSchoolCalendar(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.resource_calendar_id.tz = 'UTC'
        cls.period = cls.env['afa.membership.period'].create(
            {
                'name': '2026-2027',
                'date_start': date(2026, 7, 1),
                'date_end': date(2027, 6, 30),
            }
        )

    def _add_terms(self, env=None):
        env = env or self.env
        return env['afa.school.term'].create(
            [
                {
                    'name': name,
                    'period_id': self.period.id,
                    'date_start': start,
                    'date_end': end,
                }
                for name, start, end in TERMS
            ]
        )

    def _manual_holiday(self):
        return self.env['resource.calendar.leaves'].create(
            {
                'name': 'School elective holiday',
                'date_from': datetime.combine(date(2027, 2, 15), time.min),
                'date_to': datetime.combine(date(2027, 2, 15), time.max),
            }
        )

    def test_generation_covers_every_gap_and_only_gaps(self):
        terms = self._add_terms()
        self.period.action_generate_non_teaching_days()
        leaves = self.period.non_teaching_leave_ids
        self.assertEqual(
            sorted((leaf.date_from, leaf.date_to) for leaf in leaves),
            [
                (datetime.combine(start, time.min), datetime.combine(end, time.max))
                for start, end in GAPS
            ],
        )
        for leaf in leaves:
            self.assertEqual(leaf.time_type, 'leave')
            self.assertFalse(leaf.calendar_id)
            self.assertFalse(leaf.resource_id)
            self.assertEqual(leaf.company_id, self.env.company)
            self.assertEqual(leaf.school_year_id, self.period)
        for term in terms:
            for leaf in leaves:
                overlaps = leaf.date_from.date() <= term.date_end
                overlaps = overlaps and term.date_start <= leaf.date_to.date()
                self.assertFalse(overlaps)

    def test_generation_mirrors_mandatory_days_for_time_off(self):
        self._add_terms()
        self.period.action_generate_non_teaching_days()
        days = self.period.mandatory_day_ids
        self.assertEqual(sorted((day.start_date, day.end_date) for day in days), GAPS)
        for day in days:
            self.assertEqual(day.company_id, self.env.company)
            self.assertFalse(day.resource_calendar_id)
            self.assertEqual(day.school_year_id, self.period)
            self.assertEqual(day.color, MANDATORY_DAY_COLOR)
            self.assertTrue(day.school_leave_id)
            self.assertEqual(day.school_leave_id.afa_category, 'generated')
        leaves = self.period.non_teaching_leave_ids
        self.assertEqual(len(leaves), len(days))
        self.assertEqual(sorted(days.mapped('name')), sorted(leaves.mapped('name')))

    def test_one_manual_record_pairs_time_off_and_the_engine(self):
        elective = self.env['resource.calendar.leaves'].create(
            {
                'name': 'School elective: Carnival',
                'afa_category': 'school_elective',
                'date_from': datetime.combine(date(2027, 2, 15), time.min),
                'date_to': datetime.combine(date(2027, 2, 15), time.max),
            }
        )
        day = self.env['hr.leave.mandatory.day'].search([('school_leave_id', '=', elective.id)])
        self.assertEqual(len(day), 1)
        self.assertEqual((day.start_date, day.end_date), (date(2027, 2, 15), date(2027, 2, 15)))
        self.assertFalse(day.school_year_id)
        elective.write({'name': 'School elective: Patronage day'})
        self.assertEqual(day.name, 'School elective: Patronage day')
        elective.unlink()
        self.assertFalse(day.exists())

    def test_public_holidays_register_with_category_and_survive_regeneration(self):
        state = self.env['resource.calendar.leaves'].create(
            {
                'name': 'State holiday: National Day',
                'afa_category': 'state_holiday',
                'date_from': datetime.combine(date(2026, 9, 11), time.min),
                'date_to': datetime.combine(date(2026, 9, 11), time.max),
            }
        )
        local = self.env['resource.calendar.leaves'].create(
            {
                'name': 'Local holiday: Festa Major',
                'afa_category': 'local_holiday',
                'date_from': datetime.combine(date(2027, 5, 15), time.min),
                'date_to': datetime.combine(date(2027, 5, 15), time.max),
            }
        )
        self._add_terms()
        self.period.action_generate_non_teaching_days()
        self.assertTrue(state.exists() and local.exists())
        for leave in state | local:
            days = self.env['hr.leave.mandatory.day'].search([('school_leave_id', '=', leave.id)])
            self.assertEqual(len(days), 1)
            self.assertFalse(days.school_year_id)

    def test_holidays_owned_by_time_off_status_are_not_paired(self):
        employee = self.env['hr.employee'].create({'name': 'Test Teacher'})
        leave = self.env['hr.leave'].create(
            {
                'name': 'Summer trip',
                'employee_id': employee.id,
                'holiday_status_id': self.env['hr.leave.type']
                .create({'name': 'Vacation', 'requires_allocation': False})
                .id,
                'date_from': datetime.combine(date(2027, 8, 16), time.min),
                'date_to': datetime.combine(date(2027, 8, 20), time.max),
            }
        )
        self.env['resource.calendar.leaves'].create(
            {
                'name': 'Aug 15',
                'holiday_id': leave.id,
                'date_from': datetime.combine(date(2027, 8, 15), time.min),
                'date_to': datetime.combine(date(2027, 8, 15), time.max),
            }
        )
        paired = self.env['hr.leave.mandatory.day'].search_count([('name', '=', 'Aug 15')])
        self.assertEqual(paired, 0)

    def test_clear_removes_generated_leaves_and_mandatory_days(self):
        self._add_terms()
        self.period.action_generate_non_teaching_days()
        leaves = self.period.non_teaching_leave_ids
        days = self.period.mandatory_day_ids
        self.assertEqual((len(leaves), len(days)), (4, 4))
        self.period.action_clear_non_teaching_days()
        self.assertFalse(leaves.exists())
        self.assertFalse(days.exists())

    def test_school_calendar_days_action_opens_a_calendar_view(self):
        action = self.env.ref('afa_school_calendar.action_school_calendar_leaves')
        self.assertEqual(action.view_mode, 'calendar,list,form')
        view = self.env['ir.ui.view'].browse(
            [binding.view_id.id for binding in action.view_ids if binding.view_id]
        )
        calendar_view = view.filtered(lambda v: v.type == 'calendar')
        self.assertTrue(calendar_view)
        fields_view = self.env['resource.calendar.leaves'].get_view(calendar_view.id)
        self.assertIn('date_from', fields_view['arch'])

    def test_year_without_terms_generates_one_full_year_leave(self):
        self.period.action_generate_non_teaching_days()
        leaves = self.period.non_teaching_leave_ids
        self.assertEqual(len(leaves), 1)
        self.assertEqual(leaves.date_from, datetime.combine(date(2026, 7, 1), time.min))
        self.assertEqual(leaves.date_to, datetime.combine(date(2027, 6, 30), time.max))

    def test_regeneration_replaces_generated_days_and_keeps_manual_days(self):
        manual = self._manual_holiday()
        self._add_terms()
        self.period.action_generate_non_teaching_days()
        first_ids = self.period.non_teaching_leave_ids.ids
        first_mandatory_ids = self.period.mandatory_day_ids.ids
        self.assertEqual(len(first_ids), 4)
        self.period.action_generate_non_teaching_days()
        leaves = self.period.non_teaching_leave_ids
        days = self.period.mandatory_day_ids
        self.assertEqual(len(leaves), 4)
        self.assertEqual(len(days), 4)
        self.assertTrue(set(leaves.ids).isdisjoint(first_ids))
        self.assertTrue(set(days.ids).isdisjoint(first_mandatory_ids))
        self.assertTrue(manual.exists())
        self.assertFalse(manual.school_year_id)

    def test_term_dates_must_fit_inside_the_year_and_not_overlap(self):
        with self.assertRaises(ValidationError):
            self.env['afa.school.term'].create(
                {
                    'name': 'Before the year',
                    'period_id': self.period.id,
                    'date_start': date(2026, 6, 1),
                    'date_end': date(2026, 6, 30),
                }
            )
        self._add_terms()
        with self.assertRaises(ValidationError):
            self.env['afa.school.term'].create(
                {
                    'name': 'Overlapping term',
                    'period_id': self.period.id,
                    'date_start': date(2026, 12, 21),
                    'date_end': date(2026, 12, 31),
                }
            )
        with self.assertRaises(ValidationError):
            self.env['afa.school.term'].create(
                {
                    'name': 'Inverted term',
                    'period_id': self.period.id,
                    'date_start': date(2027, 3, 1),
                    'date_end': date(2027, 2, 1),
                }
            )

    def test_removing_the_school_year_removes_generated_days(self):
        self._add_terms()
        manual = self._manual_holiday()
        self.period.action_generate_non_teaching_days()
        generated_leaves = self.period.non_teaching_leave_ids
        generated_days = self.period.mandatory_day_ids
        self.assertEqual((len(generated_leaves), len(generated_days)), (4, 4))
        self.period.unlink()
        self.assertFalse(generated_leaves.exists())
        self.assertFalse(generated_days.exists())
        self.assertTrue(manual.exists())

    def test_family_manager_generates_and_basic_user_cannot_configure(self):
        manager = self._manager_user()
        self._add_terms(env=self.env(user=manager))
        self.period.with_user(manager).action_generate_non_teaching_days()
        self.assertEqual(len(self.period.non_teaching_leave_ids), 4)
        basic = self.env['res.users'].create(
            {
                'name': 'Calendar User',
                'login': 'school_calendar_user',
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
            }
        )
        with self.assertRaises(AccessError):
            self.env['afa.school.term'].with_user(basic).create(
                {
                    'name': 'Unauthorized term',
                    'period_id': self.period.id,
                    'date_start': date(2026, 9, 8),
                    'date_end': date(2026, 9, 9),
                }
            )

    def _manager_user(self):
        return self.env['res.users'].create(
            {
                'name': 'Calendar Manager',
                'login': 'school_calendar_manager',
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

    def test_manager_creates_edits_and_deletes_manual_company_days(self):
        manager = self._manager_user()
        leaves = self.env['resource.calendar.leaves'].with_user(manager)
        holiday = leaves.create(
            {
                'name': 'School elective holiday',
                'date_from': datetime.combine(date(2027, 2, 15), time.min),
                'date_to': datetime.combine(date(2027, 2, 15), time.max),
            }
        )
        self.assertFalse(holiday.sudo().resource_id)
        self.assertFalse(holiday.sudo().calendar_id)
        holiday.write({'name': 'Carnaval'})
        holiday.unlink()
        self.assertFalse(holiday.exists())

    def test_basic_user_cannot_create_manual_company_days(self):
        basic = self.env['res.users'].create(
            {
                'name': 'Calendar User',
                'login': 'school_calendar_basic_user',
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
            }
        )
        with self.assertRaises(AccessError):
            self.env['resource.calendar.leaves'].with_user(basic).create(
                {
                    'name': 'Unauthorized company day',
                    'date_from': datetime.combine(date(2027, 2, 15), time.min),
                    'date_to': datetime.combine(date(2027, 2, 15), time.max),
                }
            )

    def test_moving_school_year_dates_revalidates_the_terms(self):
        self._add_terms()
        with self.assertRaises(ValidationError):
            self.period.write(
                {
                    'date_start': date(2025, 7, 1),
                    'date_end': date(2026, 6, 30),
                }
            )
        # Terms themselves also refuse to leave the configured year.
        with self.assertRaises(ValidationError):
            self.env['afa.school.term'].search([('period_id', '=', self.period.id)])[-1].write(
                {'date_end': date(2027, 9, 8)}
            )
        self.period.action_generate_non_teaching_days()
        self.assertTrue(
            all(
                date(2026, 7, 1) <= leave.date_from.date()
                and leave.date_to.date() <= date(2027, 6, 30)
                for leave in self.period.non_teaching_leave_ids
            )
        )
