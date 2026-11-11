from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaSepaMandateRule(models.Model):
    _name = 'afa.sepa.mandate.rule'
    _description = 'AFA Family SEPA Mandate Assignment'
    _order = 'company_id, purpose, id'

    family_id = fields.Many2one('afa.family', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, index=True
    )
    purpose = fields.Selection(
        [
            ('default', 'Default'),
            ('acollida', 'Acollida'),
            ('extracurricular', 'Extracurricular Activities'),
        ],
        required=True,
        default='default',
    )
    mandate_id = fields.Many2one(
        'account.banking.mandate', required=True, ondelete='restrict', check_company=True
    )

    def init(self):
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_sepa_mandate_rule_unique '
            'ON afa_sepa_mandate_rule (family_id, company_id, purpose)'
        )

    @api.constrains('family_id', 'company_id', 'mandate_id')
    def _check_mandate_owner(self):
        for rule in self:
            mandate = rule.mandate_id
            if (
                mandate.partner_id != rule.family_id.billing_partner_id
                or mandate.company_id != rule.company_id
                or mandate.partner_bank_id.partner_id != rule.family_id.billing_partner_id
                or mandate.partner_bank_id.acc_type != 'iban'
                or mandate.format != 'sepa'
                or mandate.scheme != 'CORE'
            ):
                raise ValidationError(
                    _('The assigned mandate must be a SEPA Core IBAN mandate for the family payer.')
                )
