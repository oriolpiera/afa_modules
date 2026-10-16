from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class AfaAcollidaBilling(models.TransientModel):
    _name = 'afa.acollida.billing'
    _description = 'Review Monthly Acollida Billing'

    month = fields.Date(
        required=True, default=lambda self: fields.Date.context_today(self).replace(day=1)
    )
    line_ids = fields.One2many('afa.acollida.billing.line', 'wizard_id', readonly=True)

    @api.constrains('month')
    def _check_month(self):
        for wizard in self:
            if wizard.month and wizard.month.day != 1:
                raise ValidationError(_('Choose the first day of the billing month.'))

    def _check_billing_permissions(self, accounting=False):
        if not self.env.su and not self.env.user.has_group('afa_family.group_family_manager'):
            raise AccessError(_('Only family managers can review Acollida billing.'))
        if (
            accounting
            and not self.env.su
            and not self.env.user.has_group('account.group_account_user')
        ):
            raise AccessError(_('Generating invoices also requires accounting access.'))

    def _charges(self):
        return self.env['afa.acollida.charge'].search(
            [('month', '=', self.month), ('active', '=', True)]
        )

    def _snapshot(self, charge):
        config = charge.config_id
        family = charge.family_id
        return {
            'family_id': family.id,
            'payer_id': family.billing_partner_id.id,
            'product_id': config.product_id.id,
            'journal_id': config.invoice_journal_id.id,
            'payment_mode_id': config.payment_mode_id.id,
            'company_id': config.company_id.id,
            'amount': charge.amount,
        }

    def _existing_invoice(self, family, journal, payment_mode):
        # Managers may review charges without accounting access; sudo only this identity lookup.
        return (
            self.env['account.move']
            .sudo()
            .search(
                [
                    ('afa_service_family_id', '=', family.id),
                    ('afa_service_month', '=', self.month),
                    ('journal_id', '=', journal.id),
                    ('payment_mode_id', '=', payment_mode.id),
                    ('state', '!=', 'cancel'),
                ],
                limit=1,
            )
        )

    def _reason(self, charge, snapshot):
        if not snapshot['family_id'] or not snapshot['payer_id']:
            return _('Student has no billing family or guardian.')
        if not snapshot['product_id']:
            return _('Configure a product on the Acollida school-year settings.')
        if not snapshot['journal_id']:
            return _('Configure an invoice journal on the Acollida school-year settings.')
        if not snapshot['payment_mode_id']:
            return _('Configure a payment mode on the Acollida school-year settings.')
        if charge.invoice_line_id:
            return _('Already invoiced.')
        invoice = self._existing_invoice(
            charge.family_id,
            charge.config_id.invoice_journal_id,
            charge.config_id.payment_mode_id,
        )
        if invoice and invoice.state != 'draft':
            return _('The family invoice is already posted; cancel it before billing Acollida.')
        if invoice and (
            invoice.partner_id.id != snapshot['payer_id']
            or invoice.company_id.id != snapshot['company_id']
        ):
            return _('The existing family invoice has a different payer or company.')
        return False

    def action_preview(self):
        self.ensure_one()
        self._check_billing_permissions()
        self._check_month()
        self.line_ids.unlink()
        for charge in self._charges():
            snapshot = self._snapshot(charge)
            reason = self._reason(charge, snapshot)
            self.env['afa.acollida.billing.line'].create(
                {
                    'wizard_id': self.id,
                    'charge_id': charge.id,
                    'month': self.month,
                    'family_id': snapshot['family_id'],
                    'payer_id': snapshot['payer_id'],
                    'product_id': snapshot['product_id'],
                    'journal_id': snapshot['journal_id'],
                    'payment_mode_id': snapshot['payment_mode_id'],
                    'company_id': snapshot['company_id'],
                    'amount': snapshot['amount'],
                    'include': not bool(reason),
                    'reason': reason,
                }
            )
        return self._action()

    def action_generate(self):
        self.ensure_one()
        self._check_billing_permissions(accounting=True)
        if not self.line_ids:
            raise ValidationError(_('Preview the month before generating invoices.'))
        if any(line.month != self.month for line in self.line_ids):
            raise ValidationError(_('Billing month changed; refresh the preview.'))
        preview_ids = self.line_ids.mapped('charge_id').ids
        if len(preview_ids) != len(self.line_ids) or set(preview_ids) != set(self._charges().ids):
            raise ValidationError(_('Imported charges changed; refresh the preview.'))
        selected = self.line_ids.filtered('include')
        if not selected:
            raise ValidationError(_('Select at least one eligible Acollida charge.'))

        grouped_lines = {}
        for line in selected:
            key = (line.family_id.id, line.journal_id.id, line.payment_mode_id.id)
            grouped_lines.setdefault(key, self.env['afa.acollida.billing.line'])
            grouped_lines[key] |= line

        invoice_ids = []
        for (family_id, journal_id, payment_mode_id), lines in sorted(grouped_lines.items()):
            family = self.env['afa.family'].browse(family_id)
            self.env.cr.execute('SELECT id FROM afa_family WHERE id = %s FOR UPDATE', [family.id])
            for student in lines.mapped('student_id').sorted('id'):
                self.env['afa.service.subscription']._lock_student(student)
            self.env.invalidate_all()
            if set(self.line_ids.mapped('charge_id').ids) != set(self._charges().ids):
                raise ValidationError(_('Imported charges changed; refresh the preview.'))
            if len(set(lines.mapped('company_id').ids)) != 1:
                raise ValidationError(
                    _('A family cannot be billed across companies on one invoice.')
                )

            company = lines[0].company_id
            journal = self.env['account.journal'].browse(journal_id)
            payment_mode = self.env['account.payment.mode'].browse(payment_mode_id)
            if journal.company_id != company or payment_mode.company_id != company:
                raise ValidationError(
                    _(
                        'Invoice journal and payment mode must match the Acollida '
                        'configuration company.'
                    )
                )
            prepared = []
            for line in lines:
                charge = line.charge_id
                snapshot = self._snapshot(charge)
                if (
                    self._reason(charge, snapshot)
                    or line.family_id.id != snapshot['family_id']
                    or line.payer_id.id != snapshot['payer_id']
                    or line.product_id.id != snapshot['product_id']
                    or line.journal_id.id != snapshot['journal_id']
                    or line.payment_mode_id.id != snapshot['payment_mode_id']
                    or line.company_id.id != snapshot['company_id']
                    or line.amount != snapshot['amount']
                ):
                    raise ValidationError(
                        _('Acollida billing details changed; refresh the preview.')
                    )
                prepared.append((line, charge, snapshot))

            invoice = self._existing_invoice(family, journal, payment_mode)
            if not invoice:
                invoice = (
                    self.env['account.move']
                    .with_context(_afa_generate_service_invoices=True)
                    .create(
                        {
                            'move_type': 'out_invoice',
                            'partner_id': family.billing_partner_id.id,
                            'company_id': company.id,
                            'journal_id': journal.id,
                            'payment_mode_id': payment_mode.id,
                            'invoice_date': self.month,
                            'afa_service_month': self.month,
                            'afa_service_family_id': family.id,
                        }
                    )
                )
            for _line, charge, snapshot in prepared:
                invoice_line = self.env['account.move.line'].create(
                    {
                        'move_id': invoice.id,
                        'product_id': snapshot['product_id'],
                        'name': _('%s — %s — %s')
                        % (charge.config_id.name, charge.student_id.name, self.month),
                        'quantity': 1,
                        'price_unit': snapshot['amount'],
                    }
                )
                charge.with_context(_afa_link_acollida_invoice=True).write(
                    {'invoice_line_id': invoice_line.id}
                )
            invoice_ids.append(invoice.id)

        self.action_preview()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Acollida Invoices'),
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
            'target': 'new',
        }


class AfaAcollidaBillingLine(models.TransientModel):
    _name = 'afa.acollida.billing.line'
    _description = 'Monthly Acollida Billing Preview Line'

    wizard_id = fields.Many2one('afa.acollida.billing', required=True, ondelete='cascade')
    month = fields.Date(readonly=True)
    charge_id = fields.Many2one('afa.acollida.charge', required=True, readonly=True)
    student_id = fields.Many2one(related='charge_id.student_id')
    family_id = fields.Many2one('afa.family', readonly=True)
    payer_id = fields.Many2one('res.partner', readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    amount = fields.Monetary(readonly=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='charge_id.currency_id')
    journal_id = fields.Many2one('account.journal', readonly=True)
    payment_mode_id = fields.Many2one('account.payment.mode', readonly=True)
    include = fields.Boolean()
    reason = fields.Char(readonly=True)
