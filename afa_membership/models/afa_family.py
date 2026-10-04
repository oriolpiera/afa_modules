from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class AfaFamily(models.Model):
    _inherit = 'afa.family'

    _derived_membership_fields = frozenset(
        {
            'is_member',
            'membership_state',
            'membership_mode',
            'current_period_id',
            'current_dues_invoice_id',
        }
    )

    membership_ids = fields.One2many(
        'afa.membership',
        'family_id',
        string='Period Links',
        groups='afa_family.group_family_manager',
    )
    manual_member = fields.Boolean(
        string='Manual Membership', groups='afa_family.group_family_manager'
    )
    is_member = fields.Boolean(
        compute='_compute_membership_status',
        string='Is Member',
        groups='afa_family.group_family_manager',
        compute_sudo=True,
    )
    membership_state = fields.Selection(
        [('inactive', 'Not a Member'), ('manual', 'Manual Member'), ('paid', 'Paid Dues')],
        compute='_compute_membership_status',
        string='Membership Status',
        groups='afa_family.group_family_manager',
        compute_sudo=True,
    )
    membership_mode = fields.Selection(
        [('invoice', 'Invoice'), ('manual', 'Manual')],
        compute='_compute_membership_status',
        string='Membership Mode',
        groups='afa_family.group_family_manager',
        compute_sudo=True,
    )
    current_period_id = fields.Many2one(
        'afa.membership.period',
        compute='_compute_membership_status',
        string='Current School Year',
        groups='afa_family.group_family_manager',
        compute_sudo=True,
    )
    current_dues_invoice_id = fields.Many2one(
        'account.move',
        compute='_compute_membership_status',
        string='Current Dues Invoice',
        groups='afa_family.group_family_manager',
        compute_sudo=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_membership_write(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._check_membership_write(vals)
        return super().write(vals)

    def _check_membership_write(self, vals):
        if self._derived_membership_fields.intersection(vals):
            raise ValidationError(_('Membership status is calculated and cannot be edited.'))
        if 'manual_member' in vals and not (
            self.env.su or self.env.user.has_group('afa_family.group_family_manager')
        ):
            raise AccessError(_('Only family managers may edit manual membership.'))

    @api.depends(
        'manual_member',
        'membership_ids',
        'membership_ids.active',
        'membership_ids.period_id',
        'membership_ids.period_id.date_start',
        'membership_ids.period_id.date_end',
        'membership_ids.invoice_id',
        'membership_ids.invoice_id.amount_total',
        'membership_ids.invoice_id.state',
        'membership_ids.invoice_id.payment_state',
        'membership_ids.invoice_id.reversal_move_ids',
        'membership_ids.invoice_id.reversal_move_ids.state',
    )
    def _compute_membership_status(self):
        mode = self.env['ir.config_parameter'].sudo().get_param('afa_membership.mode', 'invoice')
        if mode not in ('invoice', 'manual'):
            mode = 'invoice'
        today = fields.Date.context_today(self)
        period = self.env['afa.membership.period'].search(
            [('date_start', '<=', today), ('date_end', '>=', today)], limit=1
        )
        links = (
            self.env['afa.membership'].search(
                [
                    ('family_id', 'in', self.ids),
                    ('period_id', '=', period.id),
                    ('active', '=', True),
                ]
            )
            if period
            else self.env['afa.membership']
        )
        by_family = {link.family_id.id: link for link in links}
        for family in self:
            link = by_family.get(family.id)
            paid = bool(link and link.is_invoice_member_on(today)) if mode == 'invoice' else False
            family.membership_mode = mode
            family.current_period_id = period
            family.current_dues_invoice_id = link.invoice_id if link else False
            family.is_member = family.manual_member if mode == 'manual' else paid
            family.membership_state = (
                'manual'
                if mode == 'manual' and family.manual_member
                else 'paid'
                if paid
                else 'inactive'
            )
