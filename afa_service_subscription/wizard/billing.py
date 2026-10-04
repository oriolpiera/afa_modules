from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class AfaServiceBilling(models.TransientModel):
    _name = 'afa.service.billing'
    _description = 'Review Monthly AFA Service Billing'

    month = fields.Date(
        required=True, default=lambda self: fields.Date.context_today(self).replace(day=1)
    )
    line_ids = fields.One2many('afa.service.billing.line', 'wizard_id', readonly=True)

    @api.constrains('month')
    def _check_month(self):
        for wizard in self:
            if wizard.month and wizard.month.day != 1:
                raise ValidationError(_('Choose the first day of the billing month.'))

    def _member_for(self, family, month):
        mode = self.env['ir.config_parameter'].sudo().get_param('afa_membership.mode', 'invoice')
        if mode == 'manual':
            return bool(family.manual_member)
        period = self.env['afa.membership.period'].search(
            [
                ('date_start', '<=', month),
                ('date_end', '>=', month),
            ],
            limit=1,
        )
        link = (
            self.env['afa.membership'].search(
                [
                    ('family_id', '=', family.id),
                    ('period_id', '=', period.id),
                    ('active', '=', True),
                ],
                limit=1,
            )
            if period
            else self.env['afa.membership']
        )
        return bool(link and link.is_invoice_member_on(month))

    def _snapshot(self, subscription):
        family = subscription.family_id
        member = self._member_for(family, self.month)
        return {
            'family_id': family.id,
            'payer_id': family.billing_partner_id.id,
            'member': member,
            'price': (
                subscription.service_id.member_price
                if member
                else subscription.service_id.nonmember_price
            ),
        }

    def _existing_invoice(self, family):
        return self.env['account.move'].search(
            [
                ('afa_service_family_id', '=', family.id),
                ('afa_service_month', '=', self.month),
                ('state', '!=', 'cancel'),
            ],
            limit=1,
        )

    def _candidates(self):
        return self.env['afa.service.subscription'].search(
            [
                ('start_month', '<=', self.month),
                '|',
                ('end_month', '=', False),
                ('end_month', '>', self.month),
                ('service_id.date_start', '<=', self.month),
                ('service_id.date_end', '>=', self.month),
            ]
        )

    def _reason(self, subscription, snapshot):
        if not snapshot['family_id'] or not snapshot['payer_id']:
            return _('Student has no billing family or guardian.')
        if (
            self.env['afa.service.charge']
            .sudo()
            .search_count(
                [
                    ('subscription_id', '=', subscription.id),
                    ('month', '=', self.month),
                    ('active', '=', True),
                ]
            )
        ):
            return _('Already invoiced.')
        invoice = self._existing_invoice(subscription.family_id)
        if invoice and invoice.state != 'draft':
            return _('The family invoice is already posted; cancel it before billing new services.')
        if invoice and (
            invoice.partner_id.id != snapshot['payer_id']
            or invoice.company_id != subscription.service_id.company_id
        ):
            return _('The existing family invoice has a different payer or company.')
        return False

    def action_preview(self):
        self.ensure_one()
        self._check_access()
        self.line_ids.unlink()
        for subscription in self._candidates():
            snapshot = self._snapshot(subscription)
            reason = self._reason(subscription, snapshot)
            self.env['afa.service.billing.line'].create(
                {
                    'wizard_id': self.id,
                    'subscription_id': subscription.id,
                    'month': self.month,
                    'family_id': snapshot['family_id'],
                    'payer_id': snapshot['payer_id'],
                    'member': snapshot['member'],
                    'price': snapshot['price'],
                    'include': not bool(reason),
                    'reason': reason,
                }
            )
        return self._action()

    def action_generate(self):
        self.ensure_one()
        self._check_access(accounting=True)
        if not self.line_ids:
            raise ValidationError(_('Preview the month before generating invoices.'))
        if any(line.month != self.month for line in self.line_ids):
            raise ValidationError(_('Billing month changed; refresh the preview.'))
        preview_ids = self.line_ids.mapped('subscription_id').ids
        if len(preview_ids) != len(self.line_ids) or set(preview_ids) != set(
            self._candidates().ids
        ):
            raise ValidationError(_('Subscriptions changed; refresh the preview.'))
        selected = self.line_ids.filtered('include')
        if not selected:
            raise ValidationError(_('Select at least one eligible charge.'))
        invoice_ids = []
        for family in selected.mapped('family_id').sorted('id'):
            # Lock the family, not merely invoices: two first-time billing requests
            # must not both conclude that there is no invoice yet.
            self.env.cr.execute('SELECT id FROM afa_family WHERE id = %s FOR UPDATE', [family.id])
            for student in (
                selected.filtered(lambda line, current=family: line.family_id == current)
                .mapped('student_id')
                .sorted('id')
            ):
                self.env['afa.service.subscription']._lock_student(student)
            self.env.invalidate_all()
            if set(self.line_ids.mapped('subscription_id').ids) != set(self._candidates().ids):
                raise ValidationError(_('Subscriptions changed; refresh the preview.'))
            invoice = self._existing_invoice(family)
            lines = selected.filtered(lambda line, current=family: line.family_id == current)
            if len(set(lines.mapped('subscription_id.service_id.company_id').ids)) != 1:
                raise ValidationError(
                    _('A family cannot be billed across companies on one invoice.')
                )
            prepared = []
            for line in lines:
                sub = line.subscription_id
                snapshot = self._snapshot(sub)
                if (
                    self._reason(sub, snapshot)
                    or line.family_id.id != snapshot['family_id']
                    or line.payer_id.id != snapshot['payer_id']
                    or line.member != snapshot['member']
                    or line.price != snapshot['price']
                ):
                    raise ValidationError(_('Billing details changed; refresh the preview.'))
                prepared.append((line, sub, snapshot))
            if not invoice:
                service = prepared[0][1].service_id
                invoice = (
                    self.env['account.move']
                    .with_context(_afa_generate_service_invoices=True)
                    .create(
                        {
                            'move_type': 'out_invoice',
                            'partner_id': family.billing_partner_id.id,
                            'company_id': service.company_id.id,
                            'invoice_date': self.month,
                            'afa_service_month': self.month,
                            'afa_service_family_id': family.id,
                        }
                    )
                )
            for _line, sub, snapshot in prepared:
                invoice_line = self.env['account.move.line'].create(
                    {
                        'move_id': invoice.id,
                        'product_id': sub.service_id.product_id.id,
                        'name': _('%s — %s — %s')
                        % (sub.service_id.name, sub.student_id.name, self.month),
                        'quantity': 1,
                        'price_unit': snapshot['price'],
                    }
                )
                self.env['afa.service.charge'].sudo().with_context(
                    _afa_generate_service_invoices=True
                ).create(
                    {
                        'subscription_id': sub.id,
                        'month': self.month,
                        'invoice_line_id': invoice_line.id,
                        'family_id': family.id,
                        'payer_id': snapshot['payer_id'],
                        'member': snapshot['member'],
                        'price': snapshot['price'],
                        'currency_id': invoice.currency_id.id,
                    }
                )
            invoice_ids.append(invoice.id)
        self.action_preview()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Monthly Service Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', invoice_ids)],
        }

    def _action(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _check_access(self, accounting=False):
        if not self.env.su and not self.env.user.has_group('afa_family.group_family_manager'):
            raise AccessError(_('Only family managers can review monthly billing.'))
        if (
            accounting
            and not self.env.su
            and not self.env.user.has_group('account.group_account_user')
        ):
            raise AccessError(_('Generating invoices also requires accounting access.'))


class AfaServiceBillingLine(models.TransientModel):
    _name = 'afa.service.billing.line'
    _description = 'Monthly AFA Service Billing Preview Line'

    wizard_id = fields.Many2one('afa.service.billing', required=True, ondelete='cascade')
    month = fields.Date(readonly=True)
    subscription_id = fields.Many2one('afa.service.subscription', required=True, readonly=True)
    student_id = fields.Many2one(related='subscription_id.student_id')
    service_id = fields.Many2one(related='subscription_id.service_id')
    family_id = fields.Many2one('afa.family', readonly=True)
    payer_id = fields.Many2one('res.partner', readonly=True)
    member = fields.Boolean(readonly=True)
    price = fields.Monetary(readonly=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='subscription_id.service_id.currency_id')
    include = fields.Boolean()
    reason = fields.Char(readonly=True)
