from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    afa_sepa_return_fee_amount = fields.Monetary(
        related='company_id.afa_sepa_return_fee_amount',
        readonly=False,
        currency_field='currency_id',
    )
