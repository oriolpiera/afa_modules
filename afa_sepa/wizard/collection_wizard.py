from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AfaSepaWizard(models.TransientModel):
    _name = 'afa.sepa.wizard'
    _description = 'Prepare AFA SEPA collections'

    invoice_ids = fields.Many2many('account.move', string='Invoices')
    payment_mode_id = fields.Many2one(
        'account.payment.mode',
        required=True,
        domain="[('payment_method_code', '=', 'sepa_direct_debit'),"
        " ('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company, required=True
    )
    journal_id = fields.Many2one(
        'account.journal',
        required=True,
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
    )
    line_ids = fields.One2many('afa.sepa.wizard.line', 'wizard_id', readonly=True)

    @api.model
    def default_get(self, fields_list):
        result = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'account.move' and 'invoice_ids' in fields_list:
            result['invoice_ids'] = [(6, 0, self.env.context.get('active_ids', []))]
        return result

    def _mandate_for(self, invoice):
        mandates = invoice.mandate_id or self.env['account.banking.mandate'].search(
            [
                ('partner_id', '=', invoice.partner_id.id),
                ('company_id', '=', invoice.company_id.id),
                ('state', '=', 'valid'),
            ]
        )
        return mandates.filtered(
            lambda m: (
                m.partner_id == invoice.partner_id
                and m.company_id == invoice.company_id
                and m.state == 'valid'
                and m.format == 'sepa'
                and m.scheme == 'CORE'
                and m.signature_date
                and m.signature_date <= fields.Date.context_today(self)
                and m.partner_bank_id.partner_id == invoice.partner_id
                and m.partner_bank_id.acc_type == 'iban'
                and not (m.type == 'oneoff' and m.last_debit_date)
            )
        )[:1]

    def _evaluate(self, invoice):
        if (
            invoice.company_id != self.company_id
            or invoice.move_type != 'out_invoice'
            or (invoice.state != 'posted' or invoice.amount_residual <= 0)
        ):
            return False, _('Not an open posted customer invoice in this company.')
        if invoice.currency_id.name != 'EUR':
            return False, _('The invoice must be in EUR.')
        family = invoice.afa_membership_id.family_id or invoice.partner_id.afa_family_id
        if not family:
            return False, _('The invoice has no AFA family.')
        if (
            self.payment_mode_id.company_id != invoice.company_id
            or (self.payment_mode_id.payment_method_code != 'sepa_direct_debit')
            or self.payment_mode_id.group_lines
        ):
            return False, _('Select an ungrouped SEPA direct debit mode for this company.')
        if not (
            self.payment_mode_id.sepa_creditor_identifier
            or self.company_id.sepa_creditor_identifier
        ):
            return False, _('A SEPA creditor identifier is missing.')
        if self.journal_id.company_id != invoice.company_id or (
            self.journal_id.type != 'bank' or not self.journal_id.bank_account_id
        ):
            return False, _('Select a bank journal with the creditor account.')
        if (
            self.payment_mode_id.bank_account_link == 'fixed'
            and (self.payment_mode_id.fixed_journal_id != self.journal_id)
            or self.payment_mode_id.bank_account_link == 'variable'
            and (self.journal_id not in self.payment_mode_id.variable_journal_ids)
        ):
            return False, _('The journal is not allowed by this payment mode.')
        mandate = self._mandate_for(invoice)
        if not mandate:
            return False, _('No valid SEPA Core mandate with an IBAN owned by the invoice payer.')
        receivables = invoice.line_ids.filtered(
            lambda l: (
                l.account_id.account_type == 'asset_receivable'
                and l.amount_residual > 0
                and not l.reconciled
            )
        )
        if len(receivables) != 1:
            return False, _('The invoice needs exactly one open receivable line.')
        if self.env['account.payment.line'].search_count(
            [
                ('move_line_id', '=', receivables.id),
                ('afa_family_id', '!=', False),
                ('afa_returned', '=', False),
                ('state', '!=', 'cancel'),
            ]
        ):
            return False, _('The remaining balance is already in an active debit order.')
        return mandate, False

    def action_preview(self):
        self.ensure_one()
        self._check_access()
        self.line_ids.unlink()
        for invoice in self.invoice_ids:
            mandate, reason = self._evaluate(invoice)
            self.env['afa.sepa.wizard.line'].create(
                {
                    'wizard_id': self.id,
                    'invoice_id': invoice.id,
                    'reason': reason or _('Eligible'),
                    'eligible': bool(mandate),
                }
            )
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_prepare(self):
        self.ensure_one()
        self._check_access()
        if not self.invoice_ids:
            raise UserError(_('Select at least one invoice.'))
        if set(self.line_ids.mapped('invoice_id').ids) != set(self.invoice_ids.ids):
            return self.action_preview()
        order = self.env['account.payment.order']
        for invoice in self.invoice_ids:
            mandate, _reason = self._evaluate(invoice)
            if not mandate:
                continue
            if not order:
                order = order.create(
                    {'payment_mode_id': self.payment_mode_id.id, 'journal_id': self.journal_id.id}
                )
            receivable = invoice.line_ids.filtered(
                lambda l: (
                    l.account_id.account_type == 'asset_receivable'
                    and l.amount_residual > 0
                    and not l.reconciled
                )
            )
            vals = receivable._prepare_payment_line_vals(order)
            vals.update(
                {
                    'partner_id': invoice.partner_id.id,
                    'partner_bank_id': mandate.partner_bank_id.id,
                    'mandate_id': mandate.id,
                    'currency_id': invoice.currency_id.id,
                    'amount_currency': invoice.amount_residual,
                    'communication': invoice.name or invoice.ref or '/',
                }
            )
            self.env['account.payment.line'].create(vals)
        if not order:
            return self.action_preview()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.order',
            'res_id': order.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _check_access(self):
        if (
            not self.env.user.has_group('afa_family.group_family_manager')
            or not (self.env.user.has_group('account.group_account_user'))
            or not self.env.user.has_group('account_payment_order.group_account_payment')
        ):
            raise UserError(_('AFA collections require family management and accounting access.'))


class AfaSepaWizardLine(models.TransientModel):
    _name = 'afa.sepa.wizard.line'
    _description = 'AFA SEPA eligibility preview'

    wizard_id = fields.Many2one('afa.sepa.wizard', required=True, ondelete='cascade')
    invoice_id = fields.Many2one('account.move', required=True)
    eligible = fields.Boolean(readonly=True)
    reason = fields.Char(readonly=True)
