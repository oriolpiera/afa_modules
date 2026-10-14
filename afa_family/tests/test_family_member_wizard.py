from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestFamilyMemberAddWizard(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Partner = self.env['res.partner']
        self.Family = self.env['afa.family']
        payer = self.Partner.create({'name': 'Billing Guardian', 'afa_family_role': 'guardian'})
        self.family = self.Family.create(
            {
                'name': 'Family',
                'billing_partner_id': payer.id,
            }
        )

    def _wizard(self, role, partners=()):
        return self.env['afa.family.member.add.wizard'].create(
            {
                'family_id': self.family.id,
                'role': role,
                'partner_ids': [(6, 0, [partner.id for partner in partners])],
            }
        )

    def test_family_tabs_open_wizard_for_their_member_role(self):
        for action, role in (
            (self.family.action_open_add_existing_guardians(), 'guardian'),
            (self.family.action_open_add_existing_students(), 'student'),
        ):
            self.assertEqual(action['res_model'], 'afa.family.member.add.wizard')
            self.assertEqual(action['view_mode'], 'form')
            self.assertEqual(action['target'], 'new')
            self.assertEqual(action['context']['default_family_id'], self.family.id)
            self.assertEqual(action['context']['default_role'], role)

    def test_add_existing_guardians_in_a_single_batch(self):
        guardian = self.Partner.create({'name': 'Existing Guardian', 'afa_family_role': 'guardian'})
        contact = self.Partner.create({'name': 'Unassigned Contact'})
        billing_guardian = self.family.billing_partner_id
        wizard = self._wizard('guardian', guardian | contact)

        result = wizard.action_add_members()

        self.assertEqual(result, {'type': 'ir.actions.act_window_close'})
        self.assertEqual(guardian.afa_family_id, self.family)
        self.assertEqual(guardian.afa_family_role, 'guardian')
        self.assertEqual(contact.afa_family_id, self.family)
        self.assertEqual(contact.afa_family_role, 'guardian')
        self.assertEqual(self.family.billing_partner_id, billing_guardian)
        self.assertIn(guardian, self.family.guardian_ids)
        self.assertIn(contact, self.family.guardian_ids)

    def test_add_existing_students_in_a_single_batch(self):
        first = self.Partner.create({'name': 'Existing Student'})
        second = self.Partner.create({'name': 'Another Existing Student'})
        wizard = self._wizard('student', first | second)

        wizard.action_add_members()

        self.assertEqual(first.afa_family_id, self.family)
        self.assertEqual(first.afa_family_role, 'student')
        self.assertEqual(second.afa_family_id, self.family)
        self.assertEqual(second.afa_family_role, 'student')
        self.assertEqual(self.family.student_ids, first | second)

    def test_rejects_contacts_that_already_belong_to_a_family(self):
        existing_student = self.Partner.create(
            {
                'name': 'Already Assigned',
                'afa_family_id': self.family.id,
                'afa_family_role': 'student',
            }
        )
        wizard = self._wizard('guardian', [existing_student])

        with self.assertRaises(UserError), self.cr.savepoint():
            wizard.action_add_members()

        self.assertEqual(existing_student.afa_family_id, self.family)
        self.assertEqual(existing_student.afa_family_role, 'student')

    def test_rechecks_membership_when_contact_is_assigned_after_opening(self):
        other_payer = self.Partner.create(
            {'name': 'Other Billing Guardian', 'afa_family_role': 'guardian'}
        )
        other_family = self.Family.create(
            {'name': 'Other Family', 'billing_partner_id': other_payer.id}
        )
        candidate = self.Partner.create({'name': 'Candidate'})
        wizard = self._wizard('student', [candidate])
        candidate.write({'afa_family_id': other_family.id, 'afa_family_role': 'guardian'})

        with self.assertRaises(UserError), self.cr.savepoint():
            wizard.action_add_members()

        self.assertEqual(candidate.afa_family_id, other_family)
        self.assertEqual(candidate.afa_family_role, 'guardian')

    def test_requires_at_least_one_contact(self):
        wizard = self._wizard('student')

        with self.assertRaises(UserError), self.cr.savepoint():
            wizard.action_add_members()
