from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestWebsiteHeaderAccount(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        portal_group = cls.env.ref('base.group_portal')
        cls.family_user = cls.env['res.users'].create(
            {
                'name': 'Família Prova',
                'login': 'familia.prova@example.test',
                'email': 'familia.prova@example.test',
                'password': 'test-password',
                'group_ids': [(6, 0, portal_group.ids)],
            }
        )

    def test_anonymous_header_shows_sign_in(self):
        response = self.url_open('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Inicia sessió', response.text)
        self.assertNotIn('El meu compte', response.text)

    def test_authenticated_header_shows_account_menu(self):
        self.authenticate('familia.prova@example.test', 'test-password')
        response = self.url_open('/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Inicia sessió', response.text)
        self.assertIn('Família Prova', response.text)
        self.assertIn('El meu compte', response.text)
