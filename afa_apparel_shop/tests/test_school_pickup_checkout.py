import re

from odoo import Command
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.website_sale.tests.common import MockRequest


@tagged('post_install', '-at_install')
class TestAfaSchoolPickupCheckout(TransactionCase):
    """The checkout must offer school pickup before asking for any address."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env['website'].search([], limit=1)
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1
        )
        cls.product = cls.env['product.product'].create(
            {
                'name': 'AFA Test Tracksuit Jacket',
                'is_storable': True,
                'list_price': 35,
                'website_published': True,
            }
        )
        cls.env['stock.quant']._update_available_quantity(
            cls.product, cls.warehouse.lot_stock_id, 10
        )
        cls.guardian = cls.env['res.partner'].create(
            {
                'name': 'AFA Pickup Guardian',
                'email': 'pickup.checkout@example.invalid',
            }
        )  # Families collecting at school have no address on file.
        cls.delivery_product = cls.env['product.product'].create(
            {
                'name': 'AFA School Pickup Shipping',
                'type': 'service',
                'sale_ok': False,
                'categ_id': cls.env.ref('delivery.product_category_deliveries').id,
            }
        )
        cls.pickup_carrier = cls.env['delivery.carrier'].create(
            {
                'name': "Recollida a l'escola",
                'delivery_type': 'fixed',
                'fixed_price': 0,
                'product_id': cls.delivery_product.id,
                'afa_school_pickup': True,
                'website_published': True,
            }
        )
        cls.home_carrier = cls.env['delivery.carrier'].create(
            {
                'name': 'Lliurament a domicili',
                'delivery_type': 'fixed',
                'fixed_price': 5,
                'product_id': cls.delivery_product.id,
                'website_published': True,
            }
        )
        cls.controller = WebsiteSale()

    def _cart(self):
        return self.env['sale.order'].create(
            {
                'partner_id': self.guardian.id,
                'website_id': self.website.id,
                'order_line': [
                    Command.create({'product_id': self.product.id, 'product_uom_qty': 1})
                ],
            }
        )

    def test_pickup_carrier_matches_partner_without_address(self):
        self.assertTrue(self.pickup_carrier._match_address(self.guardian))

    def test_school_pickup_is_offered_without_a_delivery_address(self):
        cart = self._cart()
        self.assertIn(self.pickup_carrier, cart._get_delivery_methods())
        self.assertTrue(cart._afa_uses_school_pickup())

    def test_pickup_checkout_does_not_require_an_address(self):
        cart = self._cart()
        cart.carrier_id = self.pickup_carrier
        self.assertFalse(cart._needs_customer_address())
        website = self.website.with_env(self.env)
        with MockRequest(website.env, website=website, sale_order_id=cart.id) as request:
            request.cart = cart
            self.assertIsNone(self.controller._check_addresses(cart))

    def test_checkout_shows_delivery_choice_before_the_address_form(self):
        # Before the customer picks a delivery method, a school pickup option
        # must be reachable instead of being hidden behind the address form.
        cart = self._cart()
        website = self.website.with_env(self.env)
        with MockRequest(website.env, website=website, sale_order_id=cart.id) as request:
            request.cart = cart
            self.assertTrue(cart._afa_uses_school_pickup())
            self.assertIsNone(self.controller._check_addresses(cart))

    def test_home_delivery_still_requires_a_delivery_address(self):
        cart = self._cart()
        cart.carrier_id = self.home_carrier
        self.assertTrue(cart._needs_customer_address())
        website = self.website.with_env(self.env)
        with MockRequest(website.env, website=website, sale_order_id=cart.id) as request:
            request.cart = cart
            redirection = self.controller._check_addresses(cart)
        self.assertIsNotNone(redirection)
        self.assertIn('address_type=delivery', redirection.location)

    def _render_checkout(self, cart):
        website = self.website.with_env(self.env)
        with MockRequest(
            website.env, website=website, sale_order_id=cart.id, url_root='http://localhost/'
        ) as request:
            request.cart = cart
            values = self.controller._prepare_checkout_page_values(cart)
            values['delivery_methods'] = cart._get_delivery_methods()
            values.update(website._get_checkout_step_values())
            return request.env['ir.ui.view']._render_template('website_sale.checkout', values)

    def test_checkout_page_hides_address_for_pickup(self):
        cart = self._cart()
        cart.carrier_id = self.pickup_carrier
        html = self._render_checkout(cart)
        block = re.search(r'<div id="delivery_address_list" class="([^"]*)">', html)
        self.assertIsNotNone(block)
        self.assertIn('d-none', block.group(1).split())
        self.assertIn('data-afa-school-pickup="true"', html)

    def test_checkout_page_keeps_address_for_home_delivery(self):
        cart = self._cart()
        cart.carrier_id = self.home_carrier
        html = self._render_checkout(cart)
        block = re.search(r'<div id="delivery_address_list" class="([^"]*)">', html)
        self.assertIsNotNone(block)
        self.assertNotIn('d-none', block.group(1).split())
        self.assertIn('data-afa-school-pickup="false"', html)
