from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools.mail import email_split


@tagged('post_install', '-at_install')
class TestAfaPaidOrderEmail(TransactionCase):
    """Paid webshop orders must reach the internal inbox once, and only paid ones."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env['website'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1
        )
        cash_account = cls.env['account.account'].search(
            [('account_type', '=', 'asset_cash')], limit=1
        )
        cls.cash_journal = cls.env['account.journal'].create(
            {
                'name': 'Apparel Test Cash',
                'code': 'AFAP',
                'type': 'cash',
                'default_account_id': cash_account.id,
            }
        )
        cls.product = cls.env['product.product'].create(
            {
                'name': 'AFA Paid Notice Jacket',
                'is_storable': True,
                'list_price': 30,
            }
        )
        cls.partner = cls.env['res.partner'].create(
            {
                'name': 'AFA Paid Notice Guardian',
                'email': 'paid-notice@example.invalid',
            }
        )
        cls.env['stock.quant']._update_available_quantity(
            cls.product, cls.warehouse.lot_stock_id, 20
        )
        cls.company = cls.env.company
        cls.company.afa_paid_order_email = 'botiga@example.invalid'

    def _order(self, *, website=True):
        return self.env['sale.order'].create(
            {
                'partner_id': self.partner.id,
                'website_id': self.website.id if website else False,
                'warehouse_id': self.warehouse.id,
                'order_line': [
                    Command.create(
                        {
                            'product_id': self.product.id,
                            'product_uom_qty': 1,
                            'price_unit': 30,
                        }
                    )
                ],
            }
        )

    def _confirm_and_invoice(self, *, website=True):
        order = self._order(website=website)
        order.action_confirm()
        invoice = order._create_invoices()
        # Webshop pricelists are in EUR while demo databases keep every other
        # currency archived, which would block posting the invoice.
        invoice.currency_id.active = True
        invoice.action_post()
        return order, invoice

    def _pay(self, invoice, amount):
        (
            self.env['account.payment.register']
            .with_context(active_model='account.move', active_ids=invoice.ids)
            .create({'journal_id': self.cash_journal.id, 'amount': amount})
            .action_create_payments()
        )

    def _notices(self):
        return self.env['mail.mail'].sudo().search([('subject', 'like', 'Comanda pagada')])

    def test_paid_order_notifies_internal_address_once(self):
        order, invoice = self._confirm_and_invoice()

        self.env['sale.order']._cron_send_paid_order_notifications()
        self.assertFalse(self._notices())
        self.assertFalse(order.afa_paid_order_email_sent)

        self._pay(invoice, invoice.amount_residual)
        self.assertEqual(invoice.payment_state, 'paid')

        notified = self.env['sale.order']._cron_send_paid_order_notifications()
        self.assertEqual(notified, order)
        self.assertTrue(order.afa_paid_order_email_sent)

        notice = self._notices()
        self.assertEqual(len(notice), 1)
        self.assertEqual(notice.email_to, 'botiga@example.invalid')
        self.assertIn(order.name, notice.subject)
        self.assertIn(self.product.display_name, notice.body_html)
        # Inline {{ }} expressions must render, not reach the inbox as literal text.
        self.assertNotIn('{{', notice.body_html)
        self.assertIn(order.name, notice.body_html)
        self.assertIn(self.partner.name, notice.body_html)
        self.assertIn(f'id={order.id}', notice.body_html)

        # A second sweep must not notify the same order again.
        self.env['sale.order']._cron_send_paid_order_notifications()
        self.assertEqual(len(self._notices()), 1)

    def test_unpaid_orders_do_not_crowd_paid_ones_out_of_the_batch(self):
        # The oldest orders stay unpaid on purpose: a newer paid order must still
        # be notified even when the batch limit is smaller than that backlog.
        for _ in range(3):
            blocking = self._order()
            blocking.action_confirm()
        order, invoice = self._confirm_and_invoice()
        self._pay(invoice, invoice.amount_residual)
        self.assertTrue(order.afa_is_paid)

        self.env['sale.order']._cron_send_paid_order_notifications(limit=1)
        self.assertTrue(order.afa_paid_order_email_sent)
        self.assertEqual(len(self._notices()), 1)

    def test_partial_payment_does_not_notify(self):
        order, invoice = self._confirm_and_invoice()
        self._pay(invoice, invoice.amount_residual / 2)
        self.assertNotEqual(invoice.payment_state, 'paid')

        self.env['sale.order']._cron_send_paid_order_notifications()
        self.assertFalse(self._notices())
        self.assertFalse(order.afa_paid_order_email_sent)

    def test_without_configured_address_nothing_is_sent(self):
        self.company.afa_paid_order_email = False
        order, invoice = self._confirm_and_invoice()
        self._pay(invoice, invoice.amount_residual)

        self.env['sale.order']._cron_send_paid_order_notifications()
        self.assertFalse(self._notices())
        self.assertFalse(order.afa_paid_order_email_sent)

    def test_backend_orders_are_not_notified(self):
        order, invoice = self._confirm_and_invoice(website=False)
        self._pay(invoice, invoice.amount_residual)
        self.assertEqual(invoice.payment_state, 'paid')

        self.env['sale.order']._cron_send_paid_order_notifications()
        self.assertFalse(self._notices())
        self.assertFalse(order.afa_paid_order_email_sent)

    def test_multiple_internal_addresses_are_accepted(self):
        self.company.afa_paid_order_email = (
            'botiga@example.invalid, Entrega <entrega@example.invalid>'
        )
        order, invoice = self._confirm_and_invoice()
        self._pay(invoice, invoice.amount_residual)

        self.env['sale.order']._cron_send_paid_order_notifications()
        notice = self._notices()
        self.assertEqual(len(notice), 1)
        self.assertTrue(order.afa_paid_order_email_sent)
        self.assertEqual(
            sorted(email_split(notice.email_to)),
            ['botiga@example.invalid', 'entrega@example.invalid'],
        )

    def test_setting_writes_the_company_address(self):
        settings = self.env['res.config.settings'].create(
            {'afa_paid_order_email': 'entrega@example.invalid'}
        )
        settings.execute()
        self.assertEqual(self.company.afa_paid_order_email, 'entrega@example.invalid')

    def test_invalid_address_is_rejected(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.company.afa_paid_order_email = 'not-an-email'
