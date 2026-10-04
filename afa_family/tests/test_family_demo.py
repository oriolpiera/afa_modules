import os

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestFamilyDemo(TransactionCase):
    def test_demo_families_and_contacts(self):
        first = self.env.ref('afa_family.demo_family_cedar', raise_if_not_found=False)
        if not first:
            if os.environ.get('AFA_EXPECT_DEMO') == '1':
                self.fail('Demo records are required for this test run')
            self.skipTest('Demo records were not loaded')

        second = self.env.ref('afa_family.demo_family_maple')
        self.assertEqual(len(first | second), 2)
        self.assertNotEqual(first.billing_partner_id, second.billing_partner_id)

        contact_ids = set()
        for family, guardian_names, student_names in (
            (first, ('cedar_payer', 'cedar_guardian'), ('cedar_student_1', 'cedar_student_2')),
            (second, ('maple_payer', 'maple_guardian'), ('maple_student_1', 'maple_student_2')),
        ):
            guardians = self.env['res.partner'].browse(
                [self.env.ref(f'afa_family.demo_{name}').id for name in guardian_names]
            )
            students = self.env['res.partner'].browse(
                [self.env.ref(f'afa_family.demo_{name}').id for name in student_names]
            )
            self.assertEqual(family.guardian_ids, guardians)
            self.assertEqual(family.student_ids, students)
            self.assertEqual(family.billing_partner_id, guardians[0])
            self.assertTrue(
                all(partner.afa_family_id == family for partner in guardians | students)
            )
            self.assertTrue(all(partner.afa_family_role == 'guardian' for partner in guardians))
            self.assertTrue(all(partner.afa_family_role == 'student' for partner in students))
            contact_ids.update((guardians | students).ids)
        self.assertEqual(len(contact_ids), 8)

        group_user = self.env.ref('base.group_user')
        group_contacts = self.env.ref('base.group_partner_manager')
        staff = self.env['res.users'].create(
            {
                'name': 'Demo Contacts Staff',
                'login': 'demo_contacts_staff_test',
                'group_ids': [(6, 0, (group_user | group_contacts).ids)],
            }
        )
        visible = self.env['res.partner'].with_user(staff)
        for family in first | second:
            for guardian in family.guardian_ids:
                self.assertEqual(visible.search([('id', '=', guardian.id)]).id, guardian.id)
            for student in family.student_ids:
                self.assertFalse(visible.search([('id', '=', student.id)]))
                with self.assertRaises(AccessError):
                    visible.browse(student.id).read(['name'])
