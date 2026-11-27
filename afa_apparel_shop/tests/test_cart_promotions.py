from unittest.mock import patch

from odoo import Command
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.website_sale.tests.common import MockRequest


@tagged('post_install', '-at_install')
class TestAfaCartPromotionsVisibility(TransactionCase):
    """The cart must only show the coupon field while the "Discounts, Loyalty
    & Gift Card" website setting (the `loyalty` module chain) is enabled."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env['website'].search([], limit=1)
        cls.product = cls.env['product.product'].create(
            {
                'name': 'AFA Test Tracksuit Pants',
                'is_storable': True,
                'list_price': 25,
                'website_published': True,
            }
        )
        cls.partner = cls.env['res.partner'].create(
            {
                'name': 'AFA Cart Customer',
                'email': 'cart.promotions@example.invalid',
            }
        )

    def _cart(self):
        return self.env['sale.order'].create(
            {
                'partner_id': self.partner.id,
                'website_id': self.website.id,
                'order_line': [
                    Command.create({'product_id': self.product.id, 'product_uom_qty': 1})
                ],
            }
        )

    def _render_cart_total(self, cart):
        website = self.website.with_env(self.env)
        with MockRequest(
            website.env, website=website, sale_order_id=cart.id, url_root='http://localhost/'
        ) as request:
            return request.env['ir.ui.view']._render_template(
                'website_sale.total',
                {'website_sale_order': cart, 'website': website},
            )

    def test_is_promotions_enabled_follows_loyalty_module(self):
        loyalty = self.env['ir.module.module'].sudo().search([('name', '=', 'loyalty')], limit=1)
        self.assertEqual(
            self.website.is_promotions_enabled(),
            loyalty.state == 'installed',
        )

    def test_cart_hides_coupon_field_when_promotions_disabled(self):
        cart = self._cart()
        with patch.object(type(cart.website_id), 'is_promotions_enabled', return_value=False):
            html = self._render_cart_total(cart)
        self.assertNotIn('name="promo"', html)
        self.assertIn('Total', html)

    def test_cart_shows_coupon_field_when_promotions_enabled(self):
        cart = self._cart()
        with patch.object(type(cart.website_id), 'is_promotions_enabled', return_value=True):
            html = self._render_cart_total(cart)
        self.assertIn('name="promo"', html)
