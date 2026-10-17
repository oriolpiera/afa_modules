from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaAcollidaCharge(models.Model):
    _name = 'afa.acollida.charge'
    _description = 'AFA Acollida Imported Monthly Charge'
    _order = 'month desc, student_id, id'

    config_id = fields.Many2one(
        'afa.acollida.config', required=True, ondelete='restrict', index=True
    )
    student_id = fields.Many2one(
        'res.partner',
        required=True,
        ondelete='restrict',
        index=True,
        domain=[('afa_family_role', '=', 'student')],
    )
    family_id = fields.Many2one('afa.family', required=True, ondelete='restrict', index=True)
    month = fields.Date(required=True, index=True)
    amount = fields.Monetary(required=True, currency_field='currency_id')
    base_amount = fields.Monetary(currency_field='currency_id')
    tranche = fields.Char()
    weekly_hours = fields.Char()
    parent_name = fields.Char()
    currency_id = fields.Many2one(related='config_id.currency_id')
    invoice_line_id = fields.Many2one(
        'account.move.line', ondelete='restrict', readonly=True, copy=False
    )
    invoice_id = fields.Many2one(
        'account.move', related='invoice_line_id.move_id', store=True, readonly=True
    )
    active = fields.Boolean(default=True, copy=False, index=True)

    def init(self):
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_acollida_charge_active_uniq '
            'ON afa_acollida_charge (config_id, student_id, month) WHERE active'
        )
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_acollida_charge_invoice_line_uniq '
            'ON afa_acollida_charge (invoice_line_id) WHERE invoice_line_id IS NOT NULL'
        )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('_afa_import_acollida_charges'):
            raise ValidationError(_('Import Acollida charges from the spreadsheet assistant.'))
        try:
            with self.env.cr.savepoint():
                return super().create(vals_list)
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_acollida_charge_active_uniq':
                raise
            raise ValidationError(
                _('This student already has an active Acollida charge for that month.')
            ) from error

    def write(self, vals):
        if (
            self.env.context.get('_afa_link_acollida_invoice')
            and set(vals) == {'invoice_line_id'}
            and all(not charge.invoice_line_id for charge in self)
        ):
            invoice_line = self.env['account.move.line'].browse(vals['invoice_line_id'])
            move = invoice_line.move_id
            if (
                not invoice_line
                or invoice_line.afa_acollida_charge_ids
                or any(
                    move.afa_service_family_id != charge.family_id
                    or move.afa_service_month != charge.month
                    or move.company_id != charge.config_id.company_id
                    or invoice_line.product_id != charge.config_id.product_id
                    or invoice_line.quantity != 1
                    or invoice_line.price_unit != charge.amount
                    for charge in self
                )
            ):
                raise ValidationError(_('The invoice line does not match this Acollida charge.'))
            return super().write(vals)
        if (
            self.env.context.get('_afa_cancel_acollida_invoice')
            and vals == {'active': False}
            and all(charge.invoice_id and charge.invoice_id.state == 'cancel' for charge in self)
        ):
            return super().write(vals)
        raise ValidationError(_('Imported Acollida charge history cannot be edited.'))

    def unlink(self):
        raise ValidationError(_('Imported Acollida charge history cannot be deleted.'))

    @api.constrains('config_id', 'student_id', 'family_id', 'month', 'amount', 'base_amount')
    def _check_charge(self):
        for charge in self:
            if charge.month and (
                charge.month.day != 1
                or not charge.config_id.period_id.date_start
                or charge.month < charge.config_id.period_id.date_start
                or charge.month > charge.config_id.period_id.date_end
            ):
                raise ValidationError(
                    _('The charge month must be inside the selected school year.')
                )
            if (
                charge.student_id.afa_family_role != 'student'
                or not charge.family_id
                or charge.family_id != charge.student_id.afa_family_id
            ):
                raise ValidationError(
                    _('An Acollida charge requires a student assigned to a family.')
                )
            if charge.amount <= 0:
                raise ValidationError(_('An imported Acollida charge must be greater than zero.'))
            if charge.base_amount < 0:
                raise ValidationError(_('The base monthly amount cannot be negative.'))
            if self.search_count(
                [
                    ('id', '!=', charge.id),
                    ('config_id', '=', charge.config_id.id),
                    ('student_id', '=', charge.student_id.id),
                    ('month', '=', charge.month),
                    ('active', '=', True),
                ]
            ):
                raise ValidationError(
                    _('This student already has an active Acollida charge for that month.')
                )
