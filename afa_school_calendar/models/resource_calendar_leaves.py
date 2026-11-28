from odoo import fields, models


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
