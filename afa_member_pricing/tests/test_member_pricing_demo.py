import os

from odoo.tests.common import HttpCase, TransactionCase


class TestMemberPricingDemo(TransactionCase):
    def test_demo_apparel_variants_and_prices(self):
        tracksuit = self.env.ref('afa_member_pricing.demo_tracksuit', raise_if_not_found=False)
        if not tracksuit:
            if os.environ.get('AFA_EXPECT_DEMO') == '1':
                self.fail('AFA pricing demo records are required for this test run')
            self.skipTest('AFA pricing demo records were not loaded')

        shirt = self.env.ref('afa_member_pricing.demo_short_sleeve_tshirt')
        member = self.env.ref('afa_member_pricing.demo_member_pricelist')
        nonmember = self.env.ref('afa_member_pricing.demo_nonmember_pricelist')
        self.assertEqual(self.env.company.afa_member_pricelist_id, member)
        self.assertEqual(self.env.company.afa_nonmember_pricelist_id, nonmember)
        self.assertEqual((member.currency_id.name, nonmember.currency_id.name), ('EUR', 'EUR'))
        self.assertFalse(member.selectable or member.code)
        self.assertEqual(member.website_id, nonmember.website_id)

        guardian = self.env.ref('afa_family.demo_cedar_payer')
        outsider = self.env.ref('afa_family.demo_maple_payer')
        self.env['res.config.settings'].create({'afa_membership_mode': 'manual'}).set_values()
        self.env.ref('afa_family.demo_family_cedar').manual_member = True

        for product, member_price, nonmember_price in (
            (tracksuit, 25, 35),
            (shirt, 12, 15),
        ):
            self.assertTrue(product.is_published)
            variants = product.product_variant_ids
            self.assertEqual(len(variants), 3)
            sizes = {
                value.name
                for variant in variants
                for value in variant.product_template_attribute_value_ids.product_attribute_value_id
            }
            self.assertEqual(
                sizes,
                {'S', 'M', 'L'},
            )
            for partner, pricelist, expected in (
                (guardian, member, member_price),
                (outsider, nonmember, nonmember_price),
            ):
                order = self.env['sale.order'].create(
                    {
                        'partner_id': partner.id,
                        'website_id': member.website_id.id,
                        'order_line': [(0, 0, {'product_id': variant.id}) for variant in variants],
                    }
                )
                self.assertEqual(order.pricelist_id, pricelist)
                self.assertEqual(order.currency_id.name, 'EUR')
                self.assertEqual(set(order.order_line.mapped('price_unit')), {expected})
                for variant in variants:
                    self.assertEqual(pricelist._get_product_price(variant, 1), expected)


class TestMemberPricingWebsite(HttpCase):
    def test_public_product_page_uses_nonmember_price(self):
        tracksuit = self.env.ref('afa_member_pricing.demo_tracksuit', raise_if_not_found=False)
        if not tracksuit:
            if os.environ.get('AFA_EXPECT_DEMO') == '1':
                self.fail('AFA pricing demo records are required for this test run')
            self.skipTest('AFA pricing demo records were not loaded')

        page = self.url_open(tracksuit._get_product_url())
        self.assertEqual(page.status_code, 200)
        self.assertIn('Xandall', page.text)
        self.assertIn('35.00', page.text)

    def test_identified_member_product_page_uses_member_price(self):
        tracksuit = self.env.ref('afa_member_pricing.demo_tracksuit', raise_if_not_found=False)
        if not tracksuit:
            if os.environ.get('AFA_EXPECT_DEMO') == '1':
                self.fail('AFA pricing demo records are required for this test run')
            self.skipTest('AFA pricing demo records were not loaded')

        self.env['res.config.settings'].create({'afa_membership_mode': 'manual'}).set_values()
        self.env.ref('afa_family.demo_family_cedar').manual_member = True
        login = 'afa-pricing-website-guardian'
        password = 'test-website-guardian'
        self.env['res.users'].create(
            {
                'name': 'AFA Demo Guardian',
                'login': login,
                'password': password,
                'partner_id': self.env.ref('afa_family.demo_cedar_payer').id,
                'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
            }
        )
        self.authenticate(login, password)
        page = self.url_open(tracksuit._get_product_url())
        self.assertEqual(page.status_code, 200)
        self.assertIn('Xandall', page.text)
        self.assertIn('25.00', page.text)
