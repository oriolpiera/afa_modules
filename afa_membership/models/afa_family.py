from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class AfaFamily(models.Model):
    _inherit = 'afa.family'

    _derived_membership_fields = frozenset(
        {
            'is_member',
            'membership_state',
            'current_period_id',
            'current_dues_invoice_id',
            'current_dues_invoice_reference',
        }
    )

    membership_ids = fields.One2many(
        'afa.membership',
        'family_id',
        string='Period Links',
        groups='afa_family.group_family_manager',
        context={'active_test': False},
    )
    manual_member = fields.Boolean(
        string='Intends to Be a Member',
        help='Keep enabled while this family intends to remain an AFA member.',
        groups='afa_family.group_family_manager',
    )
    is_member = fields.Boolean(
        compute='_compute_membership_status',
        string='Is Member',
        groups='afa_family.group_family_manager',
        compute_sudo=True,
    )
    membership_state = fields.Selection(
        [('inactive', 'Not a Member'), ('member', 'Member')],
        compute='_compute_membership_status',
        string='Membership Status',
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
    current_dues_invoice_reference = fields.Char(
        compute='_compute_membership_status',
        string='Current Dues Invoice Reference',
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
            raise AccessError(_('Only family managers may edit membership intention.'))

    @api.depends(
        'manual_member',
        'membership_ids',
        'membership_ids.active',
        'membership_ids.period_id',
        'membership_ids.period_id.date_start',
        'membership_ids.period_id.date_end',
        'membership_ids.invoice_id',
        'membership_ids.returned_dues_invoice_id',
        'membership_ids.invoice_id.amount_total',
        'membership_ids.invoice_id.state',
        'membership_ids.invoice_id.payment_state',
        'membership_ids.invoice_id.reversal_move_ids',
        'membership_ids.invoice_id.reversal_move_ids.state',
        'membership_ids.returned_dues_invoice_id.state',
        'membership_ids.returned_dues_invoice_id.payment_state',
    )
    def _compute_membership_status(self):
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
        revoked_links = links._membership_fee_revoked_links()
        suspended_family_ids = self._families_with_unpaid_returned_dues()
        suspended_family_ids.update(revoked_links.mapped('family_id').ids)
        for family in self:
            link = by_family.get(family.id)
            family.current_period_id = period
            family.current_dues_invoice_id = link.invoice_id if link else False
            family.current_dues_invoice_reference = (
                link.invoice_id.display_name if link and link.invoice_id else False
            )
            family.is_member = bool(family.manual_member and family.id not in suspended_family_ids)
            family.membership_state = 'member' if family.is_member else 'inactive'

    def is_member_on(self, check_date):
        """Return the family's effective membership for a date in a school year."""
        self.ensure_one()
        if not self.manual_member:
            return False
        if self._families_with_unpaid_returned_dues():
            return False
        period = self.env['afa.membership.period'].search(
            [('date_start', '<=', check_date), ('date_end', '>=', check_date)], limit=1
        )
        if not period:
            return True
        link = self.env['afa.membership'].search(
            [
                ('family_id', '=', self.id),
                ('period_id', '=', period.id),
                ('active', '=', True),
            ],
            limit=1,
        )
        return not bool(link and link._membership_fee_revoked_links())

    def _families_with_unpaid_returned_dues(self):
        links = (
            self.env['afa.membership']
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ('family_id', 'in', self.ids),
                    ('returned_dues_invoice_id', '!=', False),
                ]
            )
        )
        return set(
            links.filtered(
                lambda link: (
                    link.returned_dues_invoice_id.state != 'cancel'
                    and link.returned_dues_invoice_id.payment_state != 'paid'
                )
            )
            .mapped('family_id')
            .ids
        )
