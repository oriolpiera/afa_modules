from odoo import _, fields, models
from odoo.exceptions import AccessError


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _afa_sepa_mandate_purposes(self):
        self.ensure_one()
        purposes = set()

        has_acollida_sources = self._afa_sepa_has_acollida_charges()
        if has_acollida_sources:
            purposes.add('acollida')

        billing_type = self.afa_service_billing_type
        if billing_type == 'acollida':
            purposes.add('acollida')
        elif billing_type == 'extracurricular':
            purposes.add('extracurricular')

        has_service_sources = False
        if 'afa_service_charge_ids' in self._fields and self.afa_service_charge_ids:
            has_service_sources = True
            service_charges = self.afa_service_charge_ids
            extracurricular_charges = service_charges.filtered(
                lambda charge: (
                    'is_extracurricular' in charge.subscription_id.service_id._fields
                    and charge.subscription_id.service_id.is_extracurricular
                )
            )
            if extracurricular_charges:
                purposes.add('extracurricular')
            if len(extracurricular_charges) != len(service_charges):
                purposes.add('default')

        if billing_type == 'service' and not has_service_sources and not has_acollida_sources:
            purposes.add('default')
        return purposes or {'default'}

    def _afa_sepa_has_acollida_charges(self):
        self.ensure_one()
        return bool('afa_acollida_charge_ids' in self._fields and self.afa_acollida_charge_ids)

    def _afa_sepa_resolve_collection_mandate(self):
        self.ensure_one()

        def usable(mandate):
            return (
                mandate.partner_id == self.partner_id
                and mandate.company_id == self.company_id
                and mandate.state == 'valid'
                and mandate.format == 'sepa'
                and mandate.scheme == 'CORE'
                and mandate.signature_date
                and mandate.signature_date <= fields.Date.context_today(self)
                and mandate.partner_bank_id.partner_id == self.partner_id
                and mandate.partner_bank_id.acc_type == 'iban'
                and not (mandate.type == 'oneoff' and mandate.last_debit_date)
            )

        mandates = self.env['account.banking.mandate'].search(
            [
                ('partner_id', '=', self.partner_id.id),
                ('company_id', '=', self.company_id.id),
                ('state', '=', 'valid'),
            ]
        )
        usable_mandates = mandates.filtered(usable)
        family = self.afa_membership_id.family_id or self.partner_id.afa_family_id
        family_rules = family.sepa_mandate_rule_ids.filtered(
            lambda rule: rule.company_id == self.company_id
        )
        selected = self.env['account.banking.mandate']

        for purpose in self._afa_sepa_mandate_purposes():
            rules = family_rules.filtered(
                lambda rule, current_purpose=purpose: rule.purpose == current_purpose
            )
            if not rules and purpose != 'default':
                rules = family_rules.filtered(lambda rule: rule.purpose == 'default')
            if rules:
                mandate = rules.mandate_id
                if mandate not in usable_mandates:
                    return self.env['account.banking.mandate'], _(
                        'The assigned SEPA mandate for this billing type is no longer valid.'
                    )
            elif len(usable_mandates) == 1 and not family_rules:
                mandate = usable_mandates
            elif usable_mandates:
                linked = self.mandate_id.filtered(usable)
                if linked and not family_rules:
                    mandate = linked[:1]
                    selected |= mandate
                    continue
                if len(usable_mandates) == 1:
                    return self.env['account.banking.mandate'], _(
                        'No default SEPA mandate is assigned for this billing type.'
                    )
                return self.env['account.banking.mandate'], _(
                    'Multiple valid SEPA mandates exist; configure a default and any '
                    'service-specific assignments.'
                )
            else:
                return self.env['account.banking.mandate'], _(
                    'No valid SEPA Core mandate with an IBAN owned by the invoice payer.'
                )
            selected |= mandate

        if len(selected) != 1:
            return self.env['account.banking.mandate'], _(
                'This invoice includes billing types assigned to different SEPA mandates; '
                'split the invoice before collection.'
            )
        return selected, False

    def action_open_afa_sepa_lines(self):
        self.ensure_one()
        if not self.env.user.has_group('afa_family.group_family_manager') or not (
            self.env.user.has_group('account_payment_order.group_account_payment')
        ):
            raise AccessError(_('AFA collections require family and payment-order access.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('AFA Debit Lines'),
            'res_model': 'account.payment.line',
            'view_mode': 'list,form',
            'domain': [('move_line_id.move_id', '=', self.id), ('afa_family_id', '!=', False)],
            'context': {'list_view_ref': 'afa_sepa.view_afa_sepa_line_list'},
        }
