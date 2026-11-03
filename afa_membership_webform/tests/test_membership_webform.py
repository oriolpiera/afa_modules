import re

from odoo.tests.common import HttpCase

VALID_IBAN = 'ES9121000418450200051332'


class TestMembershipWebform(HttpCase):
    def _course(self):
        return self.env['afa.school.course'].create({'name': 'P4', 'sequence': 4})

    def _form_token(self):
        response = self.url_open('/alta-socia')
        match = re.search(r'name="csrf_token"\s+value=[\'"]([^\'"]+)', response.text)
        self.assertIsNotNone(match)
        return match.group(1)

    def _submission(self, course_id, **overrides):
        data = {
            'csrf_token': self._form_token(),
            'guardian1_name': 'Aina Sol',
            'guardian1_vat': 'DNI1001',
            'guardian1_email': 'aina@example.cat',
            'guardian1_phone': '+34600000001',
            'guardian2_name': '',
            'guardian2_vat': '',
            'guardian2_email': '',
            'guardian2_phone': '',
            'address': 'Carrer de l’Escola, 1, les Preses',
            'student_name': ['Pol Sol'],
            'student_birthday': ['2020-03-15'],
            'student_course': [str(course_id)],
            'wants_membership': 'yes',
            'iban': VALID_IBAN,
            'mandate_accepted': 'yes',
        }
        data.update(overrides)
        return data

    def test_public_form_is_available_and_lists_courses(self):
        course = self._course()

        response = self.url_open('/alta-socia')

        self.assertEqual(response.status_code, 200)
        self.assertIn('Alta de sòcia', response.text)
        self.assertIn(f'value="{course.id}"', response.text)
        self.assertIn('id="iban"', response.text)
        self.assertIn('name="mandate_accepted"', response.text)

    def test_valid_submission_creates_pending_application_only(self):
        course = self._course()

        response = self.url_open(
            '/alta-socia/submit',
            data=self._submission(
                course.id,
                guardian2_name='Joan Sol',
                guardian2_vat='DNI1002',
                guardian2_email='joan@example.cat',
                guardian2_phone='+34600000002',
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('Hem rebut la vostra sol·licitud', response.text)
        application = self.env['afa.membership.application'].search(
            [('guardian1_vat', '=', 'DNI1001')]
        )
        self.assertEqual(len(application), 1)
        self.assertEqual(application.state, 'pending')
        self.assertEqual(application.guardian1_email, 'aina@example.cat')
        self.assertEqual(application.guardian1_phone, '+34600000001')
        self.assertEqual(application.guardian2_email, 'joan@example.cat')
        self.assertEqual(application.guardian2_phone, '+34600000002')
        self.assertEqual(application.student_ids.name, 'Pol Sol')
        self.assertFalse(self.env['res.partner'].search([('vat', '=', 'DNI1001')]))

    def test_invalid_submission_preserves_values_and_creates_nothing(self):
        course = self._course()
        data = self._submission(
            course.id,
            iban='invalid',
            student_name=['Pol Sol', 'Laia Sol'],
            student_birthday=['2020-03-15', '2018-08-10'],
            student_course=[str(course.id), str(course.id)],
        )

        response = self.url_open('/alta-socia/submit', data=data)

        self.assertEqual(response.status_code, 400)
        self.assertIn('Introduïu un IBAN vàlid.', response.text)
        self.assertIn('value="Aina Sol"', response.text)
        self.assertIn('value="aina@example.cat"', response.text)
        self.assertIn('value="Pol Sol"', response.text)
        self.assertIn('value="Laia Sol"', response.text)
        self.assertIn('value="INVALID"', response.text)
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')
        self.assertFalse(self.env['afa.membership.application'].search([]))
        self.assertFalse(self.env['res.partner'].search([('vat', '=', 'DNI1001')]))

    def test_guardian_id_wildcards_are_rejected(self):
        course = self._course()

        response = self.url_open(
            '/alta-socia/submit',
            data=self._submission(course.id, guardian1_vat='DNI%_'),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('DNI del primer tutor', response.text)
        self.assertFalse(self.env['afa.membership.application'].search([]))

    def test_honeypot_submission_creates_nothing(self):
        course = self._course()

        response = self.url_open(
            '/alta-socia/submit',
            data=self._submission(course.id, website_url='https://spam.example'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('Hem rebut la vostra sol·licitud', response.text)
        self.assertFalse(self.env['afa.membership.application'].search([]))
        self.assertFalse(self.env['res.partner'].search([('vat', '=', 'DNI1001')]))

    def test_course_setup_populates_preview_form_options(self):
        self.env['afa.school.course.setup.wizard'].create(
            {'infantil': True, 'primaria': True}
        ).action_confirm()

        courses = self.env['afa.school.course'].search([])

        self.assertEqual(
            courses.mapped('name'),
            ['i3', 'i4', 'i5', '1r', '2n', '3r', '4t', '5è', '6è'],
        )

    def test_install_hook_replaces_homepage_google_form_links(self):
        home = self.env['website.page'].search([('url', '=', '/')], limit=1)

        self.assertIn('/alta-socia', home.arch)
        self.assertNotIn('docs.google.com/forms', home.arch)
