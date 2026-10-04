from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaSchoolCourse(models.Model):
    _name = 'afa.school.course'
    _description = 'AFA School Course'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(required=True)
    next_course_id = fields.Many2one('afa.school.course', string='Next Course', ondelete='restrict')

    @api.constrains('next_course_id', 'sequence')
    def _check_ladder(self):
        for course in self:
            if course.next_course_id and course.next_course_id.sequence <= course.sequence:
                raise ValidationError(_('The next course must have a higher sequence.'))
            if self.search_count(
                [
                    ('next_course_id', '=', course.id),
                    ('sequence', '>=', course.sequence),
                ]
            ):
                raise ValidationError(_('The next course must have a higher sequence.'))
            if self.search_count([('next_course_id', '=', course.id)]) > 1:
                raise ValidationError(_('A course may have only one predecessor.'))

    @api.constrains('name', 'sequence')
    def _check_unique_courses(self):
        for course in self:
            if self.search_count(
                [
                    ('id', '!=', course.id),
                    '|',
                    ('name', '=', course.name),
                    ('sequence', '=', course.sequence),
                ]
            ):
                raise ValidationError(_('Course names and sequence numbers must be unique.'))
