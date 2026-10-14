from itertools import pairwise

from odoo import _, fields, models
from odoo.exceptions import AccessError, ValidationError

STAGES = (
    ('infantil', ('i3', 'i4', 'i5')),
    ('primaria', ('1r', '2n', '3r', '4t', '5è', '6è')),
    ('secundaria', ('1r ESO', '2n ESO', '3r ESO', '4t ESO')),
)


class AfaSchoolCourseSetupWizard(models.TransientModel):
    _name = 'afa.school.course.setup.wizard'
    _description = 'Quick School Course Setup'

    infantil = fields.Boolean(string='Preschool (i3, i4, i5)')
    primaria = fields.Boolean(string='Primary (1r to 6è)')
    secundaria = fields.Boolean(string='Secondary (1r ESO to 4t ESO)')

    def _check_manager(self):
        if not self.env.su and not self.env.user.has_group('afa_family.group_family_manager'):
            raise AccessError(_('Only family managers can set up courses.'))

    def _names(self):
        self.ensure_one()
        return [name for stage, names in STAGES if self[stage] for name in names]

    def _free_sequence(self, lower, upper, used):
        candidate = 1 if lower is None else lower + 1
        while upper is None or candidate < upper:
            if candidate not in used:
                used.add(candidate)
                return candidate
            candidate += 1
        if lower is not None:
            raise ValidationError(
                _(
                    'No free course sequence between %(lower)s and %(upper)s. '
                    'Adjust the existing course sequences first.'
                )
                % {'lower': lower, 'upper': upper}
            )
        # The ladder has to start below the usual numbering: fit under an existing course.
        candidate = upper - 1
        while candidate in used:
            candidate -= 1
        used.add(candidate)
        return candidate

    def _ladder(self, names, existing, used):
        Course = self.env['afa.school.course']
        ladder = []
        lower = None
        for index, name in enumerate(names):
            course = existing.get(name)
            next_index = next(
                (
                    position
                    for position in range(index + 1, len(names))
                    if names[position] in existing
                ),
                None,
            )
            upper = existing[names[next_index]].sequence if next_index is not None else None
            if course:
                if (lower is not None and course.sequence <= lower) or (
                    upper is not None and course.sequence >= upper
                ):
                    raise ValidationError(
                        _(
                            'Course %(course)s has sequence %(sequence)s, which does not fit '
                            'the ladder order. Adjust the existing course sequences first.'
                        )
                        % {'course': name, 'sequence': course.sequence}
                    )
            else:
                course = Course.create(
                    {'name': name, 'sequence': self._free_sequence(lower, upper, used)}
                )
                existing[name] = course
            ladder.append(course)
            lower = course.sequence
        return ladder

    def _link(self, ladder):
        Course = self.env['afa.school.course']
        for course, successor in pairwise(ladder):
            if course.next_course_id:
                if course.next_course_id != successor:
                    raise ValidationError(
                        _('Course %(course)s already continues to %(next)s.')
                        % {'course': course.name, 'next': course.next_course_id.name}
                    )
                continue
            if Course.search_count([('next_course_id', '=', successor.id)]):
                raise ValidationError(
                    _(
                        'Course %(course)s cannot continue to %(next)s: %(next)s already has '
                        'a predecessor.'
                    )
                    % {'course': course.name, 'next': successor.name}
                )
            course.next_course_id = successor

    def action_confirm(self):
        self.ensure_one()
        self._check_manager()
        names = self._names()
        if not names:
            raise ValidationError(_('Select at least one school stage.'))
        courses = self.env['afa.school.course'].search([])
        existing = {course.name: course for course in courses}
        used = set(courses.mapped('sequence'))
        self._link(self._ladder(names, existing, used))
        try:
            self.env['afa.school.course'].search([])._check_single_ladder()
        except ValidationError as error:
            raise ValidationError(
                _(
                    'The selected stages leave the school courses in more than one ladder. '
                    'Also select the stages that continue the existing courses, or link '
                    'them by hand.'
                )
            ) from error
        return self.env['ir.actions.actions']._for_xml_id(
            'afa_school_course.action_afa_school_course'
        )
