from odoo import _, fields, models
from odoo.exceptions import AccessError, ValidationError


class AfaSchoolPromotionWizard(models.TransientModel):
    _name = 'afa.school.promotion.wizard'
    _description = 'Preview and Confirm School Promotion'

    period_id = fields.Many2one('afa.membership.period', required=True)
    line_ids = fields.One2many('afa.school.promotion.line', 'wizard_id', readonly=True)

    def _check_manager(self):
        if not self.env.su and not self.env.user.has_group('afa_family.group_family_manager'):
            raise AccessError(_('Only family managers can promote students.'))

    def _students(self):
        return self.env['res.partner'].search(
            [('afa_family_role', '=', 'student'), ('active', '=', True)], order='id'
        )

    def _check_ready(self, students):
        today = fields.Date.context_today(self)
        if today < self.period_id.date_end.replace(day=1):
            raise ValidationError(_('Promote a school year during or after its final month.'))
        if self.env['afa.school.promotion'].search_count([('period_id', '=', self.period_id.id)]):
            raise ValidationError(_('This school year has already been promoted.'))
        promoted_later = self.env['afa.school.promotion'].search(
            [('period_id.date_end', '>', self.period_id.date_end)], limit=1
        )
        if promoted_later:
            raise ValidationError(
                _(
                    'School year %(selected)s ends before the already promoted school '
                    'year %(promoted)s. Promote school years in chronological order.'
                )
                % {
                    'selected': self.period_id.name,
                    'promoted': promoted_later.period_id.name,
                }
            )
        courses = self.env['afa.school.course'].search([])
        if courses:
            predecessors = set(courses.mapped('next_course_id').ids)
            roots = courses.filtered(lambda course: course.id not in predecessors)
            if len(roots) != 1:
                raise ValidationError(_('Configure one connected course ladder before promotion.'))
            seen = set()
            course = roots
            while course:
                if course.id in seen:
                    raise ValidationError(_('The course ladder must not contain cycles.'))
                seen.add(course.id)
                course = course.next_course_id
            if len(seen) != len(courses):
                raise ValidationError(_('Configure one connected course ladder before promotion.'))
        missing = students.filtered(lambda student: not student.afa_course_id)
        if missing:
            raise ValidationError(
                _('Assign a course to every active student first: %s')
                % ', '.join(missing.mapped('name'))
            )

    def _action(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_preview(self):
        self.ensure_one()
        self._check_manager()
        students = self._students()
        self._check_ready(students)
        self.line_ids.unlink()
        self.env['afa.school.promotion.line'].create(
            [
                {
                    'wizard_id': self.id,
                    'student_id': student.id,
                    'course_id': student.afa_course_id.id,
                    'next_course_id': student.afa_course_id.next_course_id.id,
                }
                for student in students
            ]
        )
        return self._action()

    def _withdraw_graduates(self, graduates):
        future = self.env['afa.service.subscription'].search(
            [
                ('student_id', 'in', graduates.ids),
                ('service_id.date_start', '>', self.period_id.date_end),
                ('leave_window_id', '=', False),
            ],
            limit=1,
        )
        if future:
            raise ValidationError(
                _(
                    'Student %(student)s has a future subscription to %(service)s. '
                    'Resolve it before graduation.'
                )
                % {'student': future.student_id.name, 'service': future.service_id.name}
            )
        subscriptions = self.env['afa.service.subscription'].search(
            [
                ('student_id', 'in', graduates.ids),
                ('service_id.period_id', '=', self.period_id.id),
                ('leave_window_id', '=', False),
            ]
        )
        today = fields.Date.context_today(self)
        for sub in subscriptions:
            windows = self.env['afa.service.window'].search(
                [
                    ('service_id', '=', sub.service_id.id),
                    ('kind', '=', 'leave'),
                    ('date_start', '<=', today),
                    ('date_end', '>=', today),
                    ('effective_month', '>', sub.start_month),
                ]
            )
            if len(windows) != 1:
                raise ValidationError(
                    _(
                        'Student %(student)s cannot graduate: configure one open withdrawal '
                        'window for %(service)s.'
                    )
                    % {'student': sub.student_id.name, 'service': sub.service_id.name}
                )
            sub.action_leave(windows)

    def action_confirm(self):
        self.ensure_one()
        self._check_manager()
        if not self.line_ids:
            raise ValidationError(_('Preview the students before confirming.'))
        # Serialize confirmations for the same school year, including two first runs.
        self.env.cr.execute(
            'SELECT id FROM afa_membership_period WHERE id = %s FOR UPDATE',
            [self.period_id.id],
        )
        students = self._students()
        self._check_ready(students)
        with self.env.cr.savepoint():
            subscriptions_model = self.env['afa.service.subscription']
            for family in students.mapped('afa_family_id').sorted('id'):
                subscriptions_model._lock_family(family)
            for student in students.sorted('id'):
                subscriptions_model._lock_student(student)
            self.env.invalidate_all()
            students = self._students()
            self._check_ready(students)
            snapshot = {
                line.student_id.id: (line.course_id.id, line.next_course_id.id)
                for line in self.line_ids
            }
            if len(snapshot) != len(self.line_ids) or snapshot != {
                student.id: (student.afa_course_id.id, student.afa_course_id.next_course_id.id)
                for student in students
            }:
                raise ValidationError(_('The student courses changed. Refresh the preview.'))
            graduates = students.filtered(lambda student: not student.afa_course_id.next_course_id)
            self._withdraw_graduates(graduates)
            for student in students - graduates:
                student.write({'afa_course_id': student.afa_course_id.next_course_id.id})
            graduates.write({'active': False})
            self.env['afa.school.promotion'].sudo().create(
                {
                    'period_id': self.period_id.id,
                    'promoted_count': len(students - graduates),
                    'graduated_count': len(graduates),
                }
            )
        return {'type': 'ir.actions.act_window_close'}


class AfaSchoolPromotionLine(models.TransientModel):
    _name = 'afa.school.promotion.line'
    _description = 'School Promotion Preview Line'

    wizard_id = fields.Many2one('afa.school.promotion.wizard', required=True, ondelete='cascade')
    student_id = fields.Many2one('res.partner', readonly=True, required=True)
    course_id = fields.Many2one('afa.school.course', readonly=True)
    next_course_id = fields.Many2one('afa.school.course', readonly=True)
