from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountPaymentLine(models.Model):
    _inherit = 'account.payment.line'

    afa_family_id = fields.Many2one('afa.family', readonly=True, copy=False, index=True)
    afa_returned = fields.Boolean(readonly=True, copy=False, default=False)

    def init(self):
        # OCA reoffers uploaded lines before bank reconciliation; keep them reserved.
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_sepa_reserved_move_line_uniq '
            'ON account_payment_line (move_line_id) '
            'WHERE afa_family_id IS NOT NULL AND move_line_id IS NOT NULL '
            "AND NOT afa_returned AND state != 'cancel'"
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['afa_returned'] = False
            order = self.env['account.payment.order'].browse(vals.get('order_id'))
            move_line = self.env['account.move.line'].browse(vals.get('move_line_id'))
            if order.payment_method_id.code == 'sepa_direct_debit' and move_line:
                invoice = move_line.move_id
                family = invoice.afa_membership_id.family_id or invoice.partner_id.afa_family_id
                vals.pop('afa_family_id', None)
                if family:
                    vals['afa_family_id'] = family.id
                    self._check_source(invoice, move_line)
            elif vals.get('afa_family_id'):
                raise ValidationError(_('AFA collections need a family invoice and SEPA order.'))
        lines = super().create(vals_list)
        lines._check_afa_collection()
        return lines

    def write(self, vals):
        if 'afa_family_id' in vals or ('afa_returned' in vals and not self.env.su):
            raise UserError(_('AFA collection history cannot be edited directly.'))
        if {'move_line_id', 'order_id'} & vals.keys() and self.filtered('afa_family_id'):
            raise UserError(_('AFA debit source and order cannot be reassigned.'))
        result = super().write(vals)
        if {
            'partner_id',
            'partner_bank_id',
            'mandate_id',
            'amount_currency',
            'currency_id',
            'move_line_id',
            'order_id',
        } & vals.keys():
            self._check_afa_collection()
        return result

    def unlink(self):
        if self.filtered(lambda line: line.afa_family_id and line.state != 'draft'):
            raise UserError(_('Confirmed AFA debit history cannot be deleted.'))
        return super().unlink()

    @api.model
    def _check_source(self, invoice, move_line):
        if (
            invoice.move_type != 'out_invoice'
            or invoice.state != 'posted'
            or (move_line.account_id.account_type != 'asset_receivable')
            or move_line.reconciled
            or move_line.amount_residual <= 0
        ):
            raise ValidationError(
                _('Only open posted customer invoice receivables can be collected.')
            )

    @api.constrains(
        'partner_id',
        'partner_bank_id',
        'mandate_id',
        'amount_currency',
        'currency_id',
        'move_line_id',
        'order_id',
    )
    def _check_afa_collection(self):
        for line in self.filtered('afa_family_id'):
            invoice = line.move_line_id.move_id
            line._check_source(invoice, line.move_line_id)
            if line.afa_family_id != (
                invoice.afa_membership_id.family_id or invoice.partner_id.afa_family_id
            ):
                raise ValidationError(_('The collection family does not match the invoice.'))
            mandate = line.mandate_id
            bank = line.partner_bank_id
            creditor = (
                line.order_id.payment_mode_id.sepa_creditor_identifier
                or line.company_id.sepa_creditor_identifier
            )
            if line.order_id.payment_type != 'inbound' or (
                line.order_id.payment_method_id.code != 'sepa_direct_debit'
            ):
                raise ValidationError(_('AFA collections require inbound SEPA direct debit.'))
            if line.order_id.journal_id.bank_account_id.acc_type != 'iban':
                raise ValidationError(_('The creditor bank journal needs an IBAN.'))
            if (
                line.partner_id != invoice.partner_id
                or not mandate
                or (
                    mandate.partner_id != invoice.partner_id
                    or bank != mandate.partner_bank_id
                    or bank.partner_id != invoice.partner_id
                    or bank.acc_type != 'iban'
                    or mandate.state != 'valid'
                    or mandate.format != 'sepa'
                    or mandate.scheme != 'CORE'
                    or not mandate.signature_date
                    or mandate.signature_date > fields.Date.context_today(line)
                    or mandate.company_id != invoice.company_id
                )
            ):
                raise ValidationError(
                    _('The invoice payer needs their own valid SEPA Core mandate and IBAN.')
                )
            if (
                not creditor
                or line.currency_id.name != 'EUR'
                or (line.amount_currency <= 0 or line.amount_currency > invoice.amount_residual)
            ):
                raise ValidationError(
                    _('The debit needs a creditor ID, EUR and a positive open amount.')
                )

    def draft2open_payment_line_check(self):
        self._check_afa_collection()
        return super().draft2open_payment_line_check()

    def action_record_return(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Only accounting managers can record returned debits.'))
        for line in self:
            if not line.afa_family_id or line.order_id.state != 'uploaded' or line.afa_returned:
                raise UserError(_('Only an uploaded AFA debit can be recorded as returned.'))
            if len(line.payment_ids) != 1 or line.payment_ids.payment_line_ids != line:
                raise UserError(_('AFA returns require one payment per debit line.'))
            # Odoo unreconciles the invoice when the payment is reset to draft.
            payment = line.payment_ids
            payment.action_draft()
            payment.action_cancel()
            if not line.move_line_id.amount_residual:
                raise UserError(
                    _('The invoice must be reopened before releasing a returned debit.')
                )
            line.sudo().write({'afa_returned': True})
        return True
