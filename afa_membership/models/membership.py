from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Membership(models.Model):
    _name = 'afa.membership'
    _description = 'AFA Family Period Link'

    family_id = fields.Many2one('afa.family', required=True, ondelete='restrict', index=True)
    period_id = fields.Many2one('afa.membership.period', required=True, ondelete='restrict')
    active = fields.Boolean(default=True)

    def init(self):
        # The ORM overlap check gives a readable error; the index also protects
        # concurrent transactions that cannot see each other's uncommitted links.
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_membership_active_family_period_uniq '
            'ON afa_membership (family_id, period_id) WHERE active'
        )

    @api.model_create_multi
    def create(self, vals_list):
        try:
            with self.env.cr.savepoint():
                return super().create(vals_list)
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_membership_active_family_period_uniq':
                raise
            raise ValidationError(
                _('A family can have only one active link per school year.')
            ) from error

    def write(self, vals):
        try:
            with self.env.cr.savepoint():
                result = super().write(vals)
                self.flush_recordset(['family_id', 'period_id', 'active'])
                return result
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_membership_active_family_period_uniq':
                raise
            raise ValidationError(
                _('A family can have only one active link per school year.')
            ) from error

    @api.constrains('family_id', 'period_id', 'active')
    def _check_active_overlap(self):
        for link in self:
            if not link.active or not link.family_id or not link.period_id:
                continue
            period = link.period_id
            other_periods = self.env['afa.membership.period'].search(
                [
                    ('date_start', '<=', period.date_end),
                    ('date_end', '>=', period.date_start),
                ]
            )
            if self.search_count(
                [
                    ('id', '!=', link.id),
                    ('family_id', '=', link.family_id.id),
                    ('period_id', 'in', other_periods.ids),
                    ('active', '=', True),
                ]
            ):
                raise ValidationError(_('A family can have only one active link per school year.'))
