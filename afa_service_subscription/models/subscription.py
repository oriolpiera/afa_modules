from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaServiceSubscription(models.Model):
    _name = 'afa.service.subscription'
    _description = 'AFA Student Service Subscription'
    _order = 'start_month desc, id desc'

    service_id = fields.Many2one('afa.service', required=True, ondelete='restrict', index=True)
    student_id = fields.Many2one(
        'res.partner',
        required=True,
        ondelete='restrict',
        index=True,
        domain=[('afa_family_role', '=', 'student')],
    )
    family_id = fields.Many2one(
        'afa.family', related='student_id.afa_family_id', store=True, readonly=True
    )
    join_window_id = fields.Many2one('afa.service.window', required=True, ondelete='restrict')
    join_requested_on = fields.Date(readonly=True, copy=False)
    start_month = fields.Date(readonly=True, copy=False)
    leave_window_id = fields.Many2one(
        'afa.service.window', readonly=True, copy=False, ondelete='restrict'
    )
    leave_requested_on = fields.Date(readonly=True, copy=False)
    end_month = fields.Date(
        readonly=True,
        copy=False,
        help='First month NOT billed; empty means through the end of the service.',
    )
    charge_ids = fields.One2many('afa.service.charge', 'subscription_id')

    @api.model_create_multi
    def create(self, vals_list):
        subscriptions = self.browse()
        for vals in vals_list:
            if {
                'start_month',
                'end_month',
                'join_requested_on',
                'leave_requested_on',
                'leave_window_id',
            } & vals.keys():
                raise ValidationError(_('Use the change windows to manage subscription dates.'))
            student = self.env['res.partner'].browse(vals['student_id'])
            service = self.env['afa.service'].browse(vals['service_id'])
            window = self.env['afa.service.window'].browse(vals['join_window_id'])
            today = fields.Date.context_today(self)
            if (
                not student.afa_family_id
                or student.afa_family_role != 'student'
                or window.service_id != service
                or window.kind != 'join'
                or not window.date_start <= today <= window.date_end
            ):
                raise ValidationError(
                    _('Enrollment requires a student and an open join window for this service.')
                )
            self._lock_student(student)
            self._check_overlap(student, service, window.effective_month, False)
            subscriptions |= super().create(
                [dict(vals, start_month=window.effective_month, join_requested_on=today)]
            )
        return subscriptions

    def write(self, vals):
        if {
            'service_id',
            'student_id',
            'join_window_id',
            'join_requested_on',
            'start_month',
            'leave_window_id',
            'leave_requested_on',
            'end_month',
            'family_id',
        } & vals.keys():
            raise ValidationError(_('Subscription history is immutable; use a change window.'))
        return super().write(vals)

    def unlink(self):
        raise ValidationError(_('Subscription history cannot be deleted.'))

    @api.model
    def _lock_student(self, student):
        # Serialize concurrent enrollments for this student, even before any subscription exists.
        self.env.cr.execute('SELECT id FROM res_partner WHERE id = %s FOR UPDATE', [student.id])

    @api.model
    def _check_overlap(self, student, service, start, end, exclude_id=False):
        domain = [
            ('student_id', '=', student.id),
            ('service_id', '=', service.id),
            ('start_month', '<', end or '9999-12-31'),
            '|',
            ('end_month', '=', False),
            ('end_month', '>', start),
        ]
        if exclude_id:
            domain.append(('id', '!=', exclude_id))
        if self.search_count(domain):
            raise ValidationError(_('This student already has an overlapping subscription.'))

    def action_leave(self, window):
        self.ensure_one()
        window.ensure_one()
        today = fields.Date.context_today(self)
        if (
            self.leave_window_id
            or window.service_id != self.service_id
            or window.kind != 'leave'
            or not window.date_start <= today <= window.date_end
            or window.effective_month <= self.start_month
        ):
            raise ValidationError(_('Select an open leave window after the enrollment month.'))
        self._lock_student(self.student_id)
        if self.env['afa.service.charge'].search_count(
            [
                ('subscription_id', '=', self.id),
                ('month', '>=', window.effective_month),
                ('active', '=', True),
            ]
        ):
            raise ValidationError(
                _('Cancel invoices for months after the withdrawal takes effect first.')
            )
        super().write(
            {
                'leave_window_id': window.id,
                'leave_requested_on': today,
                'end_month': window.effective_month,
            }
        )

    def action_request_leave(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Request Service Withdrawal'),
            'res_model': 'afa.service.leave',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_subscription_id': self.id},
        }


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def write(self, vals):
        if {'afa_family_id', 'afa_family_role'} & vals.keys() and self.env[
            'afa.service.subscription'
        ].search_count([('student_id', 'in', self.ids)]):
            raise ValidationError(_('A subscribed student cannot change family or role.'))
        return super().write(vals)
