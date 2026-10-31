from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    afa_service_month = fields.Date(copy=False, readonly=True, index=True)
    afa_service_family_id = fields.Many2one(
        'afa.family', copy=False, readonly=True, groups='afa_family.group_family_manager'
    )
    afa_service_charge_ids = fields.One2many('afa.service.charge', 'invoice_id', readonly=True)
    afa_service_sponsor_charge_ids = fields.One2many(
        'afa.service.charge',
        'sponsor_invoice_id',
        readonly=True,
        groups='afa_family.group_family_manager',
    )

    def init(self):
        self.env.cr.execute('DROP INDEX IF EXISTS afa_service_invoice_family_month_uniq')
        self.env.cr.execute('DROP INDEX IF EXISTS afa_service_invoice_group_uniq')
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_service_invoice_payer_group_uniq '
            'ON account_move '
            '(afa_service_family_id, afa_service_month, partner_id, journal_id, '
            'COALESCE(payment_mode_id, 0)) '
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
        if (
            billed
            and {
                'partner_id',
                'afa_service_month',
                'afa_service_family_id',
            }
            & vals.keys()
        ):
            raise ValidationError(
                _('A service invoice cannot change its payer or billing identity.')
            )
        if (
            billed.filtered(lambda move: move.state != 'draft')
            and {
                'journal_id',
                'payment_mode_id',
            }
            & vals.keys()
        ):
            raise ValidationError(
                _('Posted service invoices cannot change their journal or payment mode.')
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
            charges = (
                billed.sudo().afa_service_charge_ids | billed.sudo().afa_service_sponsor_charge_ids
            )
            charges.with_context(_afa_cancel_service_invoice=True).write({'active': False})
        return result

    def unlink(self):
        service_invoices = self.filtered('afa_service_month')
        if service_invoices.filtered(lambda invoice: invoice.state != 'draft'):
            raise ValidationError(_('Only draft service invoices can be deleted.'))
        charges = (
            service_invoices.sudo().afa_service_charge_ids
            | service_invoices.sudo().afa_service_sponsor_charge_ids
        )
        charges.with_context(_afa_cancel_service_invoice=True).write({'active': False})
        return super(AccountMove, self.with_context(_afa_delete_service_invoice=True)).unlink()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    afa_service_charge_ids = fields.One2many('afa.service.charge', 'invoice_line_id')
    afa_service_sponsor_charge_ids = fields.One2many(
        'afa.service.charge',
        'sponsor_invoice_line_id',
        groups='afa_family.group_family_manager',
    )

    def write(self, vals):
        changed = {'price_unit', 'quantity', 'product_id', 'discount', 'move_id'} & vals.keys()
        if changed and self.sudo().with_context(active_test=False).filtered(
            lambda line: line.afa_service_charge_ids or line.afa_service_sponsor_charge_ids
        ):
            raise ValidationError(
                _('A billed service charge cannot be changed. Cancel the invoice first.')
            )
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get('_afa_delete_service_invoice') and self.sudo().with_context(
            active_test=False
        ).filtered(lambda line: line.afa_service_charge_ids or line.afa_service_sponsor_charge_ids):
            raise ValidationError(
                _(
                    'A billed service charge cannot be deleted. Cancel the invoice first, '
                    'then regenerate it from the monthly billing review.'
                )
            )
        return super().unlink()
