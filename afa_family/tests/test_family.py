from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestFamily(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Partner = self.env['res.partner']
        self.Family = self.env['afa.family']
        self.guardian = self.Partner.create({'name': 'Guardian A', 'afa_family_role': 'guardian'})
        self.family = self.Family.create({
            'name': 'Family A',
            'billing_partner_id': self.guardian.id,
        })

    def test_standard_transaction_fixture_can_create_family_contacts(self):
        guardian = self.Partner.create({
            'name': 'Fixture Guardian', 'afa_family_role': 'guardian',
        })
        family = self.Family.create({
            'name': 'Fixture Family', 'billing_partner_id': guardian.id,
        })
        student = self.Partner.create({
            'name': 'Fixture Student', 'afa_family_id': family.id,
            'afa_family_role': 'student',
        })
        self.assertEqual(guardian.afa_family_id, family)
        self.assertEqual(family.student_ids, student)

    def test_initial_payer_is_linked_and_multiple_guardians_share_family(self):
        self.assertEqual(self.guardian.afa_family_id, self.family)
        second = self.Partner.create({
            'name': 'Guardian B',
            'afa_family_id': self.family.id,
            'afa_family_role': 'guardian',
        })
        student = self.Partner.create({
            'name': 'Student',
            'afa_family_id': self.family.id,
            'afa_family_role': 'student',
        })
        self.assertEqual(self.family.guardian_ids, self.guardian | second)
        self.assertEqual(self.family.student_ids, student)
        self.assertEqual(student.afa_family_id, self.family)

    def test_student_cannot_be_payer(self):
        student = self.Partner.create({
            'name': 'Student', 'afa_family_id': self.family.id, 'afa_family_role': 'student',
        })
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.family.write({'billing_partner_id': student.id})
        self.assertEqual(self.family.billing_partner_id, self.guardian)

    def test_payer_cannot_belong_to_another_family(self):
        outsider = self.Partner.create({'name': 'Outsider', 'afa_family_role': 'guardian'})
        other = self.Family.create({'name': 'Other', 'billing_partner_id': outsider.id})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.family.write({'billing_partner_id': outsider.id})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.Family.create({'name': 'Invalid', 'billing_partner_id': self.guardian.id})
        self.assertEqual(outsider.afa_family_id, other)

    def test_reassignment_preserves_previous_recipient_reference(self):
        second = self.Partner.create({
            'name': 'Guardian B', 'afa_family_id': self.family.id,
            'afa_family_role': 'guardian',
        })
        previous_recipient_id = self.family.billing_partner_id.id
        self.family.write({'billing_partner_id': second.id})
        self.assertEqual(self.family.billing_partner_id, second)
        self.assertEqual(previous_recipient_id, self.guardian.id)
        self.assertEqual(self.guardian.afa_family_id, self.family)

    def test_payer_cannot_be_demoted_detached_moved_or_deleted(self):
        other_guardian = self.Partner.create({'name': 'Other', 'afa_family_role': 'guardian'})
        other = self.Family.create({'name': 'Other', 'billing_partner_id': other_guardian.id})
        for vals in (
            {'afa_family_role': 'student'},
            {'afa_family_id': False},
            {'afa_family_id': other.id},
        ):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self.guardian.write(vals)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.guardian.unlink()
        self.assertEqual(self.family.billing_partner_id, self.guardian)

    def test_archived_family_still_protects_payer(self):
        self.family.active = False
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.guardian.write({'afa_family_role': 'student'})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.guardian.unlink()

    def test_partner_must_have_role_when_joining_family(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.Partner.create({'name': 'No Role', 'afa_family_id': self.family.id})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.guardian.write({'afa_family_role': False})

    def test_unassigned_guardian_cannot_be_selected_after_creation(self):
        guardian = self.Partner.create({'name': 'Unassigned', 'afa_family_role': 'guardian'})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.family.write({'billing_partner_id': guardian.id})
        self.assertEqual(self.family.billing_partner_id, self.guardian)

    def test_student_moves_between_families_without_duplicate_partner(self):
        other_guardian = self.Partner.create({'name': 'Other', 'afa_family_role': 'guardian'})
        other = self.Family.create({'name': 'Other', 'billing_partner_id': other_guardian.id})
        student = self.Partner.create({
            'name': 'Student', 'afa_family_id': self.family.id, 'afa_family_role': 'student',
        })
        student.write({'afa_family_id': other.id})
        self.assertNotIn(student, self.family.student_ids)
        self.assertIn(student, other.student_ids)
        self.assertEqual(student.id, self.Partner.search([('id', '=', student.id)]).id)

    def test_initial_payer_must_be_guardian(self):
        student = self.Partner.create({'name': 'Student', 'afa_family_role': 'student'})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.Family.create({'name': 'Invalid', 'billing_partner_id': student.id})
