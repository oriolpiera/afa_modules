from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    afa_family_id = fields.Many2one(
        'afa.family',
        string='AFA Family',
        ondelete='set null',
        index=True,
        groups='afa_family.group_family_manager',
    )
    afa_family_role = fields.Selection(
        [
            ('guardian', 'Guardian'),
            ('student', 'Student'),
        ],
        string='AFA Family Role',
        groups='afa_family.group_family_manager',
    )
    # Record rules need a searchable field that staff can access without exposing roles.
    afa_is_student = fields.Boolean(
        compute='_compute_afa_is_student', store=True, compute_sudo=True
    )
    # UI affordance: a many2one cannot point at an unsaved o2m row, so the family
    # form flags the billing guardian from the guardians list instead.
    afa_is_billing_guardian = fields.Boolean(
        string='Billing Guardian',
        compute='_compute_afa_is_billing_guardian',
        inverse='_inverse_afa_is_billing_guardian',
        store=True,
        groups='afa_family.group_family_manager',
        help='Checked for the guardian who receives the family invoices.',
    )

    @api.depends('afa_family_role')
    def _compute_afa_is_student(self):
        for partner in self:
            partner.afa_is_student = partner.afa_family_role == 'student'

    @api.depends('afa_family_id.billing_partner_id')
    def _compute_afa_is_billing_guardian(self):
        for partner in self:
            partner.afa_is_billing_guardian = bool(partner.afa_family_id) and (
                partner.afa_family_id.billing_partner_id == partner
            )

    def _inverse_afa_is_billing_guardian(self):
        for partner in self:
            family = partner.afa_family_id
            if partner.afa_is_billing_guardian:
                if not family:
                    raise ValidationError(_('A billing guardian must belong to a family.'))
                if family.billing_partner_id != partner:
                    family.billing_partner_id = partner
            elif family.billing_partner_id == partner:
                raise ValidationError(
                    _('Select another billing guardian before clearing this one.')
                )

    def _can_manage_family(self):
        return self.env.su or self.env.user.has_group('afa_family.group_family_manager')

    @api.constrains('afa_family_id', 'afa_family_role')
    def _check_family_membership(self):
        for partner in self:
            if partner.afa_family_id and not partner.afa_family_role:
                raise ValidationError(_('A family member must have a guardian or student role.'))

    @api.model_create_multi
    def create(self, vals_list):
        if (
            any(vals.get('afa_family_id') or vals.get('afa_family_role') for vals in vals_list)
            and not self._can_manage_family()
        ):
            raise AccessError(_('Only family managers may assign family membership or roles.'))
        # A guardian flagged in create vals (e.g. an o2m line of a saved family)
        # is applied by the field inverse, which sets the family payer.
        partners = super().create(vals_list)
        return partners

    def write(self, vals):
        membership_changed = 'afa_family_id' in vals or 'afa_family_role' in vals
        if membership_changed and not self._can_manage_family():
            raise AccessError(_('Only family managers may change family membership or roles.'))
        affected = self.env['afa.family']
        if membership_changed:
            affected = affected.with_context(active_test=False).search(
                [
                    ('billing_partner_id', 'in', self.ids),
                ]
            )
        result = super().write(vals)
        if membership_changed:
            self._check_family_membership()
            affected._check_billing_guardian()
        return result

    def unlink(self):
        manager = self._can_manage_family()
        if self and not manager and self.sudo().filtered('afa_family_id'):
            raise AccessError(_('Only family managers may delete family members.'))
        if manager and self.env['afa.family'].with_context(active_test=False).search_count(
            [
                ('billing_partner_id', 'in', self.ids),
            ]
        ):
            raise ValidationError(
                _('Reassign the family billing guardian before deleting this partner.')
            )
        return super().unlink()
