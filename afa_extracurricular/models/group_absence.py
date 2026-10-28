from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaServiceGroupAbsence(models.Model):
    _name = 'afa.service.group.absence'
    _description = 'AFA Canceled Extracurricular Session'
    _order = 'session_date desc, id desc'

    group_id = fields.Many2one('afa.service.group', required=True, index=True, ondelete='restrict')
    session_date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    discount_amount = fields.Monetary(
        required=True,
        default=5,
        currency_field='currency_id',
        help='Discount per student enrolled in this group for the canceled session.',
    )
    currency_id = fields.Many2one(related='group_id.service_id.currency_id', readonly=True)

    def init(self):
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_group_absence_group_date_uniq '
            'ON afa_service_group_absence (group_id, session_date)'
        )

    @api.model
    def _lock_groups(self, group_ids):
        for group_id in sorted(set(group_ids)):
            self.env.cr.execute(
                'SELECT id FROM afa_service_group WHERE id = %s FOR UPDATE', [group_id]
            )

    @api.model
    def _check_not_billed(self, group, session_date):
        month = session_date.replace(day=1)
        charges = self.env['afa.service.charge'].sudo().with_context(active_test=False)
        if charges.search_count(
            [
                ('subscription_id.group_id', '=', group.id),
                ('month', '=', month),
            ]
        ):
            raise ValidationError(
                _('Record canceled sessions before generating invoices for that month.')
            )

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access('create')
        group_ids = [vals['group_id'] for vals in vals_list if vals.get('group_id')]
        self._lock_groups(group_ids)
        self.env.invalidate_all()
        try:
            with self.env.cr.savepoint():
                for vals in vals_list:
                    group_id = vals.get('group_id')
                    if not group_id:
                        continue
                    group = self.env['afa.service.group'].browse(group_id)
                    session_date = fields.Date.to_date(
                        vals.get('session_date') or fields.Date.context_today(self)
                    )
                    self._check_not_billed(group, session_date)
                return super().create(vals_list)
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_group_absence_group_date_uniq':
                raise
            raise ValidationError(
                _('A canceled session is already recorded for this group and date.')
            ) from error

    def write(self, vals):
        self.check_access('write')
        if 'group_id' in vals and any(record.group_id.id != vals['group_id'] for record in self):
            raise ValidationError(_('A canceled session cannot be moved to another group.'))
        self._lock_groups(self.mapped('group_id').ids)
        self.env.invalidate_all()
        original_values = [(record.group_id.id, record.session_date) for record in self]

        try:
            with self.env.cr.savepoint():
                for old_group_id, old_date in original_values:
                    new_date = fields.Date.to_date(vals.get('session_date') or old_date)
                    self._check_not_billed(
                        self.env['afa.service.group'].browse(old_group_id), old_date
                    )
                    self._check_not_billed(
                        self.env['afa.service.group'].browse(old_group_id), new_date
                    )
                result = super().write(vals)
                if {'group_id', 'session_date'} & vals.keys():
                    self.flush_recordset(['group_id', 'session_date'])
                return result
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_group_absence_group_date_uniq':
                raise
            raise ValidationError(
                _('A canceled session is already recorded for this group and date.')
            ) from error

    def unlink(self):
        self.check_access('unlink')
        self._lock_groups(self.mapped('group_id').ids)
        self.env.invalidate_all()
        original_values = [(record.group_id.id, record.session_date) for record in self]
        for group_id, session_date in original_values:
            self._check_not_billed(self.env['afa.service.group'].browse(group_id), session_date)
        return super().unlink()

    @api.constrains('group_id', 'session_date', 'discount_amount')
    def _check_absence(self):
        for absence in self:
            service = absence.group_id.service_id
            if not service.is_extracurricular:
                raise ValidationError(_('Only extracurricular groups can have canceled sessions.'))
            if not service.date_start <= absence.session_date <= service.date_end:
                raise ValidationError(
                    _('Canceled sessions must be within the activity execution period.')
                )
            if absence.discount_amount < 0:
                raise ValidationError(_('The absence discount cannot be negative.'))
