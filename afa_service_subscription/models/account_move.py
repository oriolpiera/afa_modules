from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    afa_service_month = fields.Date(copy=False, readonly=True, index=True)
    afa_service_family_id = fields.Many2one(
        'afa.family', copy=False, readonly=True, groups='afa_family.group_family_manager'
    )
    afa_service_charge_ids = fields.One2many('afa.service.charge', 'invoice_id', readonly=True)

    def init(self):
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_service_invoice_family_month_uniq '
            'ON account_move (afa_service_family_id, afa_service_month) '
            "WHERE afa_service_family_id IS NOT NULL AND state != 'cancel'"
        )

    @api.model_create_multi
    def create(self, vals_list):
        if any(
            vals.get('afa_service_month') or vals.get('afa_service_family_id') for vals in vals_list
        ) and not self.env.context.get('_afa_generate_service_invoices'):
            raise AccessError(_('Generate service invoices from the monthly billing review.'))
        return super().create(vals_list)

    def write(self, vals):
        billed = self.filtered('afa_service_month')
        if billed and {'partner_id', 'afa_service_month', 'afa_service_family_id'} & vals.keys():
            raise ValidationError(
                _('A service invoice cannot change its payer or billing identity.')
            )
        if (
            vals.get('state')
            and vals['state'] != 'cancel'
            and billed.filtered(lambda move: move.state == 'cancel')
        ):
            raise ValidationError(
                _('Canceled service invoices cannot be reopened; regenerate them.')
            )
        result = super().write(vals)
        if vals.get('state') == 'cancel':
            billed.sudo().afa_service_charge_ids.with_context(
                _afa_cancel_service_invoice=True
            ).write({'active': False})
        return result


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    afa_service_charge_ids = fields.One2many('afa.service.charge', 'invoice_line_id')

    def write(self, vals):
        changed = {'price_unit', 'quantity', 'product_id', 'discount', 'move_id'} & vals.keys()
        if changed and self.filtered('afa_service_charge_ids'):
            raise ValidationError(
                _('A billed service charge cannot be changed. Cancel the invoice first.')
            )
        return super().write(vals)

    def unlink(self):
        if self.filtered('afa_service_charge_ids'):
            raise ValidationError(_('A billed service charge cannot be deleted.'))
        return super().unlink()
