from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    afa_birthdate = fields.Date(
        string='Student Date of Birth',
        groups='afa_family.group_family_manager',
    )
