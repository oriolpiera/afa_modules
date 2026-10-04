from odoo import _, api, models
from odoo.exceptions import ValidationError


class AfaServiceSubscription(models.Model):
    _inherit = 'afa.service.subscription'

    @api.model_create_multi
    def create(self, vals_list):
        return super(AfaServiceSubscription, self.with_context(_afa_school_enrolling=True)).create(
            vals_list
        )

    @api.model
    def _lock_student(self, student):
        super()._lock_student(student)
        if self.env.context.get('_afa_school_enrolling'):
            student.invalidate_recordset(['active'])
            if not student.active:
                raise ValidationError(_('Archived students cannot enroll in services.'))
