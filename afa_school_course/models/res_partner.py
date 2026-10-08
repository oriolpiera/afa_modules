from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    afa_course_id = fields.Many2one(
        'afa.school.course',
        string='School Course',
        ondelete='restrict',
        groups='afa_family.group_family_manager',
    )

    @api.constrains('afa_course_id', 'afa_family_role')
    def _check_student_course(self):
        for partner in self:
            if partner.afa_course_id and partner.afa_family_role != 'student':
                raise ValidationError(_('Only students may have a school course.'))

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get('afa_course_id') for vals in vals_list) and not self._can_manage_family():
            raise AccessError(_('Only family managers may assign school courses.'))
        return super().create(vals_list)

    def write(self, vals):
        if 'afa_course_id' in vals and not self._can_manage_family():
            raise AccessError(_('Only family managers may assign school courses.'))
        return super().write(vals)
