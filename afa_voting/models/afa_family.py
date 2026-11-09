from odoo import Command, _, models
from odoo.exceptions import AccessError, ValidationError


class AfaFamily(models.Model):
    _inherit = 'afa.family'

    def action_add_to_voting(self):
        if not self.env.user.has_group('afa_voting.group_voting_manager'):
            raise AccessError(_('Only voting managers can add families to a voting.'))
        wizard = self.env['afa.voting.add.families.wizard'].create(
            {'family_ids': [Command.set(self.ids)]}
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Add families to a voting'),
            'res_model': 'afa.voting.add.families.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('afa_voting.view_add_families_wizard_form').id,
            'res_id': wizard.id,
            'target': 'new',
        }

    def write(self, vals):
        previous = (
            {family.id: family.billing_partner_id.id for family in self}
            if 'billing_partner_id' in vals
            else {}
        )
        result = super().write(vals)
        if previous:
            invitations = (
                self.env['afa.voting.invitation']
                .sudo()
                .search(
                    [
                        ('family_id', 'in', self.ids),
                        ('voting_id.state', '=', 'open'),
                        ('state', '=', 'pending'),
                    ]
                )
            )
            for invitation in invitations:
                family = invitation.family_id
                if previous.get(family.id) == family.billing_partner_id.id:
                    continue
                if not family.billing_partner_id.email:
                    raise ValidationError(
                        _('The new billing guardian needs an email address for voting invitations.')
                    )
                invitation._archive_current_credential()
                invitation._workflow_write(
                    {
                        'recipient_partner_id': family.billing_partner_id.id,
                        'token_hash': False,
                    }
                )
                invitation.sudo().action_send()
        return result
