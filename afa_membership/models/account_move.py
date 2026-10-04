from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    afa_membership_id = fields.Many2one(
        'afa.membership',
        string='AFA Dues Link',
        ondelete='restrict',
        index=True,
        copy=False,
        groups='afa_family.group_family_manager',
    )

    def init(self):
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS account_move_afa_membership_uniq '
            'ON account_move (afa_membership_id) WHERE afa_membership_id IS NOT NULL'
        )

    @api.model_create_multi
    def create(self, vals_list):
        if (
            any(vals.get('afa_membership_id') for vals in vals_list)
            and not self.env.su
            and not self.env.user.has_group('afa_family.group_family_manager')
        ):
            raise AccessError(_('Only family managers can issue AFA dues invoices.'))
        return super().create(vals_list)

    def write(self, vals):
        if 'afa_membership_id' in vals and self.filtered('afa_membership_id'):
            raise ValidationError(_('An issued dues invoice cannot change its family-period link.'))
        if 'partner_id' in vals and self.filtered(
            lambda move: move.afa_membership_id and move.state == 'posted'
        ):
            raise ValidationError(_('An issued dues invoice cannot change its billing guardian.'))
        return super().write(vals)
