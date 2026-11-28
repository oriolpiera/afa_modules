from pytz import timezone, utc

from odoo import api, fields, models

MANDATORY_DAY_COLOR = 11  # Calendar palette index for school closures.


class ResourceCalendarLeaves(models.Model):
    _inherit = 'resource.calendar.leaves'

    school_year_id = fields.Many2one(
        'afa.membership.period',
        string='School Year',
        ondelete='cascade',
        index=True,
        help='School year that generated this time off. Keep it empty for '
        'manually created days, such as school elective holidays.',
    )
    afa_category = fields.Selection(
        [
            ('generated', 'Non-Teaching Period'),
            ('school_elective', 'School Elective Holiday'),
            ('state_holiday', 'State Public Holiday'),
            ('regional_holiday', 'Autonomous Community Holiday'),
            ('local_holiday', 'Municipal Holiday'),
            ('other', 'Other'),
        ],
        string='Category',
        default='other',
        required=True,
        help='Why the school is closed. Generated periods are replaced by '
        'regeneration; manual categories are never touched by it.',
    )

    def _afa_pairable(self):
        # Company-wide closures linked to a Time Off request belong to the
        # leave workflow; only standalone closures are school calendar days.
        return self.filtered(
            lambda leave: (
                not leave.resource_id and not leave.holiday_id and leave.time_type == 'leave'
            )
        )

    def _afa_day_range(self):
        """Local school dates covered by this leave's UTC datetimes."""
        self.ensure_one()
        tz_name = self.env.company.resource_calendar_id.tz or 'UTC'
        tz = timezone(tz_name)
        start = utc.localize(self.date_from).astimezone(tz)
        end = utc.localize(self.date_to).astimezone(tz)
        return start.date(), end.date()

    def _afa_synchronize_mandatory_days(self):
        day_model = self.env['hr.leave.mandatory.day']
        for leave in self._afa_pairable():
            start, end = leave._afa_day_range()
            day = day_model.search([('school_leave_id', '=', leave.id)], limit=1)
            values = {
                'name': leave.name,
                'company_id': leave.company_id.id or self.env.company.id,
                'start_date': start,
                'end_date': end,
                'school_year_id': leave.school_year_id.id,
                'color': MANDATORY_DAY_COLOR,
            }
            if day:
                day.write(values)
            else:
                day_model.create(dict(values, school_leave_id=leave.id))

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        leaves._afa_synchronize_mandatory_days()
        return leaves

    def write(self, vals):
        result = super().write(vals)
        if {'name', 'date_from', 'date_to', 'time_type', 'company_id'} & set(vals):
            self._afa_synchronize_mandatory_days()
        return result
