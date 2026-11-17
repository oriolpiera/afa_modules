from odoo import models


def _generated_invoice_ids(action):
    for field, operator, value in action.get('domain', []):
        if field == 'id' and operator == 'in':
            return value
    return []


class AfaServiceBilling(models.TransientModel):
    _inherit = 'afa.service.billing'

    def action_generate(self):
        action = super().action_generate()
        invoice_ids = _generated_invoice_ids(action)
        invoices = self.env['account.move'].browse(invoice_ids).exists()
        self.env['afa.sepa.return.fee'].sudo().invoice_pending_fees(invoices)
        return action


class AfaAcollidaBilling(models.TransientModel):
    _inherit = 'afa.acollida.billing'

    def action_generate(self):
        action = super().action_generate()
        invoice_ids = _generated_invoice_ids(action)
        invoices = self.env['account.move'].browse(invoice_ids).exists()
        self.env['afa.sepa.return.fee'].sudo().invoice_pending_fees(invoices)
        return action
