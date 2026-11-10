from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class AfaVoting(models.Model):
    _name = 'afa.voting'
    _description = 'AFA Voting'
    _inherit = ['mail.thread', 'mail.activity.mixin']  # noqa: RUF012
    _order = 'date_start desc, id desc'

    name = fields.Char(required=True, tracking=True)
    description = fields.Html()
    date_start = fields.Datetime(required=True, tracking=True)
    date_end = fields.Datetime(required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('open', 'Open'), ('closed', 'Closed'), ('cancelled', 'Cancelled')],
        required=True,
        default='draft',
        tracking=True,
    )
    option_ids = fields.One2many('afa.voting.option', 'voting_id', string='Options')
    participant_family_ids = fields.Many2many(
        'afa.family', 'afa_voting_family_rel', 'voting_id', 'family_id', string='Families'
    )
    invitation_ids = fields.One2many('afa.voting.invitation', 'voting_id')
    vote_ids = fields.One2many('afa.voting.vote', 'voting_id')
    participant_count = fields.Integer(
        compute='_compute_results', compute_sudo=True, groups='afa_voting.group_voting_user'
    )
    vote_count = fields.Integer(
        compute='_compute_results', compute_sudo=True, groups='afa_voting.group_voting_user'
    )
    pending_count = fields.Integer(
        compute='_compute_results', compute_sudo=True, groups='afa_voting.group_voting_user'
    )
    participation_percent = fields.Float(
        compute='_compute_results', compute_sudo=True, groups='afa_voting.group_voting_user'
    )
    option_result_ids = fields.One2many(
        'afa.voting.option', 'voting_id', string='Results', groups='afa_voting.group_voting_user'
    )

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get('state', 'draft') != 'draft' for vals in vals_list):
            raise AccessError(_('Votings must be created as drafts.'))
        return super().create(vals_list)

    @api.depends('invitation_ids', 'invitation_ids.state', 'vote_ids')
    def _compute_results(self):
        for voting in self:
            participants = (
                self.env['afa.voting.invitation']
                .sudo()
                .search_count([('voting_id', '=', voting.id)])
            )
            votes = self.env['afa.voting.vote'].sudo().search_count([('voting_id', '=', voting.id)])
            voting.participant_count = participants
            voting.vote_count = votes
            voting.pending_count = participants - votes
            voting.participation_percent = votes / participants if participants else 0.0

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for voting in self:
            if voting.date_start and voting.date_end and voting.date_end <= voting.date_start:
                raise ValidationError(_('The end date must be after the start date.'))

    def write(self, vals):
        if vals.get('active') is False and any(
            record.state not in ('closed', 'cancelled') for record in self
        ):
            raise UserError(_('Only closed or cancelled votings can be archived.'))
        if 'state' in vals:
            raise AccessError(_('Voting state can only be changed through its workflow actions.'))
        if any(record.state != 'draft' for record in self) and set(vals) & {
            'name',
            'description',
            'date_start',
            'date_end',
            'option_ids',
            'participant_family_ids',
        }:
            raise UserError(_('Published voting details and participants cannot be changed.'))
        return super().write(vals)

    def action_publish(self):
        self._check_voting_manager()
        for voting in self:
            if voting.state != 'draft':
                raise UserError(_('Only draft votings can be published.'))
            if len(voting.option_ids) < 2 or not voting.participant_family_ids:
                raise ValidationError(_('Add at least two options and one participating family.'))
            no_payer = voting.participant_family_ids.filtered(
                lambda family: not family.billing_partner_id
            )
            if no_payer:
                raise ValidationError(_('Every participating family must have a billing guardian.'))
            no_email = voting.participant_family_ids.filtered(
                lambda family: not family.billing_partner_id.email
            )
            if no_email:
                raise ValidationError(
                    _(
                        'Every billing guardian must have an email address '
                        'to receive the invitation.'
                    )
                )
            stale_invitations = self.env['afa.voting.invitation']
            for invitation in voting.invitation_ids:
                if (
                    invitation.family_id not in voting.participant_family_ids
                    or invitation.recipient_partner_id != invitation.family_id.billing_partner_id
                ):
                    stale_invitations |= invitation
            stale_invitations.unlink()
            new_families = voting.participant_family_ids - voting.invitation_ids.family_id
            invitations = (
                self.env['afa.voting.invitation'].create(
                    [
                        {
                            'voting_id': voting.id,
                            'family_id': family.id,
                            'recipient_partner_id': family.billing_partner_id.id,
                        }
                        for family in new_families
                    ]
                )
                | voting.invitation_ids
            )
            super(AfaVoting, voting).write({'state': 'open'})
            invitations.action_send()
        return True

    def action_close(self):
        self._check_voting_manager()
        for voting in self.filtered(lambda record: record.state == 'open'):
            super(AfaVoting, voting).write({'state': 'closed'})
        return True

    def action_cancel(self):
        self._check_voting_manager()
        if any(record.state not in ('draft', 'open') for record in self):
            raise UserError(_('Only draft or open votings can be cancelled.'))
        for voting in self:
            super(AfaVoting, voting).write({'state': 'cancelled'})
        pending = self.invitation_ids.filtered(lambda item: item.state == 'pending').sudo()
        pending._archive_current_credential()
        pending._workflow_write({'state': 'revoked', 'token_hash': False})
        return True

    def unlink(self):
        if any(record.state != 'draft' for record in self):
            raise UserError(_('Published votings cannot be deleted.'))
        return super().unlink()

    def action_send_reminders(self):
        self._check_voting_manager()
        self.ensure_one()
        self.invitation_ids.filtered(lambda item: item.state == 'pending').action_send()
        return True

    def action_export_participants(self):
        self.ensure_one()
        self._check_voting_manager()
        rows = [['Family', 'Invitation recipient', 'Invitation state', 'Voted at']]
        for invitation in self.invitation_ids:
            rows.append(
                [
                    invitation.family_id.display_name,
                    invitation.recipient_partner_id.display_name,
                    invitation.state,
                    fields.Datetime.to_string(invitation.voted_at) if invitation.voted_at else '',
                ]
            )
        return self._csv_action(rows, 'participants.csv')

    def action_export_results(self):
        self.ensure_one()
        self._check_voting_manager()
        rows = [['Option', 'Votes', 'Percentage']]
        for option in self.option_ids:
            rows.append([option.name, str(option.vote_count), f'{option.vote_percent * 100:.2f}%'])
        return self._csv_action(rows, 'results.csv')

    def _csv_action(self, rows, filename):
        import base64
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows([self._safe_csv_cell(value) for value in row] for row in rows)
        invitation = self.invitation_ids[:1]
        if not invitation:
            raise UserError(_('Publish the voting before exporting its results.'))
        attachment = self.env['ir.attachment'].create(
            {
                'name': filename,
                'type': 'binary',
                'datas': base64.b64encode(output.getvalue().encode()),
                'res_model': invitation._name,
                'res_id': invitation.id,
                'public': False,
            }
        )
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    @staticmethod
    def _safe_csv_cell(value):
        text = '' if value is None else str(value)
        if text.startswith(('=', '+', '-', '@', '\t', '\r')):
            return f"'{text}"
        return text

    @api.model
    def _cron_close_expired(self):
        expired = self.search([('state', '=', 'open'), ('date_end', '<=', fields.Datetime.now())])
        for voting in expired:
            super(AfaVoting, voting).write({'state': 'closed'})
        return len(expired)

    def _check_voting_manager(self):
        if not self.env.user.has_group('afa_voting.group_voting_manager'):
            raise AccessError(_('Only voting managers can manage votings.'))

    def action_open(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.ids)],
        }
