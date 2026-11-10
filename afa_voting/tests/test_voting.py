import hashlib
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestAfaVoting(TransactionCase):
    def setUp(self):
        super().setUp()
        partner_model = self.env['res.partner']
        self.guardian = partner_model.create(
            {
                'name': 'Voting Guardian',
                'email': 'guardian@example.test',
                'afa_family_role': 'guardian',
            }
        )
        self.family = self.env['afa.family'].create(
            {'name': 'Voting Family', 'billing_partner_id': self.guardian.id}
        )
        now = fields.Datetime.now()
        self.voting = self.env['afa.voting'].create(
            {
                'name': 'Annual choice',
                'description': '<p>Choose an option.</p>',
                'date_start': now - timedelta(hours=1),
                'date_end': now + timedelta(hours=1),
                'option_ids': [(0, 0, {'name': 'Option A'}), (0, 0, {'name': 'Option B'})],
                'participant_family_ids': [(6, 0, self.family.ids)],
            }
        )

    def test_publish_and_aggregate_results(self):
        self.voting.action_publish()
        invitation = self.voting.invitation_ids
        self.assertEqual(self.voting.state, 'open')
        self.assertEqual(invitation.recipient_partner_id, self.guardian)
        vote = (
            self.env['afa.voting.vote']
            .sudo()
            .with_context(_voting_cast_vote=True)
            .create(
                {
                    'voting_id': self.voting.id,
                    'family_id': self.family.id,
                    'invitation_id': invitation.id,
                    'recipient_partner_id': self.guardian.id,
                    'option_id': self.voting.option_ids[0].id,
                }
            )
        )
        invitation.sudo()._workflow_write({'state': 'voted', 'voted_at': vote.voted_at})
        self.assertEqual(self.voting.participant_count, 1)
        self.assertEqual(self.voting.vote_count, 1)
        self.assertEqual(self.voting.pending_count, 0)
        self.assertEqual(self.voting.participation_percent, 1.0)
        self.assertEqual(self.voting.option_ids[0].vote_count, 1)

    def test_only_closed_or_cancelled_votings_can_be_archived(self):
        with self.assertRaises(UserError):
            self.voting.write({'active': False})

        self.voting.action_cancel()
        self.voting.write({'active': False})

        self.assertFalse(self.voting.active)
        self.assertFalse(self.env['afa.voting'].search([('id', '=', self.voting.id)]))
        self.assertTrue(
            self.env['afa.voting']
            .with_context(active_test=False)
            .search([('id', '=', self.voting.id)])
        )

    def test_invitation_email_contains_raw_token_but_model_stores_only_hash(self):
        token = 'generated-private-token'
        with patch(
            'odoo.addons.afa_voting.models.voting_invitation.secrets.token_urlsafe',
            return_value=token,
        ):
            self.voting.action_publish()
        invitation = self.voting.invitation_ids
        self.assertEqual(invitation.token_hash, hashlib.sha256(token.encode()).hexdigest())
        self.assertNotEqual(invitation.token_hash, token)
        mail = self.env['mail.mail'].search(
            [('model', '=', 'afa.voting.invitation'), ('res_id', '=', invitation.id)],
            order='id desc',
            limit=1,
        )
        self.assertIn(f'/afa/vote#{token}', mail.body_html)

    def test_options_and_participants_are_frozen_on_publication(self):
        self.voting.action_publish()
        with self.assertRaises(UserError), self.cr.savepoint():
            self.voting.option_ids[0].write({'name': 'Changed'})
        with self.assertRaises(UserError), self.cr.savepoint():
            self.voting.write({'participant_family_ids': [(5, 0, 0)]})

    def test_workflow_fields_cannot_be_changed_with_forged_context(self):
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.voting.with_context(_voting_state_transition=True).write({'state': 'open'})
        self.voting.action_publish()
        invitation = self.voting.invitation_ids
        with self.assertRaises(AccessError), self.cr.savepoint():
            invitation.with_context(_voting_internal=True).write({'state': 'revoked'})

    def test_invitation_cannot_be_moved_into_published_voting(self):
        invitation = self.env['afa.voting.invitation'].create(
            {
                'voting_id': self.voting.id,
                'family_id': self.family.id,
                'recipient_partner_id': self.guardian.id,
            }
        )
        other_guardian = self.env['res.partner'].create(
            {
                'name': 'Other Guardian',
                'email': 'other@example.test',
                'afa_family_role': 'guardian',
            }
        )
        other_family = self.env['afa.family'].create(
            {'name': 'Other Family', 'billing_partner_id': other_guardian.id}
        )
        destination = self.env['afa.voting'].create(
            {
                'name': 'Published destination',
                'date_start': fields.Datetime.now() - timedelta(hours=1),
                'date_end': fields.Datetime.now() + timedelta(hours=1),
                'option_ids': [(0, 0, {'name': 'A'}), (0, 0, {'name': 'B'})],
                'participant_family_ids': [(6, 0, other_family.ids)],
            }
        )
        destination.action_publish()
        with self.assertRaises(UserError), self.cr.savepoint():
            invitation.write({'voting_id': destination.id})
        self.assertEqual(invitation.voting_id, self.voting)

    def test_catalan_translations_are_loaded(self):
        voting_fields = self.env['afa.voting'].with_context(lang='ca_ES').fields_get(['state'])
        state_labels = dict(voting_fields['state']['selection'])
        menu = self.env.ref('afa_voting.menu_afa_voting').with_context(lang='ca_ES')
        add_action = self.env.ref('afa_voting.server_action_add_families_to_voting').with_context(
            lang='ca_ES'
        )

        self.assertEqual(state_labels['draft'], 'Esborrany')
        self.assertEqual(state_labels['open'], 'Oberta')
        self.assertEqual(menu.name, 'Votacions')
        self.assertEqual(add_action.name, 'Afegeix a la votació')

    def test_vote_cannot_be_changed_or_deleted(self):
        self.voting.action_publish()
        invitation = self.voting.invitation_ids
        vote = (
            self.env['afa.voting.vote']
            .sudo()
            .with_context(_voting_cast_vote=True)
            .create(
                {
                    'voting_id': self.voting.id,
                    'family_id': self.family.id,
                    'invitation_id': invitation.id,
                    'recipient_partner_id': self.guardian.id,
                    'option_id': self.voting.option_ids[0].id,
                }
            )
        )
        with self.assertRaises(UserError), self.cr.savepoint():
            vote.write({'option_id': self.voting.option_ids[1].id})
        with self.assertRaises(UserError), self.cr.savepoint():
            vote.unlink()

    def test_vote_rejects_option_from_another_voting(self):
        self.voting.action_publish()
        other_voting = self.env['afa.voting'].create(
            {
                'name': 'Other voting',
                'date_start': fields.Datetime.now() - timedelta(hours=1),
                'date_end': fields.Datetime.now() + timedelta(hours=1),
                'option_ids': [(0, 0, {'name': 'Other A'}), (0, 0, {'name': 'Other B'})],
            }
        )
        invitation = self.voting.invitation_ids
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['afa.voting.vote'].sudo().with_context(_voting_cast_vote=True).create(
                {
                    'voting_id': self.voting.id,
                    'family_id': self.family.id,
                    'invitation_id': invitation.id,
                    'recipient_partner_id': self.guardian.id,
                    'option_id': other_voting.option_ids[0].id,
                }
            )

    def test_vote_rejected_before_start_time(self):
        future = self.env['afa.voting'].create(
            {
                'name': 'Future voting',
                'date_start': fields.Datetime.now() + timedelta(hours=1),
                'date_end': fields.Datetime.now() + timedelta(hours=2),
                'option_ids': [(0, 0, {'name': 'Future A'}), (0, 0, {'name': 'Future B'})],
                'participant_family_ids': [(6, 0, self.family.ids)],
            }
        )
        future.action_publish()
        invitation = future.invitation_ids
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['afa.voting.vote'].sudo().with_context(_voting_cast_vote=True).create(
                {
                    'voting_id': future.id,
                    'family_id': self.family.id,
                    'invitation_id': invitation.id,
                    'recipient_partner_id': self.guardian.id,
                    'option_id': future.option_ids[0].id,
                }
            )

    def test_pending_invitation_tracks_billing_guardian_change_and_rotates_token(self):
        self.voting.action_publish()
        invitation = self.voting.invitation_ids
        previous_hash = invitation.token_hash
        replacement = self.env['res.partner'].create(
            {
                'name': 'Replacement Guardian',
                'email': 'replacement@example.test',
                'afa_family_id': self.family.id,
                'afa_family_role': 'guardian',
            }
        )
        self.family.write({'billing_partner_id': replacement.id})
        self.assertEqual(invitation.recipient_partner_id, replacement)
        self.assertEqual(invitation.state, 'pending')
        self.assertTrue(invitation.token_hash)
        self.assertNotEqual(invitation.token_hash, previous_hash)
        history = invitation.history_ids
        self.assertEqual(len(history), 1)
        self.assertEqual(history.recipient_partner_id, self.guardian)
        self.assertEqual(history.token_hash, previous_hash)
        self.assertEqual(history.state, 'revoked')

    def test_cron_closes_expired_voting_idempotently(self):
        expired = self.env['afa.voting'].create(
            {
                'name': 'Expired choice',
                'date_start': fields.Datetime.now() - timedelta(hours=3),
                'date_end': fields.Datetime.now() - timedelta(hours=2),
                'option_ids': [(0, 0, {'name': 'A'}), (0, 0, {'name': 'B'})],
                'participant_family_ids': [(6, 0, self.family.ids)],
            }
        )
        expired.action_publish()
        self.env['afa.voting']._cron_close_expired()
        self.assertEqual(expired.state, 'closed')
        self.assertEqual(self.env['afa.voting']._cron_close_expired(), 0)
