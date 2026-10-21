import logging
import os
from datetime import timedelta

import psycopg2

from odoo import SUPERUSER_ID, Command, api, fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestAfaApparelStockReservation(TransactionCase):
    def setUp(self):
        super().setUp()
        self.website = self.env['website'].search(
            [('company_id', '=', self.env.company.id)], limit=1
        )
        self.warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1
        )
        self.product = self.env['product.product'].create(
            {
                'name': 'Test Jacket - Size 8',
                'type': 'consu',
                'is_storable': True,
                'allow_out_of_stock_order': False,
                'list_price': 35,
            }
        )
        self.env['stock.quant']._update_available_quantity(
            self.product,
            self.warehouse.lot_stock_id,
            1,
        )
        self.partner = self.env['res.partner'].create({'name': 'AFA Web Customer'})
        self.provider = self.env.ref('payment.payment_provider_transfer')

    def _order(self, *, website=True):
        return self.env['sale.order'].create(
            {
                'partner_id': self.partner.id,
                'website_id': self.website.id if website else False,
                'warehouse_id': self.warehouse.id,
                'order_line': [
                    (
                        0,
                        0,
                        {'product_id': self.product.id, 'product_uom_qty': 1},
                    )
                ],
            }
        )

    def _wire_transfer_transaction(self, order):
        return self.env['payment.transaction'].create(
            {
                'provider_id': self.provider.id,
                'payment_method_id': self.env.ref('payment_custom.payment_method_wire_transfer').id,
                'reference': order.name,
                'amount': order.amount_total,
                'currency_id': order.currency_id.id,
                'partner_id': order.partner_id.id,
                'operation': 'online_direct',
                'sale_order_ids': [Command.set(order.ids)],
            }
        )

    def test_wire_transfer_reserves_stock_for_seven_days(self):
        order = self._order()
        transaction = self._wire_transfer_transaction(order)
        before = fields.Datetime.now()

        transaction._set_pending()

        expected_deadline = before + timedelta(days=7)
        self.assertAlmostEqual(
            (order.afa_stock_reserved_until - expected_deadline).total_seconds(),
            0,
            delta=2,
        )
        self.assertEqual(order.state, 'draft')
        self.assertEqual(self.website._get_product_available_qty(self.product), 0)

        another_cart = self._order()
        self.assertEqual(another_cart._get_free_qty(self.product), 0)

    def test_wire_transfer_cannot_reserve_stock_already_held_by_another_order(self):
        first_order = self._order()
        self._wire_transfer_transaction(first_order)._set_pending()
        second_order = self._order()
        second_transaction = self._wire_transfer_transaction(second_order)

        with self.assertRaises(ValidationError), self.cr.savepoint():
            second_transaction._set_pending()

        self.assertFalse(second_order.afa_stock_reserved_until)
        self.assertEqual(second_transaction.state, 'draft')

    def test_expired_reservation_cancels_order_and_releases_stock(self):
        order = self._order()
        self._wire_transfer_transaction(order)._set_pending()
        order.afa_stock_reserved_until = fields.Datetime.now() - timedelta(seconds=1)

        self.env['sale.order']._cron_cancel_expired_web_stock_reservations()

        self.assertEqual(order.state, 'cancel')
        self.assertEqual(self.website._get_product_available_qty(self.product), 1)

    def test_expired_reservation_cannot_be_confirmed(self):
        order = self._order()
        self._wire_transfer_transaction(order)._set_pending()
        order.afa_stock_reserved_until = fields.Datetime.now() - timedelta(seconds=1)

        with self.assertRaisesRegex(ValidationError, 'reservation expired'):
            order.action_confirm()

    def test_confirmed_order_uses_native_stock_reservation(self):
        order = self._order()
        self._wire_transfer_transaction(order)._set_pending()

        order.action_confirm()

        self.assertEqual(order.state, 'sale')
        self.assertEqual(self.website._get_product_available_qty(self.product), 0)

    def test_backend_order_cannot_consume_stock_reserved_for_web_order(self):
        web_order = self._order()
        self._wire_transfer_transaction(web_order)._set_pending()
        backend_order = self._order(website=False)

        with self.assertRaises(ValidationError), self.cr.savepoint():
            backend_order.action_confirm()

        self.assertEqual(backend_order.state, 'draft')

    def test_backend_order_without_web_reservations_can_backorder(self):
        self.env['stock.quant']._update_available_quantity(
            self.product,
            self.warehouse.lot_stock_id,
            -1,
        )
        backend_order = self._order(website=False)

        backend_order.action_confirm()

        self.assertEqual(backend_order.state, 'sale')

    def test_reserved_order_line_cannot_be_increased_beyond_stock(self):
        self.env['stock.quant']._update_available_quantity(
            self.product,
            self.warehouse.lot_stock_id,
            1,
        )
        first_order = self._order()
        second_order = self._order()
        self._wire_transfer_transaction(first_order)._set_pending()
        self._wire_transfer_transaction(second_order)._set_pending()

        with self.assertRaises(ValidationError), self.cr.savepoint():
            first_order.order_line.product_uom_qty = 2

        self.assertEqual(first_order.order_line.product_uom_qty, 1)

    def test_concurrent_wire_transfer_orders_cannot_reserve_the_same_unit(self):
        registry = self.env.registry
        fixture = {}
        try:
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                website = env['website'].search([('company_id', '=', env.company.id)], limit=1)
                warehouse = env['stock.warehouse'].search(
                    [('company_id', '=', env.company.id)], limit=1
                )
                previous_warehouse_id = website.warehouse_id.id
                website.warehouse_id = warehouse
                product = env['product.product'].create(
                    {
                        'name': 'Concurrent Test Jacket - Size 8',
                        'type': 'consu',
                        'is_storable': True,
                        'allow_out_of_stock_order': False,
                        'list_price': 35,
                    }
                )
                env['stock.quant']._update_available_quantity(
                    product,
                    warehouse.lot_stock_id,
                    1,
                )
                partners = env['res.partner'].create(
                    [{'name': 'Concurrent Web Customer 1'}, {'name': 'Concurrent Web Customer 2'}]
                )
                orders = env['sale.order'].create(
                    [
                        {
                            'partner_id': partner.id,
                            'website_id': website.id,
                            'warehouse_id': warehouse.id,
                            'order_line': [
                                (0, 0, {'product_id': product.id, 'product_uom_qty': 1})
                            ],
                        }
                        for partner in partners
                    ]
                )
                payment_method = env.ref('payment_custom.payment_method_wire_transfer')
                provider = env.ref('payment.payment_provider_transfer')
                transactions = env['payment.transaction'].create(
                    [
                        {
                            'provider_id': provider.id,
                            'payment_method_id': payment_method.id,
                            'reference': order.name,
                            'amount': order.amount_total,
                            'currency_id': order.currency_id.id,
                            'partner_id': order.partner_id.id,
                            'operation': 'online_direct',
                            'sale_order_ids': [Command.set(order.ids)],
                        }
                        for order in orders
                    ]
                )
                fixture = {
                    'website_id': website.id,
                    'previous_warehouse_id': previous_warehouse_id,
                    'product_id': product.id,
                    'partner_ids': partners.ids,
                    'order_ids': orders.ids,
                    'transaction_ids': transactions.ids,
                }
                cr.commit()

            with registry.cursor() as first_cr, registry.cursor() as second_cr:
                first_env = api.Environment(first_cr, SUPERUSER_ID, {})
                second_env = api.Environment(second_cr, SUPERUSER_ID, {})
                first_tx, second_tx = second_env['payment.transaction'].browse(
                    fixture['transaction_ids']
                )
                first_tx = first_env['payment.transaction'].browse(first_tx.id)

                # Keep the first reservation uncommitted while the other connection attempts
                # to lock the same variant, proving that reservation creation is serialized.
                first_tx._set_pending()
                second_cr.execute("SET LOCAL lock_timeout = '250ms'")
                sql_logger = logging.getLogger('odoo.sql_db')
                previous_log_level = sql_logger.level
                sql_logger.setLevel(logging.CRITICAL)
                try:
                    with self.assertRaises(psycopg2.errors.LockNotAvailable):
                        second_tx._set_pending()
                finally:
                    sql_logger.setLevel(previous_log_level)

                second_cr.rollback()
                second_env.invalidate_all()
                first_cr.commit()

                with self.assertRaises(ValidationError), second_cr.savepoint():
                    second_env['payment.transaction'].browse(second_tx.id)._set_pending()

                self.assertTrue(
                    first_env['sale.order'].browse(fixture['order_ids'][0]).afa_stock_reserved_until
                )
                self.assertFalse(
                    second_env['sale.order']
                    .browse(fixture['order_ids'][1])
                    .afa_stock_reserved_until
                )
        finally:
            if fixture:
                with registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    env['payment.transaction'].browse(fixture['transaction_ids']).unlink()
                    orders = env['sale.order'].browse(fixture['order_ids'])
                    orders.action_cancel()
                    orders.unlink()
                    env['stock.quant'].with_context(inventory_mode=True).search(
                        [('product_id', '=', fixture['product_id'])]
                    ).unlink()
                    env['product.product'].browse(fixture['product_id']).product_tmpl_id.unlink()
                    env['res.partner'].browse(fixture['partner_ids']).unlink()
                    env['website'].browse(fixture['website_id']).warehouse_id = fixture[
                        'previous_warehouse_id'
                    ]
                    cr.commit()


class TestAfaApparelDemo(TransactionCase):
    def test_demo_apparel_variants_are_stock_tracked_and_blocked_when_empty(self):
        products = [
            self.env.ref(xmlid, raise_if_not_found=False)
            for xmlid in (
                'afa_member_pricing.demo_tracksuit',
                'afa_member_pricing.demo_short_sleeve_tshirt',
                'afa_member_pricing.demo_long_sleeve_tshirt',
            )
        ]
        if not all(products):
            if os.environ.get('AFA_EXPECT_DEMO') == '1':
                self.fail('AFA apparel demo records are required for this test run')
            self.skipTest('AFA apparel demo records were not loaded')
        for product in products:
            self.assertTrue(product.is_storable)
            self.assertFalse(product.allow_out_of_stock_order)
