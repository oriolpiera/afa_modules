from odoo import _, models
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
