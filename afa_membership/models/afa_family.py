from odoo import fields, models


class AfaFamily(models.Model):
    _inherit = 'afa.family'

    membership_ids = fields.One2many(
        'afa.membership',
        'family_id',
        string='Period Links',
        groups='afa_family.group_family_manager',
    )
