from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaSchoolTerm(models.Model):
    _name = 'afa.school.term'
    _description = 'Afa School Term'
    _order = 'period_id, date_start, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    period_id = fields.Many2one(
        'afa.membership.period',
        string='School Year',
        required=True,
        ondelete='cascade',
        index=True,
    )

    @api.constrains('date_start', 'date_end')
    def _check_date_range(self):
        for term in self:
            if term.date_start > term.date_end:
                raise ValidationError(_('A term must start on or before its end date.'))

    @api.constrains('period_id', 'date_start', 'date_end')
    def _check_within_period(self):
        for term in self:
            period = term.period_id
            if term.date_start < period.date_start or term.date_end > period.date_end:
                raise ValidationError(_('Term dates must be inside the school year.'))

    @api.constrains('period_id', 'date_start', 'date_end')
    def _check_no_overlap(self):
        for term in self:
            if term.search_count(
                [
                    ('period_id', '=', term.period_id.id),
                    ('id', '!=', term.id),
                    ('date_start', '<=', term.date_end),
                    ('date_end', '>=', term.date_start),
                ]
            ):
                raise ValidationError(_('Terms inside one school year cannot overlap.'))
