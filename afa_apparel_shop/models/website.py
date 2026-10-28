from odoo import models


class Website(models.Model):
    _inherit = 'website'

    def _get_product_available_qty(self, product, **kwargs):
        available_qty = super()._get_product_available_qty(product, **kwargs)
        if not product.is_storable or product.allow_out_of_stock_order:
            return available_qty
        reserved_qty = self.env['sale.order']._afa_web_reserved_quantity(
            product,
            warehouse_id=self.warehouse_id.id,
        )
        return max(available_qty - reserved_qty, 0)
