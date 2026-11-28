from datetime import date, datetime, time

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase

TERMS = [
    ('1r trimestre', date(2026, 9, 8), date(2026, 12, 21)),
    ('2n trimestre', date(2027, 1, 8), date(2027, 4, 1)),
    ('3t trimestre', date(2027, 4, 18), date(2027, 6, 20)),
]

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
        self.assertEqual(len(first_ids), 4)
        self.period.action_generate_non_teaching_days()
        leaves = self.period.non_teaching_leave_ids
        self.assertEqual(len(leaves), 4)
        self.assertTrue(set(leaves.ids).isdisjoint(first_ids))
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
        generated = self.period.non_teaching_leave_ids
        self.period.unlink()
        self.assertFalse(generated.exists())
        self.assertTrue(manual.exists())

    def test_family_manager_generates_and_basic_user_cannot_configure(self):
        manager = self.env['res.users'].create(
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
