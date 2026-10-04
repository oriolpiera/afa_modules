from odoo import _, fields, models
from odoo.exceptions import AccessError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    afa_membership_mode = fields.Selection(
        [('invoice', 'Paid Dues Invoice'), ('manual', 'Manual Family Flag')],
        string='AFA Membership Mode',
        required=True,
        default='invoice',
        config_parameter='afa_membership.mode',
    )

    def set_values(self):
        if not self.env.su and not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Only system administrators may change membership mode.'))
        result = super().set_values()
        self.env['afa.family'].invalidate_model(
            [
                'is_member',
                'membership_state',
                'membership_mode',
                'current_period_id',
                'current_dues_invoice_id',
            ]
        )
        return result
