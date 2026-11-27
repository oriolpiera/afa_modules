from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.mail import email_split


class ResCompany(models.Model):
    _inherit = 'res.company'

    afa_paid_order_email = fields.Char(
        string='Paid Order Notification Email',
        help=(
            'Internal address that receives a copy of each paid webshop order so the '
            'team can prepare the delivery or the school pickup. Several addresses '
            'can be separated with a comma. Leave it empty to disable the notice.'
        ),
    )

    @api.constrains('afa_paid_order_email')
    def _check_afa_paid_order_email(self):
        for company in self:
            entered = [
                address.strip()
                for address in (company.afa_paid_order_email or '').split(',')
                if address.strip()
            ]
            if any(len(email_split(address)) != 1 for address in entered):
                raise ValidationError(
                    _('The paid order notification email must be a valid address.')
                )
