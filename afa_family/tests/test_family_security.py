from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestFamilySecurity(TransactionCase):
    def setUp(self):
        super().setUp()
        group_user = self.env.ref('base.group_user')
        group_manager = self.env.ref('afa_family.group_family_manager')
        self.staff = self.env['res.users'].create({
            'name': 'Contacts Staff', 'login': 'contacts_staff_family_test',
            'group_ids': [(6, 0, group_user.ids)],
        })
        self.manager = self.env['res.users'].create({
            'name': 'Family Manager', 'login': 'family_manager_test',
            'group_ids': [(6, 0, (group_user | group_manager).ids)],
        })
        partners = self.env['res.partner'].with_user(self.manager)
        guardian = partners.create({'name': 'Guardian', 'afa_family_role': 'guardian'})
        self.family = self.env['afa.family'].with_user(self.manager).create({
            'name': 'Family', 'billing_partner_id': guardian.id,
        })
        self.student = partners.create({
            'name': 'Private Student', 'afa_family_id': self.family.id,
            'afa_family_role': 'student',
        })
        self.guardian = guardian
        self.unrelated = partners.create({'name': 'Unrelated Contact'})

    def test_staff_cannot_find_or_read_students_through_contacts(self):
        partners = self.env['res.partner'].with_user(self.staff)
        self.assertFalse(partners.search([('id', '=', self.student.id)]))
        self.assertFalse(partners.search([('name', '=', 'Private Student')]))
        self.assertNotIn(self.student.id, partners.search([]).ids)
        with self.assertRaises(AccessError):
            partners.browse(self.student.id).read(['name'])
        self.assertEqual(partners.browse(self.guardian.id).read(['name'])[0]['name'], 'Guardian')
        self.assertEqual(partners.browse(self.unrelated.id).read(['name'])[0]['name'], 'Unrelated Contact')
        self.assertEqual(partners.search([('name', '=', 'Unrelated Contact')]), self.unrelated)

    def test_staff_can_delete_unrelated_contact(self):
        partners = self.env['res.partner'].with_user(self.staff)
        partners.browse(self.unrelated.id).unlink()
        self.assertFalse(self.env['res.partner'].browse(self.unrelated.id).exists())

    def test_student_privacy_tracks_role_changes_without_exposing_family_id(self):
        partners = self.env['res.partner'].with_user(self.staff)
        self.assertFalse(partners.browse(self.unrelated.id).afa_is_student)
        self.unrelated.with_user(self.manager).write({'afa_family_role': 'student'})
        self.assertFalse(partners.search([('id', '=', self.unrelated.id)]))
        with self.assertRaises(AccessError):
            partners.browse(self.unrelated.id).read(['afa_family_id'])
        self.unrelated.with_user(self.manager).write({'afa_family_role': False})
        self.assertEqual(partners.search([('id', '=', self.unrelated.id)]), self.unrelated)

    def test_staff_cannot_modify_membership_or_remove_family_member(self):
        partners = self.env['res.partner'].with_user(self.staff)
        with self.assertRaises(AccessError):
            partners.create({'name': 'New Student', 'afa_family_role': 'student'})
        with self.assertRaises(AccessError):
            partners.browse(self.guardian.id).write({'afa_family_role': 'student'})
        with self.assertRaises(AccessError):
            partners.browse(self.unrelated.id).write({'afa_family_id': self.family.id})
        with self.assertRaises(AccessError):
            partners.browse(self.guardian.id).unlink()
        with self.assertRaises(AccessError):
            partners.browse(self.student.id).write({'name': 'Changed'})
        with self.assertRaises(AccessError):
            partners.browse(self.student.id).unlink()

    def test_manager_can_see_members_and_open_contextual_contacts(self):
        partners = self.env['res.partner'].with_user(self.manager)
        self.assertEqual(partners.search([('id', '=', self.student.id)]), self.student)
        self.assertEqual(partners.browse(self.student.id).read(['name'])[0]['name'], 'Private Student')
        action = self.family.with_user(self.manager).action_open_family_members()
        self.assertEqual(action['res_model'], 'res.partner')
        self.assertEqual(action['domain'], [('afa_family_id', '=', self.family.id)])
        self.assertEqual(action['context']['default_afa_family_id'], self.family.id)
        self.assertFalse(self.env['afa.family'].with_user(self.staff).has_access('read'))

    def test_staff_cannot_read_family_fields_on_visible_guardian(self):
        guardian = self.guardian.with_user(self.staff)
        with self.assertRaises(AccessError):
            guardian.read(['afa_family_id'])
        with self.assertRaises(AccessError):
            guardian.read(['afa_family_role'])
        guardian.write({'phone': '555 0134'})
        self.assertEqual(self.guardian.phone, '555 0134')

    def test_family_views_expose_sections_and_manager_menu(self):
        form = self.env.ref('afa_family.view_afa_family_form')
        self.assertIn('guardian_ids', form.arch_db)
        self.assertIn('student_ids', form.arch_db)
        self.assertIn('billing_partner_id', form.arch_db)
        self.assertTrue(self.env.ref('afa_family.menu_afa_family_root').group_ids &
                        self.env.ref('afa_family.group_family_manager'))
        partner_form = self.env.ref('afa_family.view_partner_form_afa_family')
        self.assertIn('afa_family.group_family_manager', partner_form.arch_db)
