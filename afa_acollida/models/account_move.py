from odoo import _, fields, models
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    afa_acollida_charge_ids = fields.One2many('afa.acollida.charge', 'invoice_id', readonly=True)

    def write(self, vals):
        result = super().write(vals)
        if vals.get('state') == 'cancel':
            self.sudo().afa_acollida_charge_ids.with_context(
                _afa_cancel_acollida_invoice=True
            ).write({'active': False})
        return result


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    afa_acollida_charge_ids = fields.One2many(
        'afa.acollida.charge', 'invoice_line_id', readonly=True
    )

    def write(self, vals):
        changed = {'price_unit', 'quantity', 'product_id', 'discount', 'move_id'} & vals.keys()
        if changed and self.filtered('afa_acollida_charge_ids'):
            raise ValidationError(
                _('An invoiced Acollida charge cannot be changed. Cancel the invoice first.')
            )
        return super().write(vals)

    def unlink(self):
        if self.filtered('afa_acollida_charge_ids'):
            raise ValidationError(_('An invoiced Acollida charge line cannot be deleted.'))
        return super().unlink()
