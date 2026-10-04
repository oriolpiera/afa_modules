from datetime import date

from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MembershipPeriod(models.Model):
    _name = 'afa.membership.period'
    _description = 'AFA School Year'

    name = fields.Char(required=True)
    date_start = fields.Date(required=True, index=True)
    date_end = fields.Date(required=True, index=True)

    def init(self):
        # Valid school years cannot overlap unless they share the same July 1.
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_membership_period_date_start_uniq '
            'ON afa_membership_period (date_start)'
        )

    @api.model_create_multi
    def create(self, vals_list):
        try:
            with self.env.cr.savepoint():
                return super().create(vals_list)
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_membership_period_date_start_uniq':
                raise
            raise ValidationError(_('A school year with this July 1 already exists.')) from error

    def write(self, vals):
        try:
            with self.env.cr.savepoint():
                result = super().write(vals)
                self.flush_recordset(['date_start', 'date_end'])
                return result
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_membership_period_date_start_uniq':
                raise
            raise ValidationError(_('A school year with this July 1 already exists.')) from error

    @api.constrains('date_start', 'date_end')
    def _check_school_year(self):
        for period in self:
            start = period.date_start
            end = period.date_end
            if not start or not end:
                continue
            if start.month != 7 or start.day != 1 or end != date(start.year + 1, 6, 30):
                raise ValidationError(_('A school year must run from July 1 to June 30.'))
            if self.search_count(
                [
                    ('id', '!=', period.id),
                    ('date_start', '<=', end),
                    ('date_end', '>=', start),
                ]
            ):
                raise ValidationError(_('School years cannot overlap.'))
