from odoo import fields, models


class AfaVotingInvitationHistory(models.Model):
    _name = 'afa.voting.invitation.history'
    _description = 'AFA Voting Invitation History'
    _order = 'revoked_at desc, id desc'

    invitation_id = fields.Many2one(
        'afa.voting.invitation', required=True, ondelete='cascade', index=True
    )
    recipient_partner_id = fields.Many2one('res.partner', required=True, ondelete='restrict')
    token_hash = fields.Char(required=True, copy=False)
    issued_at = fields.Datetime(required=True)
    revoked_at = fields.Datetime(required=True)
    state = fields.Selection([('revoked', 'Revoked')], required=True, default='revoked')
