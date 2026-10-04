from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    afa_manual_discount = fields.Boolean(copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'discount' in vals:
                vals.setdefault('afa_manual_discount', True)
        return super().create(vals_list)

    def write(self, vals):
        if (
            'discount' in vals
            and 'afa_manual_discount' not in vals
            and not self.env.context.get('_afa_repricing')
            and not self.env.context.get('sale_write_from_compute')
        ):
            vals = {**vals, 'afa_manual_discount': True}
        return super().write(vals)
