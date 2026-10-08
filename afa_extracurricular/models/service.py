from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaService(models.Model):
    _inherit = 'afa.service'

    is_extracurricular = fields.Boolean(
        string='Extracurricular Activity',
        help='Charges the same family monthly fee once per activity; choose groups for enrollment.',
    )
    enrollment_date_start = fields.Date(
        string='Enrollment Information From',
        help='Informative registration window for families; it never blocks a staff enrollment.',
    )
    enrollment_date_end = fields.Date(
        string='Enrollment Information Through',
        help='Informative registration window for families; it never blocks a staff enrollment.',
    )
    group_ids = fields.One2many('afa.service.group', 'service_id', string='Groups')
    enrollment_count = fields.Integer(compute='_compute_enrollment_count')

    def write(self, vals):
        if 'is_extracurricular' in vals and self.env['afa.service.subscription'].search_count(
            [('service_id', 'in', self.ids)]
        ):
            raise ValidationError(
                _('A service with subscriptions cannot change its extracurricular type.')
            )
        return super().write(vals)

    @api.constrains('is_extracurricular', 'enrollment_date_start', 'enrollment_date_end')
    def _check_extracurricular_configuration(self):
        for service in self:
            if service.is_extracurricular:
                if not (service.enrollment_date_start and service.enrollment_date_end):
                    raise ValidationError(
                        _('Extracurriculars need an informative enrollment period.')
                    )
                if service.enrollment_date_start > service.enrollment_date_end:
                    raise ValidationError(_('The informative enrollment period is reversed.'))
            elif service.enrollment_date_start or service.enrollment_date_end:
                raise ValidationError(
                    _('Only extracurricular activities have an informative enrollment period.')
                )

    def _compute_enrollment_count(self):
        for service in self:
            service.enrollment_count = len(service.subscription_ids)

    def action_open_enrollments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Enrollments'),
            'res_model': 'afa.service.subscription',
            'view_mode': 'list,form',
            'views': [
                (
                    self.env.ref(
                        'afa_extracurricular.view_afa_subscription_extracurricular_list'
                    ).id,
                    'list',
                ),
                (
                    self.env.ref('afa_service_subscription.view_afa_service_subscription_form').id,
                    'form',
                ),
            ],
            'domain': [('service_id', '=', self.id)],
            'context': {'default_service_id': self.id},
        }
