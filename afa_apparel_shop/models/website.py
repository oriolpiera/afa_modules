from odoo import models


class Website(models.Model):
    _inherit = 'website'

    def is_promotions_enabled(self):
        """Whether the website may advertise promo codes to customers.

        The "Discounts, Loyalty & Gift Card" switch in the website settings
        installs or uninstalls the ``loyalty`` module chain. When it is off,
        no promo code, gift card or loyalty program can be applied, so the
        cart must not render the coupon input field.
        """
        self.ensure_one()
        loyalty_module = (
            self.env['ir.module.module'].sudo().search([('name', '=', 'loyalty')], limit=1)
        )
        return loyalty_module.state == 'installed'

    def _get_product_available_qty(self, product, **kwargs):
        available_qty = super()._get_product_available_qty(product, **kwargs)
        if not product.is_storable or product.allow_out_of_stock_order:
            return available_qty
        reserved_qty = self.env['sale.order']._afa_web_reserved_quantity(
            product,
            warehouse_id=self.warehouse_id.id,
        )
        return max(available_qty - reserved_qty, 0)
