from odoo import fields, models


class HrLeaveMandatoryDay(models.Model):
    _inherit = 'hr.leave.mandatory.day'

    school_year_id = fields.Many2one(
        'afa.membership.period',
        string='School Year',
        ondelete='cascade',
        index=True,
        help='School year that generated this mandatory day. Keep it empty for '
        'manually created mandatory days.',
    )
    school_leave_id = fields.Many2one(
        'resource.calendar.leaves',
        string='School Calendar Day',
        ondelete='cascade',
        index=True,
        readonly=True,
        help='Company-wide closure this mandatory day was mirrored from. '
        'Deleting the closure deletes this day with it.',
    )
