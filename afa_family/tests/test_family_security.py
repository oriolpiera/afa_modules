from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestFamilySecurity(TransactionCase):
    def setUp(self):
        super().setUp()
        group_user = self.env.ref('base.group_user')
        group_contacts = self.env.ref('base.group_partner_manager')
        group_manager = self.env.ref('afa_family.group_family_manager')
        self.staff = self.env['res.users'].create(
            {
                'name': 'Contacts Staff',
                'login': 'contacts_staff_family_test',
                'group_ids': [(6, 0, (group_user | group_contacts).ids)],
            }
        )
        self.manager = self.env['res.users'].create(
            {
                'name': 'Family Manager',
                'login': 'family_manager_test',
                'group_ids': [(6, 0, (group_user | group_manager).ids)],
            }
        )
        partners = self.env['res.partner'].with_user(self.manager)
        guardian = partners.create({'name': 'Guardian', 'afa_family_role': 'guardian'})
        self.family = (
            self.env['afa.family']
            .with_user(self.manager)
            .create(
                {
                    'name': 'Family',
                    'billing_partner_id': guardian.id,
                }
            )
        )
        self.student = partners.create(
            {
                'name': 'Private Student',
                'afa_family_id': self.family.id,
                'afa_family_role': 'student',
            }
        )
        self.guardian = guardian
        self.unrelated = partners.create({'name': 'Unrelated Contact'})

    def test_manager_and_contacts_staff_can_create_permitted_contacts(self):
        partners = self.env['res.partner'].with_user(self.manager)
        for operation in ('read', 'write', 'create', 'unlink'):
            self.assertTrue(partners.has_access(operation))
        staff_partners = self.env['res.partner'].with_user(self.staff)
        self.assertTrue(staff_partners.has_access('create'))
        self.assertEqual(
            staff_partners.create({'name': 'Ordinary Contact'}).name, 'Ordinary Contact'
        )

    def test_staff_cannot_find_or_read_students_through_contacts(self):
        partners = self.env['res.partner'].with_user(self.staff)
        self.assertFalse(partners.search([('id', '=', self.student.id)]))
        self.assertFalse(partners.search([('name', '=', 'Private Student')]))
        self.assertNotIn(self.student.id, partners.search([]).ids)
        with self.assertRaises(AccessError):
            partners.browse(self.student.id).read(['name'])
        self.assertEqual(partners.browse(self.guardian.id).read(['name'])[0]['name'], 'Guardian')
        self.assertEqual(
            partners.browse(self.unrelated.id).read(['name'])[0]['name'], 'Unrelated Contact'
        )
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
        self.assertEqual(
            partners.browse(self.student.id).read(['name'])[0]['name'], 'Private Student'
        )
        action = self.family.with_user(self.manager).action_open_family_members()
        self.assertEqual(action['res_model'], 'res.partner')
        self.assertEqual(action['domain'], [('afa_family_id', '=', self.family.id)])
        self.assertEqual(action['context']['default_afa_family_id'], self.family.id)
        self.assertFalse(self.env['afa.family'].with_user(self.staff).has_access('read'))

    def test_existing_member_wizard_is_manager_only(self):
        wizard_model = self.env['afa.family.member.add.wizard']
        self.assertTrue(wizard_model.with_user(self.manager).has_access('create'))
        self.assertFalse(wizard_model.with_user(self.staff).has_access('create'))
        with self.assertRaises(AccessError):
            wizard_model.with_user(self.staff).create(
                {
                    'family_id': self.family.id,
                    'role': 'guardian',
                    'partner_ids': [(6, 0, [self.unrelated.id])],
                }
            )

        wizard = wizard_model.create(
            {
                'family_id': self.family.id,
                'role': 'guardian',
                'partner_ids': [(6, 0, [self.unrelated.id])],
            }
        )
        with self.assertRaises(AccessError):
            wizard.with_user(self.staff).action_add_members()
        with self.assertRaises(AccessError):
            self.family.with_user(self.staff).action_open_add_existing_guardians()

        candidate = (
            self.env['res.partner']
            .with_user(self.manager)
            .create({'name': 'Manager-selected Guardian'})
        )
        manager_wizard = wizard_model.with_user(self.manager).create(
            {
                'family_id': self.family.id,
                'role': 'guardian',
                'partner_ids': [(6, 0, [candidate.id])],
            }
        )
        manager_wizard.action_add_members()
        self.assertEqual(candidate.afa_family_id, self.family)
        self.assertEqual(candidate.afa_family_role, 'guardian')

    def test_family_form_has_add_existing_actions_on_both_tabs(self):
        form = self.env.ref('afa_family.view_afa_family_form')
        self.assertIn('action_open_add_existing_guardians', form.arch_db)
        self.assertIn('action_open_add_existing_students', form.arch_db)

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
        self.assertTrue(
            self.env.ref('afa_family.menu_afa_family_root').group_ids
            & self.env.ref('afa_family.group_family_manager')
        )
        partner_form = self.env.ref('afa_family.view_partner_form_afa_family')
        self.assertIn('afa_family.group_family_manager', partner_form.arch_db)
        partner_list = self.env.ref('afa_family.view_partner_list_afa_family')
        self.assertIn('afa_family_role', partner_list.arch_db)
        self.assertIn('afa_family.group_family_manager', partner_list.arch_db)
