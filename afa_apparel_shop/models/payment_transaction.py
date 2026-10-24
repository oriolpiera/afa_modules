from odoo import models


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _set_pending(self, *, state_message=None, extra_allowed_states=()):
        pending_transactions = super()._set_pending(
            state_message=state_message,
            extra_allowed_states=extra_allowed_states,
        )
        wire_transfer_orders = pending_transactions.filtered(
            lambda transaction: (
                transaction.provider_id.code == 'custom'
                and transaction.provider_id.custom_mode == 'wire_transfer'
            )
        ).mapped('sale_order_ids')
        wire_transfer_orders.filtered(
            lambda order: order.website_id and order.state in ('draft', 'sent')
        ).sudo()._afa_reserve_web_stock()
        return pending_transactions
