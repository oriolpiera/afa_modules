from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaSchoolCourse(models.Model):
    _name = 'afa.school.course'
    _description = 'AFA School Course'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(required=True)
    next_course_id = fields.Many2one('afa.school.course', string='Next Course', ondelete='restrict')

    def init(self):
        for field in ('name', 'sequence', 'next_course_id'):
            self.env.cr.execute(
                f'CREATE UNIQUE INDEX IF NOT EXISTS afa_school_course_{field}_uniq '
                f'ON afa_school_course ({field})'
            )

    @api.model_create_multi
    def create(self, vals_list):
        try:
            with self.env.cr.savepoint():
                return super().create(vals_list)
        except IntegrityError as error:
            if error.diag.constraint_name not in {
                'afa_school_course_name_uniq',
                'afa_school_course_sequence_uniq',
                'afa_school_course_next_course_id_uniq',
            }:
                raise
            raise ValidationError(
                _('Course names, sequences and successors must be unique.')
            ) from error

    def write(self, vals):
        try:
            with self.env.cr.savepoint():
                result = super().write(vals)
                self.flush_recordset(['name', 'sequence', 'next_course_id'])
                return result
        except IntegrityError as error:
            if error.diag.constraint_name not in {
                'afa_school_course_name_uniq',
                'afa_school_course_sequence_uniq',
                'afa_school_course_next_course_id_uniq',
            }:
                raise
            raise ValidationError(
                _('Course names, sequences and successors must be unique.')
            ) from error

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
            if (
                course.next_course_id
                and self.search_count([('next_course_id', '=', course.next_course_id.id)]) > 1
            ):
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
