from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class AfaVotingVote(models.Model):
    _name = 'afa.voting.vote'
    _description = 'AFA Voting Vote'
    _order = 'voted_at desc, id desc'

    voting_id = fields.Many2one('afa.voting', required=True, ondelete='restrict', index=True)
    family_id = fields.Many2one('afa.family', required=True, ondelete='restrict', index=True)
    invitation_id = fields.Many2one(
        'afa.voting.invitation', required=True, ondelete='restrict', index=True
    )
    recipient_partner_id = fields.Many2one('res.partner', required=True, ondelete='restrict')
    option_id = fields.Many2one('afa.voting.option', required=True, ondelete='restrict')
    voted_at = fields.Datetime(required=True, default=fields.Datetime.now, readonly=True)
    _voting_family_vote_unique = models.Constraint(
        'UNIQUE(voting_id, family_id)',
        'A family can only vote once per voting.',
    )
    _invitation_vote_unique = models.Constraint(
        'UNIQUE(invitation_id)', 'An invitation can only be used once.'
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('_voting_cast_vote'):
            raise AccessError(_('Votes can only be created through the private voting link.'))
        records = super().create(vals_list)
        records._check_integrity()
        return records

    def write(self, vals):
        raise UserError(_('A submitted vote is final and cannot be changed.'))

    def unlink(self):
        raise UserError(_('Submitted votes cannot be deleted.'))

    @api.constrains('voting_id', 'family_id', 'invitation_id', 'recipient_partner_id', 'option_id')
    def _check_integrity(self):
        for vote in self:
            invitation = vote.invitation_id
            if (
                vote.option_id.voting_id != vote.voting_id
                or invitation.voting_id != vote.voting_id
                or invitation.family_id != vote.family_id
                or invitation.recipient_partner_id != vote.recipient_partner_id
            ):
                raise ValidationError(
                    _('The vote, option, family and invitation must belong together.')
                )
            if vote.voting_id.state != 'open':
                raise ValidationError(_('Votes are accepted only while voting is open.'))
            now = fields.Datetime.now()
            if now < vote.voting_id.date_start or now > vote.voting_id.date_end:
                raise ValidationError(_('Voting is outside the permitted period.'))
