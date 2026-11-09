from odoo import Command, _, fields, models
from odoo.exceptions import AccessError, UserError


class AfaVotingAddFamiliesWizard(models.TransientModel):
    _name = 'afa.voting.add.families.wizard'
    _description = 'Add Families to an AFA Voting'

    voting_id = fields.Many2one(
        'afa.voting',
        domain=[('state', '=', 'draft')],
        string='Draft Voting',
    )
    family_ids = fields.Many2many('afa.family', required=True, string='Families', readonly=True)

    def action_add_families(self):
        self.ensure_one()
        if not self.env.user.has_group('afa_voting.group_voting_manager'):
            raise AccessError(_('Only voting managers can add families to a voting.'))
        if not self.voting_id:
            raise UserError(_('Select a draft voting.'))
        if self.voting_id.state != 'draft':
            raise UserError(_('Families can only be added to a draft voting.'))
        self.voting_id.write(
            {'participant_family_ids': [Command.link(family.id) for family in self.family_ids]}
        )
        return {'type': 'ir.actions.act_window_close'}
