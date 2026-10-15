import hashlib
import unicodedata
from collections import defaultdict

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError

from . import csv_format


def _normalize(value):
    text = unicodedata.normalize('NFKD', value or '')
    text = ''.join(char for char in text if not unicodedata.combining(char))
    return ' '.join(text.casefold().split())


class AfaExtracurricularImportWizard(models.TransientModel):
    _name = 'afa.extracurricular.import.wizard'
    _description = 'Extracurricular Enrollment Import'

    file = fields.Binary()
    filename = fields.Char()
    line_ids = fields.One2many('afa.extracurricular.import.line', 'wizard_id', readonly=True)
    preview_checksum = fields.Char(readonly=True, copy=False)
    preview_message = fields.Char(readonly=True, copy=False)

    def _file_checksum(self):
        self.ensure_one()
        content = self.file or b''
        if isinstance(content, str):
            content = content.encode('ascii')
        return hashlib.sha256(content).hexdigest() if content else False

    @api.onchange('file')
    def _onchange_file(self):
        for wizard in self:
            if wizard.preview_checksum and wizard.preview_checksum != wizard._file_checksum():
                wizard.line_ids = [Command.clear()]
                wizard.preview_checksum = False
                wizard.preview_message = _(
                    'The selected CSV changed. Preview it again before confirming.'
                )

    def _check_manager(self):
        if not self.env.su and not self.env.user.has_group('afa_family.group_family_manager'):
            raise AccessError(_('Only family managers can import extracurricular enrollments.'))

    def _action(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_load(self):
        self.ensure_one()
        self._check_manager()
        if not self.file:
            raise UserError(_('Select a CSV file to load.'))
        if self.filename and not self.filename.lower().endswith('.csv'):
            raise UserError(_('Upload a CSV file.'))

        records = csv_format.parse_rows(self.file)
        self.line_ids.unlink()
        self.preview_message = False
        self.env['afa.extracurricular.import.line'].create(
            [
                {
                    'wizard_id': self.id,
                    'sequence': index * 10,
                    'course': record['course'],
                    'student_name': record['student'],
                    'phone': record['phone'],
                    'activity_name': record['activity'],
                    'group_name': record['group'],
                }
                for index, record in enumerate(records, start=1)
            ]
        )
        self.invalidate_recordset(['line_ids'])
        self.preview_checksum = self._file_checksum()
        self._validate_lines()
        return self._action()

    def action_confirm(self):
        self.ensure_one()
        self._check_manager()
        if not self.line_ids:
            if self.preview_message:
                return self._action()
            raise UserError(_('Load a CSV file before confirming.'))

        if not self.preview_checksum or self.preview_checksum != self._file_checksum():
            self.line_ids.unlink()
            self.preview_checksum = False
            self.preview_message = _(
                'The selected CSV changed. Preview it again before confirming.'
            )
            return self._action()

        self._validate_lines()
        if self.line_ids.filtered(lambda line: line.action == 'error'):
            return self._action()

        lines_to_create = self.line_ids.filtered(lambda line: line.action == 'create')
        if not lines_to_create:
            raise UserError(_('There are no new enrollments to import.'))
        self.env['afa.service.subscription'].create(
            [
                {
                    'student_id': line.student_id.id,
                    'service_id': line.service_id.id,
                    'group_id': line.group_id.id,
                    'join_window_id': line.join_window_id.id,
                }
                for line in lines_to_create
            ]
        )
        return {'type': 'ir.actions.act_window_close'}

    def _validate_lines(self):
        lines = self.line_ids.sorted('sequence', 'id')
        if not lines:
            return

        course_by_name = defaultdict(list)
        for course in self.env['afa.school.course'].search([]):
            course_by_name[_normalize(course.name)].append(course)

        candidate_course_ids = {
            course.id for courses in course_by_name.values() for course in courses
        }
        students_by_key = defaultdict(list)
        students = self.env['res.partner'].search(
            [
                ('afa_family_role', '=', 'student'),
                ('afa_course_id', 'in', list(candidate_course_ids)),
            ]
        )
        for student in students:
            students_by_key[(_normalize(student.name), student.afa_course_id.id)].append(student)

        today = fields.Date.context_today(self)
        windows = self.env['afa.service.window'].search(
            [
                ('kind', '=', 'join'),
                ('date_start', '<=', today),
                ('date_end', '>=', today),
                ('service_id.is_extracurricular', '=', True),
            ]
        )
        windows_by_service = defaultdict(list)
        services_by_name = defaultdict(list)
        for window in windows:
            windows_by_service[window.service_id.id].append(window)
            services_by_name[_normalize(window.service_id.name)].append(window.service_id)

        service_ids = {service.id for services in services_by_name.values() for service in services}
        groups_by_key = defaultdict(list)
        for group in self.env['afa.service.group'].search(
            [('service_id', 'in', list(service_ids))]
        ):
            groups_by_key[(group.service_id.id, _normalize(group.name))].append(group)

        student_ids = {student.id for values in students_by_key.values() for student in values}
        subscriptions_by_key = defaultdict(list)
        if student_ids and service_ids:
            for subscription in self.env['afa.service.subscription'].search(
                [
                    ('student_id', 'in', list(student_ids)),
                    ('service_id', 'in', list(service_ids)),
                ]
            ):
                subscriptions_by_key[
                    (subscription.student_id.id, subscription.service_id.id)
                ].append(subscription)

        planned = {}
        for line in lines:
            line.write(
                {
                    'course_id': False,
                    'student_id': False,
                    'service_id': False,
                    'group_id': False,
                    'join_window_id': False,
                    'action': 'error',
                    'error': '',
                }
            )
            error = self._validate_line(
                line,
                course_by_name,
                students_by_key,
                services_by_name,
                windows_by_service,
                groups_by_key,
            )
            if error:
                line.error = error
                continue

            key = (line.student_id.id, line.service_id.id)
            prior_group = planned.get(key)
            if prior_group:
                if prior_group == line.group_id.id:
                    line.action = 'skip'
                    line.error = _('This enrollment is repeated in the CSV.')
                else:
                    line.error = _(
                        'The CSV assigns this student to two groups of the same activity.'
                    )
                continue

            effective_month = line.join_window_id.effective_month
            overlapping = [
                subscription
                for subscription in subscriptions_by_key.get(key, [])
                if not subscription.end_month or subscription.end_month > effective_month
            ]
            if overlapping:
                if all(
                    subscription.group_id == line.group_id
                    and subscription.start_month <= effective_month
                    for subscription in overlapping
                ):
                    line.action = 'skip'
                    line.error = _('The student is already enrolled in this group.')
                    planned[key] = line.group_id.id
                else:
                    line.error = _(
                        'The student already has an enrollment that conflicts with this group '
                        'and start date.'
                    )
                continue

            line.action = 'create'
            planned[key] = line.group_id.id

    def _validate_line(
        self,
        line,
        course_by_name,
        students_by_key,
        services_by_name,
        windows_by_service,
        groups_by_key,
    ):
        missing = [
            label
            for value, label in (
                (line.course, _('course')),
                (line.student_name, _('student name')),
                (line.activity_name, _('activity')),
                (line.group_name, _('group')),
            )
            if not value.strip()
        ]
        if missing:
            return _('Missing required values: %s.') % ', '.join(missing)

        courses = course_by_name.get(_normalize(line.course), [])
        if not courses:
            return _('The school course "%s" does not exist.') % line.course
        if len(courses) > 1:
            return _('The school course "%s" is ambiguous.') % line.course
        course = courses[0]
        line.course_id = course

        matching_students = students_by_key.get((_normalize(line.student_name), course.id), [])
        if not matching_students:
            return _('No student named "%s" was found in course "%s".') % (
                line.student_name,
                line.course,
            )
        if len(matching_students) > 1:
            return _(
                'More than one student named "%s" is in course "%s". '
                'Use a name that identifies the student uniquely.'
            ) % (line.student_name, line.course)
        student = matching_students[0]
        if not student.afa_family_id:
            return _('The student "%s" is not assigned to a family.') % student.name
        line.student_id = student

        services = services_by_name.get(_normalize(line.activity_name), [])
        services = list({service.id: service for service in services}.values())
        if not services:
            return (
                _('No extracurricular activity named "%s" has an open join window.')
                % line.activity_name
            )
        if len(services) > 1:
            return (
                _('More than one extracurricular activity named "%s" has an open join window.')
                % line.activity_name
            )
        service = services[0]
        line.service_id = service
        service_windows = windows_by_service[service.id]
        if len(service_windows) != 1:
            return _('The activity "%s" has more than one open join window.') % service.name
        line.join_window_id = service_windows[0]

        groups = groups_by_key.get((service.id, _normalize(line.group_name)), [])
        if not groups:
            return _('The group "%s" does not exist in activity "%s".') % (
                line.group_name,
                service.name,
            )
        if len(groups) > 1:
            return _('The group "%s" is ambiguous in activity "%s".') % (
                line.group_name,
                service.name,
            )
        line.group_id = groups[0]
        return ''
