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

    def test_actions_menu_opens_wizard_with_multiple_selected_families(self):
        second_guardian = self.env['res.partner'].create(
            {
                'name': 'Second Voting Guardian',
                'email': 'second-guardian@example.test',
                'afa_family_role': 'guardian',
            }
        )
        second_family = self.env['afa.family'].create(
            {'name': 'Second Voting Family', 'billing_partner_id': second_guardian.id}
        )
        families = self.family | second_family
        server_action = self.env.ref('afa_voting.server_action_add_families_to_voting')
        action = server_action.with_context(
            active_model='afa.family',
            active_id=families[0].id,
            active_ids=families.ids,
        ).run()

        self.assertEqual(action['res_model'], 'afa.voting.add.families.wizard')
        self.assertEqual(action['target'], 'new')
        wizard = self.env[action['res_model']].browse(action['res_id'])
        self.assertEqual(wizard.family_ids, families)

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
        self.assertEqual(voting_menu.parent_id, family_menu)
        self.assertIn(self.env.ref('afa_voting.group_voting_user'), family_menu.group_ids)
        server_action = self.env.ref('afa_voting.server_action_add_families_to_voting')
        self.assertEqual(server_action.binding_model_id.model, 'afa.family')
        self.assertEqual(server_action.binding_view_types, 'list')
        self.assertIn(self.env.ref('afa_voting.group_voting_manager'), server_action.group_ids)
