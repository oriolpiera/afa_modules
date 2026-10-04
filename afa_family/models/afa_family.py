from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaFamily(models.Model):
    _name = 'afa.family'
    _description = 'AFA Family'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    billing_partner_id = fields.Many2one(
        'res.partner',
        string='Billing Guardian',
        required=True,
        ondelete='restrict',
        domain="[('afa_family_role', '=', 'guardian'), ('afa_family_id', '=', id or False)]",
    )
    guardian_ids = fields.One2many(
        'res.partner',
        'afa_family_id',
        string='Guardians',
        domain=[('afa_family_role', '=', 'guardian')],
    )
    student_ids = fields.One2many(
        'res.partner',
        'afa_family_id',
        string='Students',
        domain=[('afa_family_role', '=', 'student')],
    )

    @api.constrains('billing_partner_id')
    def _check_billing_guardian(self):
        for family in self:
            payer = family.billing_partner_id
            # The required payer is stored before its family can be assigned on create.
            # create() validates and links it, then checks the final invariant.
            if (
                self.env.context.get('_afa_initial_family_creation')
                and payer
                and not payer.afa_family_id
            ):
                continue
            if not payer or payer.afa_family_id != family or payer.afa_family_role != 'guardian':
                raise ValidationError(
                    _('The billing partner must be a guardian in the same family.')
                )

    @api.model_create_multi
    def create(self, vals_list):
        # The initial guardian has no family yet; link after the family has an ID.
        payers = self.env['res.partner'].browse(
            [vals['billing_partner_id'] for vals in vals_list if vals.get('billing_partner_id')]
        )
        for payer in payers:
            if payer.afa_family_id or payer.afa_family_role != 'guardian':
                raise ValidationError(
                    _('An initial billing partner must be an unassigned guardian.')
                )
        families = super(AfaFamily, self.with_context(_afa_initial_family_creation=True)).create(
            vals_list
        )
        for family in families:
            family.billing_partner_id.write({'afa_family_id': family.id})
        families._check_billing_guardian()
        return families

    def write(self, vals):
        result = super().write(vals)
        if 'billing_partner_id' in vals:
            self.with_context(_afa_initial_family_creation=False)._check_billing_guardian()
        return result

    def action_open_family_members(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Family Members'),
            'res_model': 'res.partner',
            'view_mode': 'list,form',
            'domain': [('afa_family_id', '=', self.id)],
            'context': {'default_afa_family_id': self.id},
        }
