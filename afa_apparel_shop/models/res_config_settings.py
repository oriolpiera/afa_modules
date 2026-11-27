from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    afa_paid_order_email = fields.Char(
        related='company_id.afa_paid_order_email',
        readonly=False,
    )
