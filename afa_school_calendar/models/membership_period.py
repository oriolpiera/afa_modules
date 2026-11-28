from datetime import datetime, time, timedelta

from pytz import timezone, utc

from odoo import _, fields, models
from odoo.exceptions import ValidationError

MANDATORY_DAY_COLOR = 11  # Calendar palette index for school closures.


class AfaMembershipPeriod(models.Model):
    _inherit = 'afa.membership.period'

    term_ids = fields.One2many('afa.school.term', 'period_id', string='Terms')
    non_teaching_leave_ids = fields.One2many(
        'resource.calendar.leaves',
        'school_year_id',
        string='Non-Teaching Days',
    )
    mandatory_day_ids = fields.One2many(
        'hr.leave.mandatory.day',
        'school_year_id',
        string='Mandatory Days',
    )
    non_teaching_leave_count = fields.Integer(
        string='Generated Days',
        compute='_compute_non_teaching_leave_count',
    )

    def _compute_non_teaching_leave_count(self):
        for period in self:
            period.non_teaching_leave_count = len(period.non_teaching_leave_ids)

    def _non_teaching_gaps(self):
        """Return the contiguous date ranges without any term in the school year."""
        self.ensure_one()
        gaps = []
        cursor = self.date_start
        for term in self.term_ids.sorted('date_start'):
            if term.date_start > cursor:
                gaps.append((cursor, term.date_start - timedelta(days=1)))
            cursor = max(cursor, term.date_end + timedelta(days=1))
        if cursor <= self.date_end:
            gaps.append((cursor, self.date_end))
        return gaps

    def _local_day_bounds(self, start, end):
        calendar = self.env.company.resource_calendar_id
        tz = timezone(calendar.tz or 'UTC')
        date_from = tz.localize(datetime.combine(start, time.min)).astimezone(utc)
        date_to = tz.localize(datetime.combine(end, time.max)).astimezone(utc)
        return date_from.replace(tzinfo=None), date_to.replace(tzinfo=None)

    def _terms_outside_year(self):
        self.ensure_one()
        return self.term_ids.filtered(
            lambda term: term.date_start < self.date_start or term.date_end > self.date_end
        )

    def _check_terms_within_year(self):
        for period in self:
            outside = period._terms_outside_year()
            if outside:
                raise ValidationError(
                    _('Adjust the terms that no longer fit in the school year: %s')
                    % ', '.join(outside.mapped('name'))
                )

    def write(self, vals):
        result = super().write(vals)
        if 'date_start' in vals or 'date_end' in vals:
            self._check_terms_within_year()
        return result

    def action_generate_non_teaching_days(self):
        self._check_terms_within_year()
        leave_model = self.env['resource.calendar.leaves']
        mandatory_model = self.env['hr.leave.mandatory.day']
        for period in self:
            period.non_teaching_leave_ids.unlink()
            period.mandatory_day_ids.unlink()
            for start, end in period._non_teaching_gaps():
                date_from, date_to = period._local_day_bounds(start, end)
                title = _('Non-Teaching Days (%(start)s to %(end)s)') % {
                    'start': start.strftime('%d/%m/%Y'),
                    'end': end.strftime('%d/%m/%Y'),
                }
                leave_model.create(
                    {
                        'name': title,
                        'school_year_id': period.id,
                        'date_from': date_from,
                        'date_to': date_to,
                        'time_type': 'leave',
                    }
                )
                # Mandatory days are what the Time Off calendar paints; they
                # need a company and an empty schedule to reach every employee.
                mandatory_model.create(
                    {
                        'name': title,
                        'school_year_id': period.id,
                        'company_id': self.env.company.id,
                        'start_date': start,
                        'end_date': end,
                        'color': MANDATORY_DAY_COLOR,
                    }
                )
        return self.action_view_non_teaching_days()

    def action_clear_non_teaching_days(self):
        for period in self:
            period.non_teaching_leave_ids.unlink()
            period.mandatory_day_ids.unlink()
        return True

    def action_view_non_teaching_days(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Non-Teaching Days'),
            'res_model': 'resource.calendar.leaves',
            'view_mode': 'calendar,list,form',
            'domain': [('id', 'in', self.non_teaching_leave_ids.ids)],
        }
