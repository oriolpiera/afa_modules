from odoo import models


class AfaServiceBilling(models.TransientModel):
    _inherit = 'afa.service.billing'

    def _invoice_group_extra(self, subscription, snapshot):
        service = subscription.service_id
        is_extracurricular = 'is_extracurricular' in service._fields and service.is_extracurricular
        return self._afa_sepa_invoice_group_extra(
            subscription.family_id, service.company_id, is_extracurricular
        )

    def _afa_sepa_invoice_group_extra(self, family, company, is_extracurricular):
        extracurricular_rule = family.sepa_mandate_rule_ids.filtered(
            lambda rule: rule.company_id == company and rule.purpose == 'extracurricular'
        )
        if not extracurricular_rule:
            return ('service',)
        return ('extracurricular' if is_extracurricular else 'service',)
