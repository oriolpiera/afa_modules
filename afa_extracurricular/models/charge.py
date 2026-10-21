from odoo import fields, models


class AfaServiceCharge(models.Model):
    _inherit = 'afa.service.charge'

    aid_id = fields.Many2one('afa.extracurricular.aid', ondelete='restrict', readonly=True)
