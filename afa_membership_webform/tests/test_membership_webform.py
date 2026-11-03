from odoo.tests.common import HttpCase


class TestMembershipWebform(HttpCase):
    def test_public_form_is_available_and_lists_courses(self):
        course = self.env['afa.school.course'].create({'name': 'P4', 'sequence': 4})

        response = self.url_open('/alta-socia')

        self.assertEqual(response.status_code, 200)
        self.assertIn('Alta de sòcia', response.text)
        self.assertIn(f'value="{course.id}"', response.text)
        self.assertIn('name="mandate_accepted"', response.text)

    def test_install_hook_replaces_homepage_google_form_links(self):
        home = self.env['website.page'].search([('url', '=', '/')], limit=1)

        self.assertIn('/alta-socia', home.arch)
        self.assertNotIn('docs.google.com/forms', home.arch)
