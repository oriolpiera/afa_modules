from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Membership(models.Model):
    _name = 'afa.membership'
    _description = 'AFA Family Period Link'

    family_id = fields.Many2one('afa.family', required=True, ondelete='restrict', index=True)
    period_id = fields.Many2one('afa.membership.period', required=True, ondelete='restrict')
    active = fields.Boolean(default=True)
    invoice_id = fields.Many2one(
        'account.move',
        string='Dues Invoice',
        ondelete='restrict',
        copy=False,
        readonly=True,
    )
    invoice_state = fields.Selection(related='invoice_id.state', string='Dues Invoice Status')
    dues_product_id = fields.Many2one(
        'product.product',
        string='Dues Product',
        domain=[('sale_ok', '=', True)],
    )

    def init(self):
        # The ORM overlap check gives a readable error; the index also protects
        # concurrent transactions that cannot see each other's uncommitted links.
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_membership_active_family_period_uniq '
            'ON afa_membership (family_id, period_id) WHERE active'
        )

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get('invoice_id') for vals in vals_list):
            raise ValidationError(_('Create the dues invoice from the family-period link.'))
        try:
            with self.env.cr.savepoint():
                return super().create(vals_list)
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_membership_active_family_period_uniq':
                raise
            raise ValidationError(
                _('A family can have only one active link per school year.')
            ) from error

    def write(self, vals):
        if 'invoice_id' in vals and not self.env.context.get('_afa_link_dues_invoice'):
            raise ValidationError(_('Create the dues invoice from the family-period link.'))
        if {'family_id', 'period_id'} & vals.keys() and self.filtered('invoice_id'):
            raise ValidationError(_('A billed family-period link cannot be reassigned.'))
        try:
            with self.env.cr.savepoint():
                result = super().write(vals)
                self.flush_recordset(['family_id', 'period_id', 'active'])
                return result
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_membership_active_family_period_uniq':
                raise
            raise ValidationError(
                _('A family can have only one active link per school year.')
            ) from error

    def action_create_dues_invoice(self, product=None):
        self.ensure_one()
        if not self.active or (self.invoice_id and self.invoice_id.state != 'cancel'):
            raise ValidationError(
                _('Only an active link without a current dues invoice can be invoiced.')
            )
        product = product or self.dues_product_id
        if not product:
            raise ValidationError(_('Choose a dues product before creating an invoice.'))
        product.ensure_one()
        if product._name != 'product.product' or product.lst_price <= 0:
            raise ValidationError(_('Choose a billable product with a positive price.'))
        guardian = self.family_id.billing_partner_id
        try:
            with self.env.cr.savepoint():
                invoice = self.env['account.move'].create(
                    {
                        'move_type': 'out_invoice',
                        'partner_id': guardian.id,
                        'afa_membership_id': self.id,
                        'invoice_line_ids': [
                            (
                                0,
                                0,
                                {
                                    'product_id': product.id,
                                    'quantity': 1,
                                    'price_unit': product.lst_price,
                                },
                            )
                        ],
                    }
                )
                if invoice.amount_total <= 0:
                    raise ValidationError(_('The dues invoice must have a positive amount.'))
                self.with_context(_afa_link_dues_invoice=True).write({'invoice_id': invoice.id})
        except IntegrityError as error:
            if error.diag.constraint_name != 'account_move_afa_membership_uniq':
                raise
            raise ValidationError(
                _('A dues invoice already exists for this family and school year.')
            ) from error
        return invoice

    def action_open_dues_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise ValidationError(_('This family-period link has no dues invoice.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Dues Invoice'),
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
        }

    def is_invoice_member_on(self, check_date):
        self.ensure_one()
        invoice = self.invoice_id
        qualifies = bool(
            self.active
            and self.period_id.date_start <= check_date <= self.period_id.date_end
            and invoice
            and invoice.afa_membership_id == self
            and invoice.partner_id
            and invoice.amount_total > 0
            and invoice.move_type == 'out_invoice'
            and invoice.state == 'posted'
            and invoice.payment_state == 'paid'
        )
        if not qualifies:
            return False
        # Odoo keeps an independently reversed invoice marked paid. Only a
        # posted customer credit note reversing this exact invoice revokes dues.
        moves = self.env['account.move'].sudo()
        credit_notes = moves.search_count(
            [
                ('reversed_entry_id', '=', invoice.id),
                ('move_type', '=', 'out_refund'),
                ('state', '=', 'posted'),
            ]
        )
        return not credit_notes

    @api.constrains('family_id', 'period_id', 'active')
    def _check_active_overlap(self):
        for link in self:
            if not link.active or not link.family_id or not link.period_id:
                continue
            period = link.period_id
            other_periods = self.env['afa.membership.period'].search(
                [
                    ('date_start', '<=', period.date_end),
                    ('date_end', '>=', period.date_start),
                ]
            )
            if self.search_count(
                [
                    ('id', '!=', link.id),
                    ('family_id', '=', link.family_id.id),
                    ('period_id', 'in', other_periods.ids),
                    ('active', '=', True),
                ]
            ):
                raise ValidationError(_('A family can have only one active link per school year.'))
