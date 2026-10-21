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
        return family.is_member_on(month)

    def _snapshot(self, subscription):
        family = subscription.family_id
        member = self._member_for(family, self.month)
        service = subscription.service_id
        price = service.member_price if member else service.nonmember_price
        price = service.currency_id.round(price)
        return {
            'family_id': family.id,
            'payer_id': family.billing_partner_id.id,
            'member': member,
            'price': price,
            'family_price': price,
            'sponsor_id': False,
            'sponsor_price': 0,
            'subsidy_percent': 0,
            'tariff_basis': 'membership',
            'journal_id': service.invoice_journal_id.id,
            'payment_mode_id': service.payment_mode_id.id,
        }

    def _line_snapshot_values(self, snapshot):
        fields_to_copy = (
            'family_id',
            'payer_id',
            'member',
            'price',
            'family_price',
            'sponsor_id',
            'sponsor_price',
            'subsidy_percent',
            'tariff_basis',
            'journal_id',
            'payment_mode_id',
        )
        return {name: snapshot[name] for name in fields_to_copy}

    def _snapshot_matches_line(self, line, snapshot):
        return (
            line.family_id.id == snapshot['family_id']
            and line.payer_id.id == snapshot['payer_id']
            and line.member == snapshot['member']
            and line.price == snapshot['price']
            and line.family_price == snapshot['family_price']
            and (line.sponsor_id.id or False) == snapshot['sponsor_id']
            and line.sponsor_price == snapshot['sponsor_price']
            and line.subsidy_percent == snapshot['subsidy_percent']
            and line.tariff_basis == snapshot['tariff_basis']
            and line.journal_id.id == snapshot['journal_id']
            and (line.payment_mode_id.id or False) == snapshot['payment_mode_id']
        )

    def _charge_snapshot_values(self, snapshot):
        return {
            'member': snapshot['member'],
            'price': snapshot['price'],
            'sponsor_id': snapshot['sponsor_id'],
            'sponsor_price': snapshot['sponsor_price'],
            'subsidy_percent': snapshot['subsidy_percent'],
            'tariff_basis': snapshot['tariff_basis'],
        }

    def _invoice_allocations(self, snapshot):
        allocations = []
        if snapshot['family_price'] or not snapshot['sponsor_price']:
            allocations.append(
                {
                    'role': 'family',
                    'payer_id': snapshot['payer_id'],
                    'amount': snapshot['family_price'],
                    'payment_mode_id': snapshot['payment_mode_id'],
                }
            )
        if snapshot['sponsor_price']:
            allocations.append(
                {
                    'role': 'sponsor',
                    'payer_id': snapshot['sponsor_id'],
                    'amount': snapshot['sponsor_price'],
                    # Council invoices are issued for direct payment, not through the
                    # family's configured direct-debit mode.
                    'payment_mode_id': False,
                }
            )
        return allocations

    def _existing_invoice(self, family, payer, journal, payment_mode):
        return self.env['account.move'].search(
            [
                ('afa_service_family_id', '=', family.id),
                ('afa_service_month', '=', self.month),
                ('partner_id', '=', payer.id),
                ('journal_id', '=', journal.id),
                ('payment_mode_id', '=', payment_mode.id),
                ('state', '!=', 'cancel'),
            ],
            limit=1,
        )

    def _invoices_for_group(self, family, journal, payment_mode):
        return self.env['account.move'].search(
            [
                ('afa_service_family_id', '=', family.id),
                ('afa_service_month', '=', self.month),
                ('journal_id', '=', journal.id),
                ('payment_mode_id', '=', payment_mode.id),
                ('state', '!=', 'cancel'),
            ]
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
        if snapshot.get('billing_error'):
            return snapshot['billing_error']
        if not snapshot['family_id'] or not snapshot['payer_id']:
            return _('Student has no billing family or guardian.')
        if not snapshot['journal_id']:
            return _('Configure an invoice journal on the monthly service.')
        if not snapshot['payment_mode_id']:
            return _('Configure a payment mode on the monthly service.')
        charges = (
            self.env['afa.service.charge']
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ('subscription_id', '=', subscription.id),
                    ('month', '=', self.month),
                ]
            )
        )
        if charges.filtered('active'):
            return _('Already invoiced.')
        if charges:
            existing_moves = charges.mapped('invoice_id') | charges.mapped('sponsor_invoice_id')
            if existing_moves.filtered(lambda invoice: invoice.state != 'cancel'):
                return _(
                    'Cancel all family and sponsor invoices for this charge before '
                    'billing it again.'
                )
        if snapshot['sponsor_price'] and not snapshot['sponsor_id']:
            return _('Configure a sponsor for the extracurricular scholarship.')
        if snapshot['sponsor_price'] and snapshot['sponsor_id'] == snapshot['payer_id']:
            return _('The sponsor and family billing guardian must be different contacts.')
        for allocation in self._invoice_allocations(snapshot):
            payer = self.env['res.partner'].browse(allocation['payer_id'])
            payment_mode = self.env['account.payment.mode'].browse(allocation['payment_mode_id'])
            group_invoices = self._invoices_for_group(
                subscription.family_id,
                subscription.service_id.invoice_journal_id,
                payment_mode,
            )
            if any(invoice.partner_id != payer for invoice in group_invoices):
                return _('An existing service invoice for this family has a different payer.')
            invoice = self._existing_invoice(
                subscription.family_id,
                payer,
                subscription.service_id.invoice_journal_id,
                payment_mode,
            )
            if invoice and invoice.state != 'draft':
                return _(
                    'The invoice to %s is already posted; cancel it before billing new services.'
                ) % (payer.display_name)
            if invoice and invoice.company_id != subscription.service_id.company_id:
                return _('The existing invoice belongs to a different company.')
        return False

    def action_preview(self):
        self.ensure_one()
        self._check_access()
        self.line_ids.unlink()
        for subscription in self._candidates():
            snapshot = self._snapshot(subscription)
            reason = self._reason(subscription, snapshot)
            values = self._line_snapshot_values(snapshot)
            values.update(
                {
                    'wizard_id': self.id,
                    'subscription_id': subscription.id,
                    'month': self.month,
                    'include': not bool(reason),
                    'reason': reason,
                }
            )
            self.env['afa.service.billing.line'].create(self._billing_line_values(values, snapshot))
        return self._action()

    def _billing_line_values(self, values, snapshot):
        """Allow service-specific modules to add fields to the billing preview."""
        return values

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

        family_ids = sorted(set(selected.mapped('family_id').ids))
        student_ids = sorted(set(selected.mapped('student_id').ids))
        for family_id in family_ids:
            self.env.cr.execute('SELECT id FROM afa_family WHERE id = %s FOR UPDATE', [family_id])
        for student_id in student_ids:
            self.env['afa.service.subscription']._lock_student(
                self.env['res.partner'].browse(student_id)
            )
        self.env.invalidate_all()
        if set(self.line_ids.mapped('subscription_id').ids) != set(self._candidates().ids):
            raise ValidationError(_('Subscriptions changed; refresh the preview.'))

        prepared = self._prepare_selected_lines(selected)
        grouped_lines = self._group_invoice_allocations(prepared)
        invoice_lines_by_subscription = {}
        invoice_ids = {
            self._generate_invoice_group(key, entries, invoice_lines_by_subscription)
            for key, entries in sorted(
                grouped_lines.items(), key=lambda item: tuple(value or 0 for value in item[0])
            )
        }
        self._create_charge_snapshots(prepared, invoice_lines_by_subscription)
        self.action_preview()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Monthly Service Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', sorted(invoice_ids))],
        }

    def _prepare_selected_lines(self, selected):
        prepared = []
        for line in selected:
            subscription = line.subscription_id
            snapshot = self._snapshot(subscription)
            if self._reason(subscription, snapshot) or not self._snapshot_matches_line(
                line, snapshot
            ):
                raise ValidationError(_('Billing details changed; refresh the preview.'))
            prepared.append((line, subscription, snapshot))
        return prepared

    def _group_invoice_allocations(self, prepared):
        grouped_lines = {}
        for line, subscription, snapshot in prepared:
            for allocation in self._invoice_allocations(snapshot):
                key = (
                    snapshot['family_id'],
                    allocation['payer_id'],
                    snapshot['journal_id'],
                    allocation['payment_mode_id'] or False,
                )
                grouped_lines.setdefault(key, []).append((line, subscription, snapshot, allocation))
        return grouped_lines

    def _generate_invoice_group(self, key, entries, invoice_lines_by_subscription):
        family_id, payer_id, journal_id, payment_mode_id = key
        family = self.env['afa.family'].browse(family_id)
        payer = self.env['res.partner'].browse(payer_id)
        journal = self.env['account.journal'].browse(journal_id)
        payment_mode = self.env['account.payment.mode'].browse(payment_mode_id)
        lines = self.env['afa.service.billing.line'].browse([entry[0].id for entry in entries])
        companies = lines.mapped('subscription_id.service_id.company_id')
        if len(set(companies.ids)) != 1:
            raise ValidationError(_('A family cannot be billed across companies on one invoice.'))
        company = companies[0]
        if journal.company_id != company or (payment_mode and payment_mode.company_id != company):
            raise ValidationError(
                _('Invoice journal and payment mode must match the service company.')
            )
        invoice = self._existing_invoice(family, payer, journal, payment_mode)
        if invoice and invoice.state != 'draft':
            raise ValidationError(
                _('The invoice to %s is already posted; cancel it before billing new services.')
                % payer.display_name
            )
        if not invoice:
            invoice = (
                self.env['account.move']
                .with_context(_afa_generate_service_invoices=True)
                .create(
                    {
                        'move_type': 'out_invoice',
                        'partner_id': payer.id,
                        'company_id': company.id,
                        'journal_id': journal.id,
                        'payment_mode_id': payment_mode.id or False,
                        'invoice_date': self.month,
                        'afa_service_month': self.month,
                        'afa_service_family_id': family.id,
                    }
                )
            )
        for _line, subscription, _snapshot, allocation in entries:
            invoice_line = self.env['account.move.line'].create(
                {
                    'move_id': invoice.id,
                    'product_id': subscription.service_id.product_id.id,
                    'name': self._invoice_line_name(subscription, allocation),
                    'quantity': 1,
                    'price_unit': allocation['amount'],
                }
            )
            invoice_lines_by_subscription.setdefault(subscription.id, {})[allocation['role']] = (
                invoice_line.id
            )
        return invoice.id

    def _create_charge_snapshots(self, prepared, invoice_lines_by_subscription):
        for _line, subscription, snapshot in prepared:
            charge_values = self._charge_snapshot_values(snapshot)
            invoice_lines = invoice_lines_by_subscription.get(subscription.id, {})
            charge_values.update(
                {
                    'subscription_id': subscription.id,
                    'month': self.month,
                    'invoice_line_id': invoice_lines.get('family'),
                    'sponsor_invoice_line_id': invoice_lines.get('sponsor'),
                    'family_id': snapshot['family_id'],
                    'payer_id': snapshot['payer_id'],
                    'currency_id': subscription.service_id.currency_id.id,
                }
            )
            self.env['afa.service.charge'].sudo().with_context(
                _afa_generate_service_invoices=True
            ).create(charge_values)

    def _invoice_line_name(self, subscription, allocation):
        name = _('%s — %s — %s') % (
            subscription.service_id.name,
            subscription.student_id.name,
            self.month,
        )
        if allocation['role'] == 'sponsor':
            return _('%s — Scholarship Share') % name
        return name

    def _action(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
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
    price = fields.Monetary(string='Tariff Price', readonly=True, currency_field='currency_id')
    family_price = fields.Monetary(readonly=True, currency_field='currency_id')
    sponsor_id = fields.Many2one('res.partner', readonly=True)
    sponsor_price = fields.Monetary(readonly=True, currency_field='currency_id')
    subsidy_percent = fields.Float(readonly=True, digits=(5, 2))
    tariff_basis = fields.Selection(
        [('membership', 'Membership-based tariff'), ('member', 'Member tariff')], readonly=True
    )
    currency_id = fields.Many2one(related='subscription_id.service_id.currency_id')
    journal_id = fields.Many2one('account.journal', readonly=True)
    payment_mode_id = fields.Many2one('account.payment.mode', readonly=True)
    include = fields.Boolean()
    reason = fields.Char(readonly=True)
