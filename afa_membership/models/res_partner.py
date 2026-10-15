from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    afa_is_member = fields.Boolean(
        related='afa_family_id.is_member',
        string='AFA Member',
        readonly=True,
        groups='afa_family.group_family_manager',
    )
