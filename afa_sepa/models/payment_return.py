from odoo import _, fields, models
from odoo.exceptions import UserError


class PaymentReturnLine(models.Model):
    _inherit = 'payment.return.line'

    def _get_afa_payment_lines(self):
        self.ensure_one()
        payments = self.env['account.payment']
        if self.reference and self.reference.isdigit():
            payments |= payments.search(
                [
                    ('id', '=', int(self.reference)),
                    ('payment_order_id', '!=', False),
                ]
            )
        payment_moves = self.move_line_ids.mapped('move_id')
        if payment_moves:
            payments |= payments.search(
                [
                    ('move_id', 'in', payment_moves.ids),
                    ('payment_order_id', '!=', False),
                ]
            )
        return self.env['account.payment.line'].search(
            [
                ('payment_ids', 'in', payments.ids),
                ('afa_family_id', '!=', False),
            ]
        )


class PaymentReturn(models.Model):
    _inherit = 'payment.return'

    afa_processed = fields.Boolean(readonly=True, copy=False)

    def action_confirm(self):
        self.ensure_one()
        if self.afa_processed:
            raise UserError(_('This AFA payment return has already been processed.'))

        # Import normally matches numeric EndToEndId values before confirmation.
        # Resolve by reference as well so an unmatched AFA debit cannot fall
        # through to the generic return accounting flow.
        matches = [
            (return_line, return_line._get_afa_payment_lines()) for return_line in self.line_ids
        ]
        if not any(payment_lines for _return_line, payment_lines in matches):
            return super().action_confirm()
        if any(len(payment_lines) != 1 for _return_line, payment_lines in matches):
            raise UserError(
                _(
                    'Every transaction in an AFA payment return must match exactly '
                    'one AFA debit. Split mixed or unmatched returns before confirming.'
                )
            )

        matched_lines = [payment_lines for _return_line, payment_lines in matches]
        payment_line_ids = [payment_line.id for lines in matched_lines for payment_line in lines]
        if len(payment_line_ids) != len(set(payment_line_ids)):
            raise UserError(_('An AFA debit can only appear once in a payment return.'))

        for return_line, payment_lines in matches:
            payment_line = payment_lines
            payment = payment_line.payment_ids
            if len(payment) != 1 or payment.payment_line_ids != payment_line:
                raise UserError(_('AFA returns require one payment per debit line.'))
            if (
                self.company_id != payment_line.company_id
                or self.journal_id != payment_line.order_id.journal_id
                or return_line.partner_id != payment_line.partner_id
            ):
                raise UserError(
                    _('The imported return does not match the AFA payment company, bank, or payer.')
                )
            expected_move_lines = payment.move_id.line_ids.filtered(
                lambda move_line, payment=payment: (
                    move_line.account_id == payment.destination_account_id
                    and move_line.partner_id == payment.partner_id
                )
            )
            if set(return_line.move_line_ids.ids) != set(expected_move_lines.ids):
                raise UserError(
                    _('The imported return does not match the AFA payment receivable line.')
                )
            if payment_line.currency_id.compare_amounts(
                return_line.amount, payment_line.amount_currency
            ):
                raise UserError(
                    _(
                        'Partial AFA payment returns are not supported. '
                        'The imported amount must equal the full debit.'
                    )
                )
            if return_line.expense_amount:
                raise UserError(
                    _(
                        'Do not add bank charges to an AFA payment return. '
                        'Record bank fees separately.'
                    )
                )

        notification_lines = []
        for return_line, payment_lines in matches:
            payment_lines.with_context(
                afa_return_date=self.date,
                _afa_sepa_suppress_return_notification=True,
            ).action_record_return()
            notification_lines.extend((payment_line, return_line) for payment_line in payment_lines)
        self.write({'afa_processed': True, 'state': 'done'})
        self.message_post(
            body=_(
                'Processed through the AFA Record Return workflow. '
                'No generic payment-return journal entry was created; '
                'account for the bank debit through the bank statement.'
            )
        )
        self.env['afa.sepa.return.notification'].sudo().queue_for_return(
            notification_lines,
            payment_return=self,
            returned_date=self.date,
        )
        return True

    def action_cancel(self):
        if self.filtered('afa_processed'):
            raise UserError(
                _(
                    'This AFA return was processed by cancelling its payment. '
                    'It cannot be cancelled with the generic payment-return action.'
                )
            )
        return super().action_cancel()

    def action_draft(self):
        if self.filtered('afa_processed'):
            raise UserError(_('An AFA payment return cannot be reset to draft after processing.'))
        return super().action_draft()
