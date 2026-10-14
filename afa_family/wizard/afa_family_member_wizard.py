from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError


class AfaFamilyMemberAddWizard(models.TransientModel):
    _name = 'afa.family.member.add.wizard'
    _description = 'Add Existing Family Members'

    family_id = fields.Many2one('afa.family', required=True, readonly=True)
    role = fields.Selection(
        [('guardian', 'Guardian'), ('student', 'Student')],
        required=True,
        readonly=True,
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string='Contacts',
        domain=[('afa_family_id', '=', False)],
        required=True,
    )

    def action_add_members(self):
        self.ensure_one()
        if not self.env.user.has_group('afa_family.group_family_manager'):
            raise AccessError(_('Only family managers may add family members.'))

        family = self.family_id.exists()
        if not family:
            raise UserError(_('The family no longer exists.'))
        if self.role not in ('guardian', 'student'):
            raise UserError(_('Choose whether to add guardians or students.'))
        if not self.partner_ids:
            raise UserError(_('Select at least one contact.'))

        # Recheck the domain at confirmation time; a contact may have been
        # assigned to another family after the wizard was opened. Search under
        # the current user so partner record rules continue to apply.
        partners = self.env['res.partner'].search(
            [('id', 'in', self.partner_ids.ids), ('afa_family_id', '=', False)]
        )
        if set(partners.ids) != set(self.partner_ids.ids):
            raise UserError(_('Only contacts without a family can be added.'))

        partners.write({'afa_family_id': family.id, 'afa_family_role': self.role})
        return {'type': 'ir.actions.act_window_close'}
