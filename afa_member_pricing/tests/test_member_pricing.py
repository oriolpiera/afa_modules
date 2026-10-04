from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase

from odoo.addons.afa_member_pricing.controllers.main import AfaWebsiteSale


class TestMemberPricing(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env['res.config.settings'].create({'afa_membership_mode': 'manual'}).set_values()
        self.website = self.env['website'].search(
            [('company_id', '=', self.env.company.id)], limit=1
        )
        Pricelist = self.env['product.pricelist']
        values = {
            'currency_id': self.env.company.currency_id.id,
            'company_id': self.env.company.id,
            'website_id': self.website.id,
        }
        self.member_pl = Pricelist.create({**values, 'name': 'AFA Members', 'selectable': False})
        self.public_pl = Pricelist.create({**values, 'name': 'AFA Public', 'selectable': True})
        self.env.company.write(
            {
                'afa_member_pricelist_id': self.member_pl.id,
                'afa_nonmember_pricelist_id': self.public_pl.id,
            }
        )
        self.product = self.env['product.product'].create(
            {'name': 'Workshop', 'type': 'service', 'list_price': 100}
        )
        for pricelist, price in ((self.member_pl, 60), (self.public_pl, 100)):
            self.env['product.pricelist.item'].create(
                {
                    'pricelist_id': pricelist.id,
                    'applied_on': '0_product_variant',
                    'product_id': self.product.id,
                    'compute_price': 'fixed',
                    'fixed_price': price,
                }
            )
        self.guardian = self.env['res.partner'].create(
            {'name': 'Member Guardian', 'afa_family_role': 'guardian'}
        )
        self.family = self.env['afa.family'].create(
            {'name': 'Member Family', 'billing_partner_id': self.guardian.id, 'manual_member': True}
        )
        self.outsider = self.env['res.partner'].create({'name': 'Non-member Guardian'})

    def _order(self, partner=None, website=False):
        return self.env['sale.order'].create(
            {
                'partner_id': (partner or self.guardian).id,
                'website_id': self.website.id if website else False,
                'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 1})],
            }
        )

    def test_sale_prices_follow_customer_and_confirmed_orders_keep_price(self):
        order = self._order()
        self.assertEqual(order.afa_family_id, self.family)
        self.assertEqual(order.pricelist_id, self.member_pl)
        self.assertEqual(order.order_line.price_unit, 60)
        order.partner_id = self.outsider
        self.assertFalse(order.afa_family_id)
        self.assertEqual(order.pricelist_id, self.public_pl)
        self.assertEqual(order.order_line.price_unit, 100)
        order.partner_id = self.guardian
        self.assertEqual(order.order_line.price_unit, 60)
        order.state = 'sent'
        order.partner_id = self.outsider
        self.assertEqual(order.order_line.price_unit, 100)
        order.partner_id = self.guardian
        self.assertEqual(order.order_line.price_unit, 60)
        order.action_confirm()
        self.family.manual_member = False
        self.assertEqual(order.pricelist_id, self.member_pl)
        self.assertEqual(order.order_line.price_unit, 60)

    def test_backend_quote_cannot_confirm_after_membership_is_revoked(self):
        for state in ('draft', 'sent'):
            self.family.manual_member = True
            order = self._order()
            order.state = state
            self.family.manual_member = False
            self.assertEqual(order.pricelist_id, self.member_pl)
            with self.assertRaises(ValidationError), self.cr.savepoint():
                order.action_confirm()
            self.assertEqual(order.state, state)
            order.pricelist_id = self.public_pl
            self.assertEqual(order.order_line.price_unit, 100)
            order.action_confirm()
            self.assertEqual(order.state, 'sale')

    def test_customer_change_preserves_agreed_price_and_discount(self):
        order = self._order()
        first_line = order.order_line
        second_line = self.env['sale.order.line'].create(
            {'order_id': order.id, 'product_id': self.product.id}
        )
        first_line.price_unit = 42
        second_line.discount = 7
        self.assertFalse(first_line.afa_manual_discount)
        self.assertTrue(second_line.afa_manual_discount)
        order.partner_id = self.outsider
        self.assertEqual(first_line.price_unit, 42)
        self.assertEqual(second_line.price_unit, 100)
        self.assertEqual(second_line.discount, 7)
        self.assertTrue(second_line.afa_manual_discount)
        order.pricelist_id = self.member_pl
        self.assertEqual(first_line.price_unit, 42)
        self.assertEqual(second_line.price_unit, 60)
        self.assertEqual(second_line.discount, 7)

    def test_created_agreed_discount_survives_pricelist_change(self):
        order = self._order()
        line = self.env['sale.order.line'].create(
            {'order_id': order.id, 'product_id': self.product.id, 'discount': 13}
        )
        self.assertTrue(line.afa_manual_discount)
        order.pricelist_id = self.public_pl
        self.assertEqual(line.price_unit, 100)
        self.assertEqual(line.discount, 13)

    def test_native_discount_rule_recalculates_without_becoming_manual(self):
        self.env['res.config.settings'].create({'group_discount_per_so_line': True}).set_values()
        self.env['product.pricelist.item'].search(
            [
                ('product_id', '=', self.product.id),
                ('pricelist_id', 'in', (self.member_pl | self.public_pl).ids),
            ]
        ).unlink()
        for pricelist, discount in ((self.member_pl, 10), (self.public_pl, 20)):
            self.env['product.pricelist.item'].create(
                {
                    'pricelist_id': pricelist.id,
                    'applied_on': '0_product_variant',
                    'product_id': self.product.id,
                    'compute_price': 'percentage',
                    'percent_price': discount,
                }
            )
        order = self._order()
        line = order.order_line
        self.assertEqual(line.discount, 10)
        self.assertFalse(line.afa_manual_discount)
        line.product_uom_qty = 2
        self.assertEqual(line.discount, 10)
        self.assertFalse(line.afa_manual_discount)
        order.partner_id = self.outsider
        self.assertEqual(line.discount, 20)
        self.assertFalse(line.afa_manual_discount)

    def test_public_and_recovered_carts_lose_stale_member_price(self):
        order = self._order(website=True)
        self.assertEqual(order.order_line.price_unit, 60)
        self.family.manual_member = False
        self.assertEqual(order.pricelist_id, self.member_pl)
        self.assertTrue(order._afa_revalidate_cart())
        self.assertEqual(order.pricelist_id, self.public_pl)
        self.assertEqual(order.order_line.price_unit, 100)
        self.assertFalse(order._afa_revalidate_cart())

    def test_cart_recovery_recomputes_prices_once(self):
        order = self._order(website=True)
        self.family.manual_member = False
        order_model = type(order)
        original = order_model._recompute_prices
        with patch.object(
            order_model, '_recompute_prices', autospec=True, side_effect=original
        ) as recompute:
            self.assertTrue(order._afa_revalidate_cart())
        self.assertEqual(recompute.call_count, 1)
        self.assertEqual(order.order_line.price_unit, 100)

    def test_payment_gate_rejects_stale_member_cart_without_writing(self):
        order = self._order(website=True)
        self.family.manual_member = False
        with self.assertRaisesRegex(ValidationError, 'eligibility'):
            order._check_cart_is_ready_to_be_paid()
        self.assertEqual(order.pricelist_id, self.member_pl)
        self.assertEqual(order.order_line.price_unit, 60)
        order._afa_revalidate_cart()
        order._check_cart_is_ready_to_be_paid()

    def test_public_request_cannot_claim_member_pricelist(self):
        order = self._order(website=True)
        visitor = SimpleNamespace(
            env=SimpleNamespace(user=SimpleNamespace(_is_public=lambda: True))
        )
        with patch('odoo.addons.afa_member_pricing.models.sale_order.request', visitor):
            self.assertEqual(
                self.env.company._afa_pricelist_for_partner(self.guardian, public=True),
                self.public_pl,
            )
            order.pricelist_id = self.member_pl
            with self.assertRaises(ValidationError):
                order._check_cart_is_ready_to_be_paid()

    def test_website_pricelist_is_private_even_if_selected(self):
        visitor = SimpleNamespace(
            session={'website_sale_current_pl': self.member_pl.id},
            env=SimpleNamespace(
                user=SimpleNamespace(
                    id=self.website.user_id.id,
                    _is_public=lambda: True,
                    partner_id=self.website.user_id.partner_id,
                )
            ),
        )
        with patch('odoo.addons.afa_member_pricing.models.website.request', visitor):
            self.assertEqual(self.website._get_and_cache_current_pricelist(), self.public_pl)
            self.assertEqual(visitor.session['website_sale_current_pl'], self.public_pl.id)
            self.assertFalse(self.website.is_pricelist_available(self.member_pl.id))

    def test_browsing_keeps_session_price_until_cart_recovery(self):
        visitor = SimpleNamespace(
            session={
                'website_sale_current_pl': self.member_pl.id,
                'afa_pricing_user_id': self.env.user.id,
            }
        )
        self.family.manual_member = False
        with patch('odoo.addons.afa_member_pricing.models.website.request', visitor):
            self.assertEqual(self.website._get_and_cache_current_pricelist(), self.member_pl)
        visitor.session['afa_pricing_user_id'] = self.website.user_id.id
        with patch('odoo.addons.afa_member_pricing.models.website.request', visitor):
            self.assertEqual(
                self.website.with_user(self.website.user_id)._get_and_cache_current_pricelist(),
                self.public_pl,
            )

    def test_cart_recovery_updates_price_and_session(self):
        order = self._order(website=True)
        self.family.manual_member = False
        visitor = SimpleNamespace(
            session={},
            env=SimpleNamespace(
                cr=self.env.cr,
                user=SimpleNamespace(_is_public=lambda: False, partner_id=self.guardian),
            ),
            httprequest=SimpleNamespace(path='/shop/cart'),
        )
        with (
            patch('odoo.addons.afa_member_pricing.models.website.request', visitor),
            patch('odoo.addons.afa_member_pricing.models.sale_order.request', visitor),
            patch(
                'odoo.addons.website_sale.models.website.Website._get_and_cache_current_cart',
                return_value=order,
            ),
        ):
            self.assertEqual(self.website._get_and_cache_current_cart(), order)
        self.assertEqual(order.pricelist_id, self.public_pl)
        self.assertEqual(order.order_line.price_unit, 100)
        self.assertEqual(visitor.session['website_sale_current_pl'], self.public_pl.id)

    def test_public_selection_and_promo_cannot_apply_member_pricelist(self):
        visitor = SimpleNamespace(website=self.website)
        with patch('odoo.addons.afa_member_pricing.controllers.main.request', visitor):
            self.assertFalse(AfaWebsiteSale()._apply_selectable_pricelist(self.member_pl.id))
            self.assertIsNone(AfaWebsiteSale()._apply_pricelist(self.member_pl))

    def test_portal_user_can_resolve_family_without_manager_access(self):
        portal = self.env['res.users'].create(
            {
                'name': 'AFA Portal Guardian',
                'login': 'afa-pricing-portal',
                'partner_id': self.guardian.id,
                'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
            }
        )
        self.assertFalse(self.family.with_user(portal).has_access('read'))
        self.assertEqual(
            self.env.company.with_user(portal).sudo()._afa_pricelist_for_partner(self.guardian),
            self.member_pl,
        )
        with self.assertRaises(AccessError):
            self._order().with_user(portal).read(['afa_family_id'])

    def test_member_pricelist_cannot_be_public_or_have_promo_code(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env.company.write({'afa_member_pricelist_id': self.public_pl.id})
        self.member_pl.selectable = True
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env.company._check_afa_pricelists()
        self.member_pl.selectable = False
        self.member_pl.code = 'AFA_MEMBER'
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env.company._check_afa_pricelists()

    def test_variant_and_category_rules_use_native_pricing(self):
        category = self.env['product.category'].create({'name': 'AFA Clothes'})
        color = self.env['product.attribute'].create({'name': 'AFA Color'})
        red = self.env['product.attribute.value'].create({'name': 'Red', 'attribute_id': color.id})
        blue = self.env['product.attribute.value'].create(
            {'name': 'Blue', 'attribute_id': color.id}
        )
        shirt = self.env['product.template'].create(
            {
                'name': 'AFA Shirt',
                'categ_id': category.id,
                'list_price': 90,
                'attribute_line_ids': [
                    (0, 0, {'attribute_id': color.id, 'value_ids': [(6, 0, [red.id, blue.id])]})
                ],
            }
        )
        variants = shirt.product_variant_ids.sorted('id')
        self.assertEqual(len(variants), 2)
        for pricelist, values in (
            (
                self.member_pl,
                {
                    'applied_on': '0_product_variant',
                    'product_id': variants[0].id,
                    'fixed_price': 45,
                },
            ),
            (
                self.public_pl,
                {'applied_on': '2_product_category', 'categ_id': category.id, 'fixed_price': 90},
            ),
        ):
            self.env['product.pricelist.item'].create(
                {'pricelist_id': pricelist.id, 'compute_price': 'fixed', **values}
            )
        member_order = self._order()
        public_order = self._order(self.outsider)
        for order, product in ((member_order, variants[0]), (public_order, variants[0])):
            self.env['sale.order.line'].create({'order_id': order.id, 'product_id': product.id})
        self.assertEqual(
            member_order.order_line.filtered(lambda l: l.product_id == variants[0]).price_unit, 45
        )
        self.assertEqual(
            public_order.order_line.filtered(lambda l: l.product_id == variants[0]).price_unit, 90
        )
        self.assertEqual(self.member_pl._get_product_price(variants[0], 1), 45)
        self.assertEqual(self.public_pl._get_product_price(variants[0], 1), 90)
