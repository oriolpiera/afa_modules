from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestAfaVotingSecurity(TransactionCase):
    def test_results_user_cannot_read_individual_votes_or_invitations(self):
        user = self.env['res.users'].create(
            {
                'name': 'Voting Results User',
                'login': 'voting-results-user',
                'group_ids': [(6, 0, [self.env.ref('afa_voting.group_voting_user').id])],
            }
        )
        with self.assertRaises(AccessError):
            self.env['afa.voting.vote'].with_user(user).search([])
        with self.assertRaises(AccessError):
            self.env['afa.voting.invitation'].with_user(user).search([])
        with self.assertRaises(AccessError):
            self.env['afa.voting.invitation.history'].with_user(user).search([])

        guardian = self.env['res.partner'].create(
            {
                'name': 'Voting Guardian',
                'email': 'guardian@example.test',
                'afa_family_role': 'guardian',
            }
        )
        family = self.env['afa.family'].create(
            {'name': 'Voting Family', 'billing_partner_id': guardian.id}
        )
        voting = self.env['afa.voting'].create(
            {
                'name': 'Protected ballot',
                'date_start': fields.Datetime.now() - timedelta(minutes=1),
                'date_end': fields.Datetime.now() + timedelta(hours=1),
                'option_ids': [(0, 0, {'name': 'A'}), (0, 0, {'name': 'B'})],
                'participant_family_ids': [(6, 0, family.ids)],
            }
        )
        voting.action_publish()
        with self.assertRaises(AccessError):
            voting.with_user(user).action_close()
        self.assertEqual(voting.state, 'open')

    def test_public_user_has_no_backend_model_access(self):
        with self.assertRaises(AccessError):
            self.env['afa.voting'].with_user(self.env.ref('base.public_user')).search([])
