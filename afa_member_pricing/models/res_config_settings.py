from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    afa_member_pricelist_id = fields.Many2one(
        related='company_id.afa_member_pricelist_id', readonly=False
    )
    afa_nonmember_pricelist_id = fields.Many2one(
        related='company_id.afa_nonmember_pricelist_id', readonly=False
    )
