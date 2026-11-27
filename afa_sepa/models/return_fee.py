from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class AfaSepaReturnFee(models.Model):
    _name = 'afa.sepa.return.fee'
    _description = 'AFA SEPA Return Fee'
    _order = 'returned_date, id'

    payment_line_id = fields.Many2one(
        'account.payment.line', required=True, ondelete='restrict', index=True
    )
    invoice_id = fields.Many2one(
        'account.move',
        related='payment_line_id.move_line_id.move_id',
        store=True,
        readonly=True,
    )
    family_id = fields.Many2one('afa.family', required=True, ondelete='restrict', index=True)
    partner_id = fields.Many2one('res.partner', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one('res.company', required=True, ondelete='restrict', index=True)
    currency_id = fields.Many2one('res.currency', required=True)
    returned_date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    amount = fields.Monetary(required=True, currency_field='currency_id')
    invoice_line_id = fields.Many2one(
        'account.move.line', ondelete='set null', readonly=True, copy=False
    )
    state = fields.Selection(
        [('pending', 'Pending'), ('invoiced', 'Invoiced'), ('cancelled', 'Cancelled')],
        compute='_compute_state',
        store=True,
        index=True,
    )
    cancel_date = fields.Date(readonly=True, copy=False)

    def init(self):
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_sepa_return_fee_payment_line_uniq '
            'ON afa_sepa_return_fee (payment_line_id)'
        )

    @api.depends('invoice_line_id', 'invoice_line_id.move_id.state', 'cancel_date')
    def _compute_state(self):
        for fee in self:
            if fee.cancel_date:
                fee.state = 'cancelled'
            elif fee.invoice_line_id and fee.invoice_line_id.move_id.state != 'cancel':
                fee.state = 'invoiced'
            else:
                fee.state = 'pending'

    @api.model
    def register_return(self, payment_line, returned_date=None):
        payment_line.ensure_one()
        amount = payment_line.company_id.afa_sepa_return_fee_amount
        if amount <= 0:
            return self.browse()
        if self.search_count([('payment_line_id', '=', payment_line.id)]):
            return self.search([('payment_line_id', '=', payment_line.id)], limit=1)
        return self.with_context(_afa_register_sepa_return_fee=True).create(
            {
                'payment_line_id': payment_line.id,
                'family_id': payment_line.afa_family_id.id,
                'partner_id': payment_line.partner_id.id,
                'company_id': payment_line.company_id.id,
                'currency_id': payment_line.company_id.currency_id.id,
                'returned_date': returned_date or fields.Date.context_today(self),
                'amount': amount,
            }
        )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('_afa_register_sepa_return_fee'):
            raise ValidationError(_('SEPA return fees are created when an AFA debit is returned.'))
        for vals in vals_list:
            payment_line = self.env['account.payment.line'].browse(vals.get('payment_line_id'))
            if (
                not payment_line.afa_family_id
                or payment_line.afa_family_id.id != vals.get('family_id')
                or payment_line.partner_id.id != vals.get('partner_id')
                or payment_line.company_id.id != vals.get('company_id')
                or payment_line.company_id.currency_id.id != vals.get('currency_id')
                or vals.get('amount', 0) <= 0
            ):
                raise ValidationError(_('The return fee must match a valid AFA debit.'))
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get('_afa_cancel_sepa_return_fee') and set(vals) == {'cancel_date'}:
            cancel_date = vals['cancel_date']
            for fee in self:
                if cancel_date:
                    if fee.cancel_date:
                        raise ValidationError(_('This SEPA return fee is already cancelled.'))
                    if fee.invoice_line_id and fee.invoice_line_id.move_id.state != 'cancel':
                        raise ValidationError(
                            _(
                                'Only pending SEPA return fees can be cancelled. '
                                'Cancel the invoiced fee line through its invoice.'
                            )
                        )
                elif not fee.cancel_date:
                    raise ValidationError(
                        _('Only cancelled SEPA return fees can be set back to pending.')
                    )
            return super().write(vals)
        if self.env.context.get('_afa_link_sepa_return_fee') and set(vals) == {'invoice_line_id'}:
            for fee in self:
                if fee.cancel_date:
                    raise ValidationError(_('A cancelled SEPA return fee cannot be invoiced.'))
                line = self.env['account.move.line'].browse(vals['invoice_line_id'])
                invoice = line.move_id
                if (
                    not line
                    or invoice.state != 'draft'
                    or invoice.move_type != 'out_invoice'
                    or invoice.afa_service_family_id != fee.family_id
                    or invoice.partner_id != fee.partner_id
                    or invoice.company_id != fee.company_id
                    or invoice.invoice_date < fee.returned_date
                    or line.product_id
                    != self.env.ref('afa_sepa.product_sepa_return_fee').product_variant_id
                    or line.quantity != 1
                    or line.price_unit != fee.amount
                    or line.tax_ids
                ):
                    raise ValidationError(
                        _('The invoice line does not match this SEPA return fee.')
                    )
                if (
                    fee.invoice_line_id
                    and fee.invoice_line_id.move_id.state != 'cancel'
                    and fee.invoice_line_id != line
                ):
                    raise ValidationError(
                        _('An active SEPA return fee invoice line cannot be replaced.')
                    )
            return super().write(vals)
        raise ValidationError(_('SEPA return fee history cannot be edited.'))

    def unlink(self):
        raise ValidationError(
            _(
                'SEPA return fee history cannot be deleted. '
                'Cancel a fee that should not be invoiced instead.'
            )
        )

    def action_cancel(self):
        self._require_account_manager()
        self.sudo().with_context(_afa_cancel_sepa_return_fee=True).write(
            {'cancel_date': fields.Date.context_today(self)}
        )

    def action_set_pending(self):
        self._require_account_manager()
        self.sudo().with_context(_afa_cancel_sepa_return_fee=True).write({'cancel_date': False})

    def _require_account_manager(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise AccessError(_('Only accounting managers can change SEPA return fees.'))

    @api.model
    def _is_return_fee_invoice(self, invoice):
        if 'afa_acollida_charge_ids' in invoice._fields and invoice.afa_acollida_charge_ids:
            return True
        service_charges = (
            invoice.afa_service_charge_ids
            if 'afa_service_charge_ids' in invoice._fields
            else self.env['afa.service.charge']
        )
        return any(
            'is_extracurricular' in charge.subscription_id.service_id._fields
            and charge.subscription_id.service_id.is_extracurricular
            for charge in service_charges
        )

    @api.model
    def invoice_pending_fees(self, invoices):
        invoices = invoices.filtered(
            lambda invoice: (
                invoice.state == 'draft'
                and invoice.move_type == 'out_invoice'
                and invoice.afa_service_family_id
                and invoice.invoice_date
                and self._is_return_fee_invoice(invoice)
            )
        )
        if not invoices:
            return

        fees = self.sudo().search(
            [
                ('state', '=', 'pending'),
                ('company_id', 'in', invoices.mapped('company_id').ids),
                ('family_id', 'in', invoices.mapped('afa_service_family_id').ids),
                ('partner_id', 'in', invoices.mapped('partner_id').ids),
            ],
            order='returned_date, id',
        )
        if not fees:
            return
        self.env.cr.execute(
            'SELECT id FROM afa_sepa_return_fee WHERE id = ANY(%s) ORDER BY id FOR UPDATE',
            [fees.ids],
        )
        fees.invalidate_recordset(['state', 'invoice_line_id'])
        fees = fees.filtered(lambda fee: fee.state == 'pending')

        product = self.env.ref('afa_sepa.product_sepa_return_fee').product_variant_id
        for fee in fees:
            candidates = invoices.filtered(
                lambda invoice, fee=fee: (
                    invoice.afa_service_family_id == fee.family_id
                    and invoice.partner_id == fee.partner_id
                    and invoice.company_id == fee.company_id
                    and invoice.invoice_date >= fee.returned_date
                    and invoice.currency_id == fee.currency_id
                )
            ).sorted(key=lambda invoice: (not bool(invoice.payment_mode_id), invoice.id))
            if not candidates:
                continue

            invoice = candidates[0]
            company_product = product.with_company(invoice.company_id)
            income_account = company_product._get_product_accounts().get('income')
            income_account = income_account or invoice.journal_id.default_account_id
            if not income_account:
                raise ValidationError(
                    _(
                        'Configure an income account for the SEPA Return Fee product '
                        'in the invoice company.'
                    )
                )
            original_invoice = fee.invoice_id
            invoice_line = (
                self.env['account.move.line']
                .with_company(invoice.company_id)
                .create(
                    {
                        'move_id': invoice.id,
                        'product_id': product.id,
                        'account_id': income_account.id,
                        'name': _('Returned SEPA debit fee — %s') % original_invoice.name,
                        'quantity': 1,
                        'price_unit': fee.amount,
                        'tax_ids': [(6, 0, [])],
                    }
                )
            )
            fee.with_context(_afa_link_sepa_return_fee=True).write(
                {'invoice_line_id': invoice_line.id}
            )
