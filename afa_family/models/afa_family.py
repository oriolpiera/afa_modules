from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class AfaFamily(models.Model):
    _name = 'afa.family'
    _description = 'AFA Family'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    # Not required at field level: the payer may come from a guardian flagged
    # inline during creation; _check_billing_guardian still requires it.
    billing_partner_id = fields.Many2one(
        'res.partner',
        string='Billing Guardian',
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
            # The payer is stored before its family can be assigned on create.
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

    @api.model
    def _resolve_inline_billing_guardian(self, vals):
        """Promote a guardian flagged on an inline guardian_ids row to initial payer.

        The web client cannot point billing_partner_id at an o2m row that does
        not exist yet, so the Guardians list flags the billing guardian instead.
        The flagged partner is created up front and the family create flow links
        it as any other initial unassigned guardian.
        """
        commands = list(vals.get('guardian_ids') or [])
        flagged = [
            command
            for command in commands
            if isinstance(command, (list, tuple))
            and len(command) == 3
            and command[0] == Command.CREATE
            and command[2].get('afa_is_billing_guardian')
        ]
        if not flagged:
            return
        if vals.get('billing_partner_id'):
            raise ValidationError(
                _('Set the billing guardian either in its field or on a guardian line, not both.')
            )
        if len(flagged) > 1:
            raise ValidationError(_('Only one guardian can be the billing guardian.'))
        partner_vals = dict(flagged[0][2])
        partner_vals.pop('afa_is_billing_guardian', None)
        partner_vals.setdefault('afa_family_role', 'guardian')
        if partner_vals.get('afa_family_role') != 'guardian':
            raise ValidationError(_('Only a guardian can be the billing guardian.'))
        if partner_vals.get('afa_family_id'):
            raise ValidationError(_('An inline guardian cannot be pre-assigned to a family.'))
        payer = self.env['res.partner'].create(partner_vals)
        vals['billing_partner_id'] = payer.id
        vals['guardian_ids'] = [command for command in commands if command is not flagged[0]]

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            self._resolve_inline_billing_guardian(vals)
        if not all(vals.get('billing_partner_id') for vals in vals_list):
            raise ValidationError(
                _(
                    'A family needs a billing guardian: flag one on the Guardians'
                    ' tab or select an unassigned guardian.'
                )
            )
        # The initial guardian has no family yet; link after the family has an ID.
        payers = self.env['res.partner'].browse([vals['billing_partner_id'] for vals in vals_list])
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

    def _action_open_add_existing_members(self, role):
        self.ensure_one()
        if not self.env.user.has_group('afa_family.group_family_manager'):
            raise AccessError(_('Only family managers may add family members.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Add Existing Contacts'),
            'res_model': 'afa.family.member.add.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_family_id': self.id,
                'default_role': role,
            },
        }

    def action_open_add_existing_guardians(self):
        return self._action_open_add_existing_members('guardian')

    def action_open_add_existing_students(self):
        return self._action_open_add_existing_members('student')
