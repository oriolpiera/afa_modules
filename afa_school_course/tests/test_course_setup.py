from itertools import pairwise

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase

FULL_LADDER = [
    'i3',
    'i4',
    'i5',
    '1r',
    '2n',
    '3r',
    '4t',
    '5è',
    '6è',
    '1r ESO',
    '2n ESO',
    '3r ESO',
    '4t ESO',
]


class TestSchoolCourseSetup(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Course = self.env['afa.school.course']
        self.wizard_model = self.env['afa.school.course.setup.wizard']

    def _wizard(self, **stages):
        return self.wizard_model.create(stages)

    def _assert_chain(self, expected_names):
        courses = self.Course.search([('name', 'in', expected_names)], order='sequence, id')
        self.assertEqual(courses.mapped('name'), expected_names)
        for course, successor in pairwise(courses):
            self.assertEqual(course.next_course_id, successor)
        self.assertFalse(courses[-1].next_course_id)
        return courses

    def test_every_stage_builds_the_full_ladder(self):
        action = self._wizard(infantil=True, primaria=True, secundaria=True).action_confirm()
        self.assertEqual(action['res_model'], 'afa.school.course')
        courses = self._assert_chain(FULL_LADDER)
        self.assertEqual(courses.mapped('sequence'), list(range(1, len(FULL_LADDER) + 1)))

    def test_preschool_and_primary_share_the_boundary(self):
        self._wizard(infantil=True, primaria=True).action_confirm()
        self._assert_chain(FULL_LADDER[:9])

    def test_primary_and_secondary_share_the_boundary(self):
        self._wizard(primaria=True, secundaria=True).action_confirm()
        self._assert_chain(FULL_LADDER[3:])

    def test_zero_sequence_course_is_accepted(self):
        self.Course.create({'name': 'i3', 'sequence': 0})
        self._wizard(infantil=True).action_confirm()
        courses = self._assert_chain(FULL_LADDER[:3])
        self.assertEqual(courses.mapped('sequence'), [0, 1, 2])

    def test_a_ladder_can_start_below_the_existing_numbering(self):
        self.Course.create({'name': 'i4', 'sequence': 1})
        self._wizard(infantil=True).action_confirm()
        courses = self._assert_chain(FULL_LADDER[:3])
        self.assertEqual(courses.mapped('sequence'), [0, 1, 2])

    def test_a_single_stage_ends_without_a_successor(self):
        self._wizard(secundaria=True).action_confirm()
        self._assert_chain(FULL_LADDER[9:])

    def test_a_stage_selection_is_required(self):
        with self.assertRaisesRegex(ValidationError, 'at least one school stage'):
            self._wizard().action_confirm()
        self.assertFalse(self.Course.search([]))

    def test_existing_courses_are_reused_and_gaps_are_filled(self):
        existing = self.Course.create({'name': '4t', 'sequence': 5})
        self._wizard(primaria=True).action_confirm()
        courses = self._assert_chain(FULL_LADDER[3:9])
        self.assertEqual(courses[3], existing)
        self.assertEqual(courses.mapped('sequence'), [1, 2, 3, 5, 6, 7])

    def test_unrelated_courses_keep_their_sequences(self):
        self.Course.create({'name': 'Batxillerat', 'sequence': 2})
        self._wizard(infantil=True).action_confirm()
        courses = self._assert_chain(FULL_LADDER[:3])
        self.assertEqual(courses.mapped('sequence'), [1, 3, 4])

    def test_a_second_run_creates_nothing(self):
        self._wizard(infantil=True, primaria=True, secundaria=True).action_confirm()
        before = self.Course.search([]).ids
        self._wizard(infantil=True, primaria=True, secundaria=True).action_confirm()
        self.assertEqual(self.Course.search([]).ids, before)

    def test_conflicting_successor_is_refused(self):
        last = self.Course.create({'name': 'i5', 'sequence': 3})
        last.next_course_id = self.Course.create({'name': 'Batxillerat', 'sequence': 4})
        with (
            self.assertRaisesRegex(ValidationError, 'already continues to Batxillerat'),
            self.cr.savepoint(),
        ):
            self._wizard(infantil=True, primaria=True).action_confirm()

    def test_conflicting_predecessor_is_refused(self):
        predecessor = self.Course.create({'name': 'Entrada', 'sequence': 1})
        predecessor.next_course_id = self.Course.create({'name': '2n', 'sequence': 3})
        with (
            self.assertRaisesRegex(ValidationError, 'already has a predecessor'),
            self.cr.savepoint(),
        ):
            self._wizard(primaria=True).action_confirm()

    def test_out_of_order_sequences_are_refused(self):
        self.Course.create({'name': '1r', 'sequence': 5})
        self.Course.create({'name': '2n', 'sequence': 1})
        with self.assertRaisesRegex(ValidationError, 'does not fit'), self.cr.savepoint():
            self._wizard(primaria=True).action_confirm()

    def test_an_occupied_gap_is_refused(self):
        self.Course.create({'name': '4t', 'sequence': 2})
        with (
            self.assertRaisesRegex(ValidationError, 'No free course sequence'),
            self.cr.savepoint(),
        ):
            self._wizard(primaria=True).action_confirm()

    def test_a_successor_outside_the_selection_is_kept(self):
        last = self.Course.create({'name': '4t ESO', 'sequence': 4})
        graduate = self.Course.create({'name': 'Batxillerat', 'sequence': 5})
        last.next_course_id = graduate
        self._wizard(secundaria=True).action_confirm()
        courses = self.Course.search([('name', 'in', FULL_LADDER[9:])], order='sequence, id')
        self.assertEqual(courses.mapped('name'), FULL_LADDER[9:])
        self.assertEqual(courses[2].next_course_id, last)
        self.assertEqual(last.next_course_id, graduate)

    def test_staff_cannot_run_the_setup(self):
        user = self.env['res.users'].create(
            {
                'name': 'Staff',
                'login': 'course_setup_staff',
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
            }
        )
        wizard = self._wizard(infantil=True)
        with self.assertRaises(AccessError):
            wizard.with_user(user).action_confirm()
        self.assertFalse(self.Course.search([]))

    def test_manager_can_run_the_setup(self):
        manager = self.env['res.users'].create(
            {
                'name': 'Course Manager',
                'login': 'course_setup_manager',
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
        self._wizard(infantil=True).with_user(manager).action_confirm()
        self._assert_chain(FULL_LADDER[:3])
