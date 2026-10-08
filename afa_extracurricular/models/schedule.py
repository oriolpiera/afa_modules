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
