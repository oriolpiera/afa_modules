import json

from odoo.tests.common import HttpCase


class TestAttendanceKioskPwa(HttpCase):
    def test_manifest_is_scoped_to_the_company_kiosk_url(self):
        token = self.env.company.sudo().attendance_kiosk_key

        page = self.url_open(f'/hr_attendance/{token}')
        self.assertEqual(page.status_code, 200)
        self.assertIn(f'pwa_manifest/{token}', page.text)

        response = self.url_open(f'/hr_attendance/pwa_manifest/{token}')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers['Content-Type'].startswith('application/manifest+json'))
        manifest = json.loads(response.text)
        expected_path = f'/hr_attendance/{token}'
        self.assertEqual(manifest['start_url'], expected_path)
        self.assertEqual(manifest['id'], expected_path)
        self.assertEqual(manifest['scope'], expected_path)
        self.assertEqual(manifest['display'], 'standalone')
        self.assertEqual(
            {icon['sizes'] for icon in manifest['icons']},
            {'192x192', '512x512'},
        )
        for icon in manifest['icons']:
            image = self.url_open(icon['src'])
            self.assertEqual(image.status_code, 200)
            self.assertEqual(image.headers['Content-Type'], 'image/png')

    def test_unknown_kiosk_token_has_no_manifest(self):
        response = self.url_open('/hr_attendance/pwa_manifest/not-a-valid-token')

        self.assertEqual(response.status_code, 404)
