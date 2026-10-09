from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaServiceGroupSchedule(models.Model):
    _name = 'afa.service.group.schedule'
    _description = 'AFA Extracurricular Weekly Schedule'
    _order = 'group_id, weekday'

    group_id = fields.Many2one('afa.service.group', required=True, index=True, ondelete='cascade')
    weekday = fields.Selection(
        [
            ('1', 'Monday'),
            ('2', 'Tuesday'),
            ('3', 'Wednesday'),
            ('4', 'Thursday'),
            ('5', 'Friday'),
            ('6', 'Saturday'),
            ('7', 'Sunday'),
        ],
        required=True,
        string='Day',
    )
    hour_from = fields.Float(required=True, string='From')
    hour_to = fields.Float(required=True, string='To')

    def init(self):
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_service_group_schedule_group_weekday_uniq '
            'ON afa_service_group_schedule (group_id, weekday)'
        )

    @api.model_create_multi
    def create(self, vals_list):
        try:
            with self.env.cr.savepoint():
                return super().create(vals_list)
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_service_group_schedule_group_weekday_uniq':
                raise
            raise ValidationError(_('A group can only have one slot per weekday.')) from error

    def write(self, vals):
        try:
            with self.env.cr.savepoint():
                result = super().write(vals)
                if 'group_id' in vals or 'weekday' in vals:
                    self.flush_recordset(['group_id', 'weekday'])
                return result
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_service_group_schedule_group_weekday_uniq':
                raise
            raise ValidationError(_('A group can only have one slot per weekday.')) from error

    @api.constrains('weekday', 'hour_from', 'hour_to', 'group_id')
    def _check_schedule(self):
        for slot in self:
            if not (0 <= slot.hour_from < slot.hour_to <= 24):
                raise ValidationError(_('Set a valid time range within the day.'))
            if self.search_count(
                [
                    ('id', '!=', slot.id),
                    ('group_id', '=', slot.group_id.id),
                    ('weekday', '=', slot.weekday),
                ]
            ):
                raise ValidationError(_('A group can only have one slot per weekday.'))
