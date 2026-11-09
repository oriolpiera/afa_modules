from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestAfaVotingFamilyEntrypoint(TransactionCase):
    def setUp(self):
        super().setUp()
        guardian = self.env['res.partner'].create(
            {
                'name': 'Voting Guardian',
                'email': 'guardian@example.test',
                'afa_family_role': 'guardian',
            }
        )
        self.family = self.env['afa.family'].create(
            {'name': 'Voting Family', 'billing_partner_id': guardian.id}
        )

    def test_family_list_action_opens_preselected_add_to_voting_wizard(self):
        action = self.family.action_add_to_voting()

        self.assertEqual(action['res_model'], 'afa.voting.add.families.wizard')
        self.assertEqual(action['target'], 'new')
        wizard = self.env[action['res_model']].browse(action['res_id'])
        self.assertEqual(wizard.family_ids, self.family)

    def test_wizard_adds_family_to_selected_draft_voting(self):
        voting = self.env['afa.voting'].create(
            {
                'name': 'Draft ballot',
                'date_start': fields.Datetime.now() - timedelta(minutes=1),
                'date_end': fields.Datetime.now() + timedelta(hours=1),
                'option_ids': [(0, 0, {'name': 'A'}), (0, 0, {'name': 'B'})],
            }
        )
        wizard = self.env['afa.voting.add.families.wizard'].create(
            {'voting_id': voting.id, 'family_ids': [(6, 0, self.family.ids)]}
        )

        action = wizard.action_add_families()

        self.assertEqual(action['type'], 'ir.actions.act_window_close')
        self.assertIn(self.family, voting.participant_family_ids)

    def test_votings_menu_is_nested_under_afa_families(self):
        voting_menu = self.env.ref('afa_voting.menu_afa_voting')
        family_menu = self.env.ref('afa_family.menu_afa_family_root')
        family_list_view = self.env.ref('afa_voting.view_afa_family_list_add_to_voting')

        self.assertEqual(voting_menu.parent_id, family_menu)
        self.assertIn(self.env.ref('afa_voting.group_voting_user'), family_menu.group_ids)
        self.assertIn('action_add_to_voting', family_list_view.arch_db)
