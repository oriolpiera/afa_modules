import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import requests
from psycopg2 import IntegrityError

from odoo import fields
from odoo.tests.common import TEST_CURSOR_COOKIE_NAME, HttpCase, TransactionCase


class TestAfaVotingConcurrency(TransactionCase):
    def test_database_unique_constraints_prevent_duplicate_invitation_and_vote(self):
        guardian = self.env['res.partner'].create(
            {
                'name': 'Guardian',
                'email': 'guardian@example.test',
                'afa_family_role': 'guardian',
            }
        )
        family = self.env['afa.family'].create(
            {'name': 'Family', 'billing_partner_id': guardian.id}
        )
        voting = self.env['afa.voting'].create(
            {
                'name': 'Choice',
                'date_start': fields.Datetime.now(),
                'date_end': fields.Datetime.add(fields.Datetime.now(), hours=1),
                'option_ids': [(0, 0, {'name': 'A'}), (0, 0, {'name': 'B'})],
                'participant_family_ids': [(6, 0, family.ids)],
            }
        )
        invitation = self.env['afa.voting.invitation'].create(
            {
                'voting_id': voting.id,
                'family_id': family.id,
                'recipient_partner_id': guardian.id,
            }
        )
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env['afa.voting.invitation'].create(
                {
                    'voting_id': voting.id,
                    'family_id': family.id,
                    'recipient_partner_id': guardian.id,
                }
            )
        voting.action_publish()
        vote_values = {
            'voting_id': voting.id,
            'family_id': family.id,
            'invitation_id': invitation.id,
            'recipient_partner_id': guardian.id,
            'option_id': voting.option_ids[0].id,
        }
        self.env['afa.voting.vote'].sudo().with_context(_voting_cast_vote=True).create(vote_values)
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env['afa.voting.vote'].sudo().with_context(_voting_cast_vote=True).create(
                vote_values
            )


class TestAfaVotingConcurrentSubmissions(HttpCase):
    def setUp(self):
        super().setUp()
        self.token = 'same-bearer-token-concurrent-submission'
        guardian = self.env['res.partner'].create(
            {
                'name': 'Concurrent Guardian',
                'email': 'concurrent@example.test',
                'afa_family_role': 'guardian',
            }
        )
        family = self.env['afa.family'].create(
            {'name': 'Concurrent Family', 'billing_partner_id': guardian.id}
        )
        now = fields.Datetime.now()
        self.voting = self.env['afa.voting'].create(
            {
                'name': 'Concurrent ballot',
                'date_start': now - timedelta(minutes=1),
                'date_end': now + timedelta(hours=1),
                'option_ids': [(0, 0, {'name': 'A'}), (0, 0, {'name': 'B'})],
                'participant_family_ids': [(6, 0, family.ids)],
            }
        )
        self.voting.action_publish()
        self.invitation = self.voting.invitation_ids
        self.invitation.sudo()._workflow_write(
            {'token_hash': hashlib.sha256(self.token.encode()).hexdigest()}
        )

    def test_two_simultaneous_posts_create_one_vote(self):
        landing = self.url_open('/afa/vote')
        landing_csrf = re.search(r'name="csrf_token"\s+value=[\'\"]([^\'\"]+)', landing.text)
        page = self.url_open(
            '/afa/vote/open',
            data={'csrf_token': landing_csrf.group(1), 'token': self.token},
        )
        page_csrf = re.search(r'name="csrf_token"\s+value=[\'\"]([^\'\"]+)', page.text)
        post_data = {
            'csrf_token': page_csrf.group(1),
            'token': self.token,
            'option_id': str(self.voting.option_ids[0].id),
        }

        with self.allow_requests():
            cookies = self.opener.cookies.get_dict()
            cookies[TEST_CURSOR_COOKIE_NAME] = self.http_request_key

            def submit_vote(_):
                return requests.post(
                    f'{self.base_url()}/afa/vote/submit',
                    data=post_data,
                    cookies=cookies,
                    timeout=20,
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(submit_vote, range(2)))

        self.assertCountEqual([response.status_code for response in responses], [200, 400])
        self.assertEqual(self.env['afa.voting.vote'].sudo().search_count([]), 1)
        self.assertEqual(self.invitation.state, 'voted')
