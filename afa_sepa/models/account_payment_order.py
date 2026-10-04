from odoo import _, models
from odoo.exceptions import UserError


class AccountPaymentOrder(models.Model):
    _inherit = 'account.payment.order'

    def write(self, vals):
        if vals.get('state') == 'cancel' and any(
            order.state == 'uploaded'
            and order.payment_line_ids.filtered(
                lambda line: line.afa_family_id and not line.afa_returned
            )
            for order in self
        ):
            raise UserError(_('Record each returned AFA debit before canceling an uploaded order.'))
        return super().write(vals)

    def _check_afa_lines(self):
        for order in self:
            lines = order.payment_line_ids.filtered('afa_family_id')
            if lines and order.payment_mode_id.group_lines:
                raise UserError(_('Disable payment-line grouping for AFA debit orders.'))
            lines._check_afa_collection()

    def draft2open(self):
        self._check_afa_lines()
        return super().draft2open()

    def open2generated(self):
        self._check_afa_lines()
        return super().open2generated()

    def action_cancel(self):
        if any(
            order.state == 'uploaded'
            and order.payment_line_ids.filtered(
                lambda line: line.afa_family_id and not line.afa_returned
            )
            for order in self
        ):
            raise UserError(_('Record each returned AFA debit before canceling an uploaded order.'))
        return super().action_cancel()
