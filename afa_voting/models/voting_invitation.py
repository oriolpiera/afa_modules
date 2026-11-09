import hashlib
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class AfaVotingInvitation(models.Model):
    _name = 'afa.voting.invitation'
    _description = 'AFA Voting Invitation'

    voting_id = fields.Many2one('afa.voting', required=True, ondelete='cascade', index=True)
    family_id = fields.Many2one('afa.family', required=True, ondelete='restrict', index=True)
    recipient_partner_id = fields.Many2one('res.partner', required=True, ondelete='restrict')
    token_hash = fields.Char(copy=False, index=True)
    issued_at = fields.Datetime(readonly=True)
    history_ids = fields.One2many('afa.voting.invitation.history', 'invitation_id')
    state = fields.Selection(
        [('pending', 'Pending'), ('voted', 'Voted'), ('revoked', 'Revoked')],
        required=True,
        default='pending',
        index=True,
    )
    voted_at = fields.Datetime(readonly=True)
    _voting_family_unique = models.Constraint(
        'UNIQUE(voting_id, family_id)',
        'A family can only be invited once per voting.',
    )
    _token_hash_unique = models.Constraint(
        'UNIQUE(token_hash)', 'Invitation token hashes must be unique.'
    )

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [
            dict(vals, token_hash=False, issued_at=False, state='pending', voted_at=False)
            for vals in vals_list
        ]
        for vals in vals_list:
            voting = self.env['afa.voting'].browse(vals.get('voting_id'))
            if voting.state != 'draft':
                raise AccessError(_('Invitations can only be prepared for draft votings.'))
            if vals.get('family_id') not in voting.participant_family_ids.ids:
                raise ValidationError(_('The invited family must be selected as a participant.'))
        return super().create(vals_list)

    @api.constrains('family_id', 'recipient_partner_id')
    def _check_recipient(self):
        for invitation in self:
            if (
                invitation.recipient_partner_id.afa_family_id != invitation.family_id
                or invitation.recipient_partner_id.afa_family_role != 'guardian'
            ):
                raise ValidationError(
                    _('The invitation recipient must be a guardian of the invited family.')
                )

    def write(self, vals):
        if {'state', 'token_hash', 'issued_at', 'voted_at', 'recipient_partner_id'} & set(vals):
            raise AccessError(
                _('Invitation state and credentials are managed by the voting workflow.')
            )
        if any(item.voting_id.state != 'draft' for item in self) and {
            'voting_id',
            'family_id',
        } & set(vals):
            raise UserError(_('Published participants cannot be changed.'))
        if {'voting_id', 'family_id'} & set(vals):
            for invitation in self:
                voting = self.env['afa.voting'].browse(
                    vals.get('voting_id', invitation.voting_id.id)
                )
                family = self.env['afa.family'].browse(
                    vals.get('family_id', invitation.family_id.id)
                )
                if voting.state != 'draft':
                    raise UserError(_('Invitations cannot be moved into a published voting.'))
                if family not in voting.participant_family_ids:
                    raise ValidationError(
                        _('The invited family must be selected as a participant.')
                    )
        return super().write(vals)

    def unlink(self):
        if any(invitation.voting_id.state != 'draft' for invitation in self):
            raise AccessError(_('Published invitations cannot be deleted.'))
        return super().unlink()

    def _workflow_write(self, vals):
        if not self.env.su:
            raise AccessError(_('Invitation workflow updates require elevated internal access.'))
        return super().write(vals)

    def _archive_current_credential(self):
        if not self.env.su:
            raise AccessError(_('Invitation history updates require elevated internal access.'))
        now = fields.Datetime.now()
        for invitation in self.filtered('token_hash'):
            self.env['afa.voting.invitation.history'].sudo().create(
                {
                    'invitation_id': invitation.id,
                    'recipient_partner_id': invitation.recipient_partner_id.id,
                    'token_hash': invitation.token_hash,
                    'issued_at': invitation.issued_at or now,
                    'revoked_at': now,
                }
            )
            invitation._workflow_write({'token_hash': False})

    def action_send(self):
        if not self.env.su and not self.env.user.has_group('afa_voting.group_voting_manager'):
            raise AccessError(_('Only voting managers can send invitations.'))
        template = self.env.ref('afa_voting.mail_template_voting_invitation')
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for invitation in self:
            if invitation.voting_id.state != 'open' or invitation.state != 'pending':
                continue
            if not invitation.recipient_partner_id.email:
                continue
            invitation.sudo()._archive_current_credential()
            token = secrets.token_urlsafe(32)
            invitation.sudo()._workflow_write(
                {
                    'token_hash': hashlib.sha256(token.encode()).hexdigest(),
                    'issued_at': fields.Datetime.now(),
                }
            )
            template.with_context(voting_url=f'{base_url}/afa/vote#{token}').send_mail(
                invitation.id,
                force_send=False,
                email_values={'email_to': invitation.recipient_partner_id.email},
            )
        return True
