from odoo import fields, models


class AfaSchoolPromotion(models.Model):
    _name = 'afa.school.promotion'
    _description = 'Completed AFA School Promotion'

    period_id = fields.Many2one('afa.membership.period', required=True, ondelete='restrict')
    promoted_count = fields.Integer(readonly=True)
    graduated_count = fields.Integer(readonly=True)
    completed_on = fields.Datetime(default=fields.Datetime.now, readonly=True)

    def init(self):
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_school_promotion_period_uniq '
            'ON afa_school_promotion (period_id)'
        )
