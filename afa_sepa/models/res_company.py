from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    afa_sepa_return_fee_amount = fields.Monetary(
        string='SEPA Return Fee',
        currency_field='currency_id',
        default=4.0,
        help='Amount to recover for each returned AFA SEPA debit. Set to zero to disable.',
    )

    @api.constrains('afa_sepa_return_fee_amount')
    def _check_afa_sepa_return_fee_amount(self):
        if any(company.afa_sepa_return_fee_amount < 0 for company in self):
            raise ValidationError(_('The SEPA return fee cannot be negative.'))
