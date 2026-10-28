from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    afa_is_accounting_partner_eligible = fields.Boolean(
        compute='_compute_afa_is_accounting_partner_eligible',
        store=True,
        compute_sudo=True,
        groups='account.group_account_user',
        help='Whether this contact can be selected for AFA accounting entries.',
    )

    @api.depends('afa_family_id', 'afa_family_id.billing_partner_id')
    def _compute_afa_is_accounting_partner_eligible(self):
        for partner in self:
            partner.afa_is_accounting_partner_eligible = (
                not partner.afa_family_id or partner.afa_family_id.billing_partner_id == partner
            )
