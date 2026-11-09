import hashlib
import re
from datetime import timedelta

from odoo import fields
from odoo.tests.common import HttpCase


class TestAfaVotingHttp(HttpCase):
    def setUp(self):
        super().setUp()
        self.token = 'a-private-test-bearer-token'
        guardian = self.env['res.partner'].create(
            {
                'name': 'Private Guardian Name',
                'email': 'private@example.test',
                'afa_family_role': 'guardian',
            }
        )
        family = self.env['afa.family'].create(
            {'name': 'Private Family Name', 'billing_partner_id': guardian.id}
        )
        now = fields.Datetime.now()
        voting = self.env['afa.voting'].create(
            {
                'name': 'Public ballot title',
                'description': '<p>Public ballot description</p>',
                'date_start': now - timedelta(minutes=1),
                'date_end': now + timedelta(hours=1),
                'option_ids': [(0, 0, {'name': 'Choice one'}), (0, 0, {'name': 'Choice two'})],
                'participant_family_ids': [(6, 0, family.ids)],
            }
        )
        voting.action_publish()
        self.invitation = voting.invitation_ids
        self.invitation.sudo()._workflow_write(
            {'token_hash': hashlib.sha256(self.token.encode()).hexdigest()}
        )
        self.voting = voting

    def test_public_page_hides_family_details_and_vote_is_single_use(self):
        landing = self.url_open('/afa/vote')
        self.assertEqual(landing.status_code, 200)
        self.assertNotIn(self.token, landing.url)
        csrf_match = re.search(r'name="csrf_token"\s+value=[\'\"]([^\'\"]+)', landing.text)
        self.assertTrue(csrf_match)
        page = self.url_open(
            '/afa/vote/open',
            data={'csrf_token': csrf_match.group(1), 'token': self.token},
        )
        self.assertEqual(page.status_code, 200)
        self.assertIn('Public ballot title', page.text)
        self.assertIn('Choice one', page.text)
        self.assertNotIn('Private Family Name', page.text)
        self.assertNotIn('Private Guardian Name', page.text)
        self.assertEqual(page.headers.get('Cache-Control'), 'no-store')

        page_csrf = re.search(r'name="csrf_token"\s+value=[\'\"]([^\'\"]+)', page.text)
        self.assertTrue(page_csrf)
        response = self.url_open(
            '/afa/vote/submit',
            data={
                'csrf_token': page_csrf.group(1),
                'token': self.token,
                'option_id': str(self.voting.option_ids[0].id),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('Vot registrat', response.text)
        self.assertEqual(self.env['afa.voting.vote'].sudo().search_count([]), 1)
        self.assertFalse(self.invitation.token_hash)

        repeated = self.url_open(
            '/afa/vote/submit',
            data={
                'csrf_token': page_csrf.group(1),
                'token': self.token,
                'option_id': str(self.voting.option_ids[0].id),
            },
        )
        self.assertEqual(repeated.status_code, 400)
        self.assertEqual(self.env['afa.voting.vote'].sudo().search_count([]), 1)

    def test_invalid_link_has_generic_response(self):
        landing = self.url_open('/afa/vote')
        csrf_match = re.search(r'name="csrf_token"\s+value=[\'\"]([^\'\"]+)', landing.text)
        response = self.url_open(
            '/afa/vote/open',
            data={'csrf_token': csrf_match.group(1), 'token': 'invalid-private-link'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Enllaç no disponible', response.text)
        self.assertNotIn('Private Family Name', response.text)

    def test_revoked_link_has_generic_response(self):
        self.voting.action_cancel()
        landing = self.url_open('/afa/vote')
        csrf_match = re.search(r'name="csrf_token"\s+value=[\'\"]([^\'\"]+)', landing.text)
        response = self.url_open(
            '/afa/vote/open',
            data={'csrf_token': csrf_match.group(1), 'token': self.token},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Enllaç no disponible', response.text)
