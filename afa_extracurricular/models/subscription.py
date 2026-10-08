from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaServiceSubscription(models.Model):
    _inherit = 'afa.service.subscription'

    group_id = fields.Many2one(
        'afa.service.group',
        string='Group',
        ondelete='restrict',
        copy=False,
        domain="[('service_id', '=', service_id)]",
        help='Group of an extracurricular activity; empty for non-extracurricular services.',
    )
    is_extracurricular = fields.Boolean(related='service_id.is_extracurricular')

    @api.constrains('group_id', 'service_id')
    def _check_group_assignment(self):
        for subscription in self:
            service = subscription.service_id
            if service and not service.is_extracurricular and subscription.group_id:
                raise ValidationError(_('Only extracurricular enrollments have a group.'))
            if service and service.is_extracurricular and not subscription.group_id:
                raise ValidationError(_('Choose a group for an extracurricular enrollment.'))
            if subscription.group_id and subscription.group_id.service_id != service:
                raise ValidationError(_('The group belongs to another activity.'))
