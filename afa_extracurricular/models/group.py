from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_WEEKDAY_SHORT = {
    '1': 'Mon',
    '2': 'Tue',
    '3': 'Wed',
    '4': 'Thu',
    '5': 'Fri',
    '6': 'Sat',
    '7': 'Sun',
}


def _format_hour(value):
    hours = int(value)
    minutes = round((value - hours) * 60)
    return f'{hours:02d}:{minutes:02d}'


class AfaServiceGroup(models.Model):
    _name = 'afa.service.group'
    _description = 'AFA Extracurricular Group'
    _order = 'name, id'

    service_id = fields.Many2one(
        'afa.service',
        required=True,
        index=True,
        ondelete='cascade',
        domain=[('is_extracurricular', '=', True)],
        string='Activity',
    )
    name = fields.Char(required=True)
    capacity = fields.Integer(
        string='Places',
        default=0,
        help='Informational seat limit; enrollments are never blocked by it.',
    )
    enrolled_count = fields.Integer(
        compute='_compute_enrolled_count',
        string='Enrolled',
        groups='afa_family.group_family_manager',
    )
    schedule_ids = fields.One2many(
        'afa.service.group.schedule', 'group_id', string='Weekly Schedule'
    )
    subscription_ids = fields.One2many('afa.service.subscription', 'group_id', string='Enrollments')
    schedule_summary = fields.Char(compute='_compute_schedule_summary')

    def init(self):
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_service_group_service_name_uniq '
            'ON afa_service_group (service_id, name)'
        )

    @api.model_create_multi
    def create(self, vals_list):
        try:
            with self.env.cr.savepoint():
                return super().create(vals_list)
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_service_group_service_name_uniq':
                raise
            raise ValidationError(_('Group names must be unique within an activity.')) from error

    def write(self, vals):
        if 'service_id' in vals and self.env['afa.service.subscription'].search_count(
            [('group_id', 'in', self.ids)]
        ):
            raise ValidationError(_('A group with enrollments cannot move to another activity.'))
        try:
            with self.env.cr.savepoint():
                result = super().write(vals)
                if 'name' in vals or 'service_id' in vals:
                    self.flush_recordset(['name', 'service_id'])
                return result
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_service_group_service_name_uniq':
                raise
            raise ValidationError(_('Group names must be unique within an activity.')) from error

    def unlink(self):
        if self.env['afa.service.subscription'].search_count([('group_id', 'in', self.ids)]):
            raise ValidationError(_('A group with enrollment history cannot be deleted.'))
        return super().unlink()

    @api.constrains('name', 'service_id', 'capacity')
    def _check_group(self):
        for group in self:
            if not group.service_id.is_extracurricular:
                raise ValidationError(_('Only extracurricular activities have groups.'))
            if group.capacity < 0:
                raise ValidationError(_('Group places cannot be negative.'))
            if self.search_count(
                [
                    ('id', '!=', group.id),
                    ('service_id', '=', group.service_id.id),
                    ('name', '=', group.name),
                ]
            ):
                raise ValidationError(_('Group names must be unique within an activity.'))

    def _compute_enrolled_count(self):
        today = fields.Date.context_today(self)
        counts = dict.fromkeys(self.ids, 0)
        for subscription in self.env['afa.service.subscription'].search(
            [('group_id', 'in', self.ids)]
        ):
            service_end = subscription.service_id.date_end
            if (
                subscription.start_month <= today
                and (not subscription.end_month or subscription.end_month > today)
                and (not service_end or service_end >= today)
            ):
                counts[subscription.group_id.id] += 1
        for group in self:
            group.enrolled_count = counts.get(group.id, 0)

    def _compute_schedule_summary(self):
        for group in self:
            parts = []
            for slot in group.schedule_ids:
                parts.append(
                    f'{_WEEKDAY_SHORT[slot.weekday]} '
                    f'{_format_hour(slot.hour_from)}-{_format_hour(slot.hour_to)}'
                )
            group.schedule_summary = ', '.join(parts)
