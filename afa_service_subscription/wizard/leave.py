from odoo import fields, models


class AfaServiceLeave(models.TransientModel):
    _name = 'afa.service.leave'
    _description = 'Request AFA Service Withdrawal'

    subscription_id = fields.Many2one('afa.service.subscription', required=True, readonly=True)
    window_id = fields.Many2one(
        'afa.service.window',
        required=True,
        domain="[('service_id', '=', service_id), ('kind', '=', 'leave')]",
    )
    service_id = fields.Many2one(related='subscription_id.service_id')

    def action_confirm(self):
        self.ensure_one()
        self.subscription_id.action_leave(self.window_id)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'afa.service.subscription',
            'res_id': self.subscription_id.id,
            'view_mode': 'form',
        }
