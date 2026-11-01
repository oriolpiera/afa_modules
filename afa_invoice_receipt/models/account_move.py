import re

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    afa_receipt_payer_iban = fields.Char(compute='_compute_afa_receipt_bank_details')
    afa_receipt_payer_bank = fields.Char(compute='_compute_afa_receipt_bank_details')
    afa_receipt_transfer_iban = fields.Char(compute='_compute_afa_receipt_bank_details')

    @api.depends(
        'move_type',
        'partner_id',
        'company_id',
        'mandate_id',
        'mandate_id.partner_id',
        'mandate_id.company_id',
        'mandate_id.state',
        'mandate_id.format',
        'mandate_id.scheme',
        'mandate_id.type',
        'mandate_id.signature_date',
        'mandate_id.last_debit_date',
        'mandate_id.partner_bank_id.acc_number',
        'mandate_id.partner_bank_id.acc_type',
        'mandate_id.partner_bank_id.partner_id',
        'mandate_id.partner_bank_id.bank_id.name',
        'partner_bank_id',
        'partner_bank_id.acc_number',
    )
    def _compute_afa_receipt_bank_details(self):
        today = fields.Date.context_today(self)
        for move in self:
            move.afa_receipt_payer_iban = False
            move.afa_receipt_payer_bank = False
            move.afa_receipt_transfer_iban = False
            if move.move_type != 'out_invoice':
                continue

            mandate = move._afa_receipt_get_mandate(today)
            if mandate:
                account = mandate.partner_bank_id
                iban = re.sub(r'\s+', '', account.acc_number or '')
                if iban:
                    move.afa_receipt_payer_iban = f'****{iban[-4:]}'
                move.afa_receipt_payer_bank = account.bank_id.name or False
                continue

            account = move.partner_bank_id
            if account and account.partner_id == move.company_id.partner_id:
                move.afa_receipt_transfer_iban = account.acc_number or False

    def _afa_receipt_get_mandate(self, today=None):
        self.ensure_one()
        today = today or fields.Date.context_today(self)

        def usable(mandate):
            return bool(
                mandate.partner_id == self.partner_id
                and mandate.company_id == self.company_id
                and mandate.state == 'valid'
                and mandate.format == 'sepa'
                and mandate.scheme == 'CORE'
                and mandate.signature_date
                and mandate.signature_date <= today
                and mandate.partner_bank_id.partner_id == self.partner_id
                and mandate.partner_bank_id.acc_type == 'iban'
                and not (mandate.type == 'oneoff' and mandate.last_debit_date)
            )

        mandate = self.mandate_id.sudo().filtered(usable)
        if mandate:
            return mandate[:1]
        mandates = (
            self.env['account.banking.mandate']
            .sudo()
            .search(
                [
                    ('partner_id', '=', self.partner_id.id),
                    ('company_id', '=', self.company_id.id),
                    ('state', '=', 'valid'),
                ]
            )
        )
        return mandates.filtered(usable)[:1]

    def _get_mail_template(self):
        if self and all(move.move_type == 'out_invoice' for move in self):
            return self.env.ref('afa_invoice_receipt.email_template_edi_receipt')
        return super()._get_mail_template()
