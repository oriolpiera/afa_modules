from odoo import _, models
from odoo.exceptions import AccessError


class AfaFamily(models.Model):
    _inherit = 'afa.family'

    def action_open_afa_sepa_lines(self):
        self.ensure_one()
        if not self.env.user.has_group('afa_family.group_family_manager') or not (
            self.env.user.has_group('account_payment_order.group_account_payment')
        ):
            raise AccessError(_('AFA collections require family and payment-order access.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('AFA Debit Lines'),
            'res_model': 'account.payment.line',
            'view_mode': 'list,form',
            'domain': [('afa_family_id', '=', self.id)],
            'context': {'list_view_ref': 'afa_sepa.view_afa_sepa_line_list'},
        }
