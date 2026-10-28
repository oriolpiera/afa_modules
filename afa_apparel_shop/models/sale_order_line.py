from odoo import api, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.mapped('order_id')._afa_check_active_web_stock_reservations()
        return lines

    def write(self, vals):
        stock_fields = {'order_id', 'product_id', 'product_uom_id', 'product_uom_qty'}
        if not stock_fields.intersection(vals):
            return super().write(vals)

        previous_orders = self.mapped('order_id')
        result = super().write(vals)
        (previous_orders | self.mapped('order_id'))._afa_check_active_web_stock_reservations()
        return result
