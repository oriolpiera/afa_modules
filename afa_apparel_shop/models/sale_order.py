from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    afa_stock_reserved_until = fields.Datetime(
        string='Web Stock Reserved Until',
        copy=False,
        readonly=True,
        index=True,
        groups='sales_team.group_sale_salesman',
    )

    @api.model
    def _afa_web_reserved_quantity(self, product, warehouse_id=False, exclude_order_ids=()):
        domain = [
            ('product_id', '=', product.id),
            ('order_id.website_id', '!=', False),
            ('order_id.state', 'in', ('draft', 'sent')),
            ('order_id.afa_stock_reserved_until', '>', fields.Datetime.now()),
        ]
        if warehouse_id:
            domain.append(('order_id.warehouse_id', '=', warehouse_id))
        if exclude_order_ids:
            domain.append(('order_id', 'not in', list(exclude_order_ids)))

        reserved_lines = self.env['sale.order.line'].sudo().search(domain)
        return sum(
            line.product_uom_id._compute_quantity(
                line.product_uom_qty,
                product.uom_id,
                round=False,
            )
            for line in reserved_lines
        )

    def _afa_has_active_web_stock_reservation(self):
        self.ensure_one()
        order = self.sudo()
        return bool(
            order.website_id
            and order.state in ('draft', 'sent')
            and order.afa_stock_reserved_until
            and order.afa_stock_reserved_until > fields.Datetime.now()
        )

    def _afa_check_active_web_stock_reservations(self):
        active_orders = self.filtered(lambda order: order._afa_has_active_web_stock_reservation())
        active_orders.sudo()._afa_check_web_reserved_stock()

    def write(self, vals):
        active_orders = self.filtered(lambda order: order._afa_has_active_web_stock_reservation())
        if active_orders and {'company_id', 'website_id'} & vals.keys():
            raise ValidationError(
                _('The company and website cannot change while web stock is reserved.')
            )

        result = super().write(vals)
        if 'warehouse_id' in vals:
            self._afa_check_active_web_stock_reservations()
        return result

    def _get_free_qty(self, product):
        free_qty = super()._get_free_qty(product)
        if not product.is_storable or product.allow_out_of_stock_order:
            return free_qty
        warehouse_id = self._get_shop_warehouse_id()
        reserved_qty = self.env['sale.order']._afa_web_reserved_quantity(
            product,
            warehouse_id=warehouse_id,
            exclude_order_ids=self.ids,
        )
        return max(free_qty - reserved_qty, 0)

    def _afa_lock_stock_products(self, products):
        products = products.sorted('id')
        if not products:
            return
        self.env.cr.execute(
            'SELECT id FROM product_product WHERE id = ANY(%s) ORDER BY id FOR UPDATE',
            [products.ids],
        )
        products.invalidate_recordset(['free_qty'])

    def _afa_check_web_reserved_stock(self):
        requirements = defaultdict(float)
        products_by_key = {}
        for order in self:
            warehouse_id = order.warehouse_id.id
            for line in order.order_line.filtered(
                lambda order_line: (
                    order_line.product_id.is_storable
                    and not order_line.product_id.allow_out_of_stock_order
                    and order_line.product_uom_qty > 0
                )
            ):
                product = line.product_id
                key = (order.company_id.id, warehouse_id, product.id)
                requirements[key] += line.product_uom_id._compute_quantity(
                    line.product_uom_qty,
                    product.uom_id,
                    round=False,
                )
                products_by_key[key] = product

        self._afa_lock_stock_products(
            self.env['product.product'].browse([product.id for product in products_by_key.values()])
        )

        for (company_id, warehouse_id, product_id), required_qty in requirements.items():
            product = products_by_key[(company_id, warehouse_id, product_id)]
            company = self.env['res.company'].browse(company_id)
            free_qty = (
                product.with_company(company).with_context(warehouse_id=warehouse_id).free_qty
            )
            reserved_qty = self.env['sale.order']._afa_web_reserved_quantity(
                product,
                warehouse_id=warehouse_id,
                exclude_order_ids=self.ids,
            )
            available_qty = free_qty - reserved_qty
            if (
                float_compare(
                    available_qty,
                    required_qty,
                    precision_rounding=product.uom_id.rounding,
                )
                < 0
            ):
                raise ValidationError(
                    _(
                        'There is not enough available stock for %(product)s. '
                        'Available: %(available)s; requested: %(requested)s.',
                        product=product.display_name,
                        available=max(available_qty, 0),
                        requested=required_qty,
                    )
                )

    def _afa_reserve_web_stock(self):
        now = fields.Datetime.now()
        for order in self:
            if not order.website_id or order.state not in ('draft', 'sent'):
                continue
            if order.afa_stock_reserved_until:
                if order.afa_stock_reserved_until <= now:
                    raise ValidationError(_('The seven-day stock reservation has expired.'))
                order._afa_check_web_reserved_stock()
                continue

            order._afa_check_web_reserved_stock()
            order.afa_stock_reserved_until = now + timedelta(days=7)

    def action_confirm(self):
        now = fields.Datetime.now()
        expired_orders = self.filtered(
            lambda order: (
                order.website_id
                and order.state in ('draft', 'sent')
                and order.afa_stock_reserved_until
                and order.afa_stock_reserved_until <= now
            )
        )
        if expired_orders:
            raise ValidationError(
                _('The seven-day reservation expired; this order cannot be confirmed.')
            )
        return super().action_confirm()

    def _action_confirm(self):
        self._afa_check_web_reserved_stock()
        return super()._action_confirm()

    @api.model
    def _cron_cancel_expired_web_stock_reservations(self):
        expired_orders = self.sudo().search(
            [
                ('afa_stock_reserved_until', '<=', fields.Datetime.now()),
                ('state', 'in', ('draft', 'sent')),
                ('website_id', '!=', False),
            ],
            order='afa_stock_reserved_until, id',
            limit=500,
        )
        for order in expired_orders:
            order.message_post(
                body=_('Canceled because the seven-day bank-transfer reservation expired.')
            )
            order.action_cancel()
