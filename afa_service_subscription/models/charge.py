from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaServiceCharge(models.Model):
    _name = 'afa.service.charge'
    _description = 'AFA Monthly Service Invoice Charge'
    _order = 'month desc, id desc'

    subscription_id = fields.Many2one(
        'afa.service.subscription', required=True, ondelete='restrict', index=True
    )
    month = fields.Date(required=True, index=True)
    invoice_line_id = fields.Many2one('account.move.line', required=True, ondelete='restrict')
    invoice_id = fields.Many2one('account.move', related='invoice_line_id.move_id', store=True)
    family_id = fields.Many2one('afa.family', required=True, ondelete='restrict')
    payer_id = fields.Many2one('res.partner', required=True, ondelete='restrict')
    member = fields.Boolean(string='Member at Invoicing')
    price = fields.Monetary(required=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', required=True)
    active = fields.Boolean(default=True, copy=False)

    def init(self):
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_service_charge_active_uniq '
            'ON afa_service_charge (subscription_id, month) WHERE active'
        )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('_afa_generate_service_invoices'):
            raise ValidationError(_('Generate charges from the monthly billing review.'))
        return super().create(vals_list)

    def write(self, vals):
        if (
            not self.env.context.get('_afa_cancel_service_invoice')
            or set(vals) != {'active'}
            or vals['active']
        ):
            raise ValidationError(_('Invoice charge history cannot be edited.'))
        return super().write(vals)

    def unlink(self):
        raise ValidationError(_('Invoice charge history cannot be deleted.'))
