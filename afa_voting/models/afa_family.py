from odoo import _, models
from odoo.exceptions import ValidationError


class AfaFamily(models.Model):
    _inherit = 'afa.family'

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
