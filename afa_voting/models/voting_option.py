from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AfaVotingOption(models.Model):
    _name = 'afa.voting.option'
    _description = 'AFA Voting Option'
    _order = 'sequence, id'

    voting_id = fields.Many2one('afa.voting', required=True, ondelete='cascade', index=True)
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    vote_count = fields.Integer(
        compute='_compute_results', compute_sudo=True, groups='afa_voting.group_voting_user'
    )
    vote_percent = fields.Float(
        compute='_compute_results', compute_sudo=True, groups='afa_voting.group_voting_user'
    )

    @api.depends('voting_id.vote_ids.option_id')
    def _compute_results(self):
        for option in self:
            vote_model = self.env['afa.voting.vote'].sudo()
            total = vote_model.search_count([('voting_id', '=', option.voting_id.id)])
            count = vote_model.search_count(
                [('voting_id', '=', option.voting_id.id), ('option_id', '=', option.id)]
            )
            option.vote_count = count
            option.vote_percent = count / total if total else 0.0

    @api.constrains('voting_id')
    def _check_draft(self):
        if any(option.voting_id.state != 'draft' for option in self):
            raise UserError(_('Options cannot be changed after publication.'))

    def write(self, vals):
        if any(option.voting_id.state != 'draft' for option in self):
            raise UserError(_('Options cannot be changed after publication.'))
        return super().write(vals)

    def unlink(self):
        if any(option.voting_id.state != 'draft' for option in self):
            raise UserError(_('Options cannot be changed after publication.'))
        return super().unlink()
