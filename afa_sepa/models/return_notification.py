import logging
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AfaSepaReturnNotification(models.Model):
    _name = 'afa.sepa.return.notification'
    _description = 'AFA SEPA Return Notification'
    _order = 'create_date desc, id desc'

    partner_id = fields.Many2one('res.partner', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one('res.company', required=True, ondelete='restrict', index=True)
    currency_id = fields.Many2one('res.currency', required=True)
    payment_return_id = fields.Many2one('payment.return', ondelete='set null', index=True)
    returned_date = fields.Date(required=True, index=True)
    email_to = fields.Char(readonly=True)
    state = fields.Selection(
        [
            ('queued', 'Queued'),
            ('no_email', 'No Email Address'),
            ('error', 'Queue Error'),
        ],
        required=True,
        default='no_email',
        readonly=True,
        index=True,
    )
    mail_id = fields.Many2one('mail.mail', readonly=True, ondelete='set null')
    line_ids = fields.One2many(
        'afa.sepa.return.notification.line', 'notification_id', readonly=True
    )
    total_returned_amount = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_fee_amount = fields.Monetary(compute='_compute_totals', currency_field='currency_id')

    @api.depends('line_ids.amount', 'line_ids.fee_amount')
    def _compute_totals(self):
        for notification in self:
            notification.total_returned_amount = sum(notification.line_ids.mapped('amount'))
            notification.total_fee_amount = sum(notification.line_ids.mapped('fee_amount'))

    @api.model
    def queue_for_return(self, entries, payment_return=None, returned_date=None):
        grouped_entries = defaultdict(list)
        for payment_line, return_line in entries:
            if not payment_line.afa_family_id:
                continue
            key = (payment_line.company_id.id, payment_line.partner_id.id)
            grouped_entries[key].append((payment_line, return_line))

        notifications = self.browse()
        template = self.env.ref('afa_sepa.mail_template_return_notification').sudo()
        for (company_id, partner_id), group_entries in sorted(grouped_entries.items()):
            company = self.env['res.company'].browse(company_id)
            partner = self.env['res.partner'].browse(partner_id)
            email_to = (partner.email or '').strip()
            notification = (
                self.sudo()
                .with_context(_afa_create_return_notification=True)
                .create(
                    {
                        'partner_id': partner.id,
                        'company_id': company.id,
                        'currency_id': company.currency_id.id,
                        'payment_return_id': payment_return.id if payment_return else False,
                        'returned_date': returned_date or fields.Date.context_today(self),
                        'email_to': email_to,
                    }
                )
            )
            notifications |= notification
            line_values = []
            for payment_line, return_line in group_entries:
                fee = (
                    self.env['afa.sepa.return.fee']
                    .sudo()
                    .search([('payment_line_id', '=', payment_line.id)], limit=1)
                )
                reason_parts = []
                if return_line:
                    if return_line.reason_id:
                        reason_parts.append(return_line.reason_id.display_name)
                    if return_line.reason_additional_information:
                        reason_parts.append(return_line.reason_additional_information)
                line_values.append(
                    {
                        'notification_id': notification.id,
                        'payment_line_id': payment_line.id,
                        'payment_return_line_id': return_line.id if return_line else False,
                        'currency_id': company.currency_id.id,
                        'amount': (
                            return_line.amount if return_line else payment_line.amount_currency
                        ),
                        'fee_amount': fee.amount if fee else 0,
                        'reason': ' — '.join(reason_parts),
                    }
                )
            self.env['afa.sepa.return.notification.line'].sudo().with_context(
                _afa_create_return_notification=True
            ).create(line_values)
            if not email_to:
                continue

            try:
                with self.env.cr.savepoint():
                    mail_id = template.with_context(lang=partner.lang or self.env.lang).send_mail(
                        notification.id,
                        force_send=False,
                        email_values={'email_to': email_to},
                    )
            except Exception:
                _logger.exception(
                    'Could not queue the SEPA return email for partner %s',
                    partner.id,
                )
                notification.with_context(_afa_update_return_notification=True).write(
                    {'state': 'error'}
                )
                continue
            notification.with_context(_afa_update_return_notification=True).write(
                {'state': 'queued', 'mail_id': mail_id}
            )
        return notifications

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('_afa_create_return_notification'):
            raise ValidationError(_('Return notifications are created by the return workflow.'))
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get('_afa_update_return_notification') and set(vals) <= {
            'state',
            'mail_id',
        }:
            return super().write(vals)
        raise ValidationError(_('Return notification history cannot be edited.'))


class AfaSepaReturnNotificationLine(models.Model):
    _name = 'afa.sepa.return.notification.line'
    _description = 'AFA SEPA Return Notification Line'

    notification_id = fields.Many2one(
        'afa.sepa.return.notification', required=True, ondelete='cascade', index=True
    )
    payment_line_id = fields.Many2one(
        'account.payment.line', required=True, ondelete='restrict', index=True
    )
    payment_return_line_id = fields.Many2one(
        'payment.return.line', ondelete='set null', readonly=True
    )
    invoice_id = fields.Many2one(
        'account.move',
        related='payment_line_id.move_line_id.move_id',
        readonly=True,
    )
    currency_id = fields.Many2one('res.currency', required=True)
    amount = fields.Monetary(required=True, currency_field='currency_id')
    fee_amount = fields.Monetary(currency_field='currency_id')
    reason = fields.Char()

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('_afa_create_return_notification'):
            raise ValidationError(
                _('Return notification lines are created by the return workflow.')
            )
        return super().create(vals_list)

    def write(self, vals):
        raise ValidationError(_('Return notification history cannot be edited.'))
