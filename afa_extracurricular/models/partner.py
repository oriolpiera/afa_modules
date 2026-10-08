from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    afa_extracurricular_count = fields.Integer(compute='_compute_afa_extracurricular_count')

    def _compute_afa_extracurricular_count(self):
        counts = dict.fromkeys(self.ids, 0)
        for subscription in self.env['afa.service.subscription'].search(
            [
                ('student_id', 'in', self.ids),
                ('service_id.is_extracurricular', '=', True),
            ]
        ):
            counts[subscription.student_id.id] += 1
        for partner in self:
            partner.afa_extracurricular_count = counts[partner.id]

    def action_open_afa_extracurriculars(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Extracurricular Enrollment'),
            'res_model': 'afa.service.subscription',
            'view_mode': 'list,form',
            'views': [
                (
                    self.env.ref(
                        'afa_extracurricular.view_afa_subscription_extracurricular_list'
                    ).id,
                    'list',
                ),
                (
                    self.env.ref('afa_service_subscription.view_afa_service_subscription_form').id,
                    'form',
                ),
            ],
            'domain': [
                ('student_id', '=', self.id),
                ('service_id.is_extracurricular', '=', True),
            ],
            'context': {'default_student_id': self.id},
        }


class AfaFamily(models.Model):
    _inherit = 'afa.family'

    afa_extracurricular_count = fields.Integer(compute='_compute_afa_extracurricular_count')

    def _compute_afa_extracurricular_count(self):
        counts = dict.fromkeys(self.ids, 0)
        for subscription in self.env['afa.service.subscription'].search(
            [
                ('family_id', 'in', self.ids),
                ('service_id.is_extracurricular', '=', True),
            ]
        ):
            counts[subscription.family_id.id] += 1
        for family in self:
            family.afa_extracurricular_count = counts[family.id]

    def action_open_afa_extracurriculars(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Extracurricular Enrollment'),
            'res_model': 'afa.service.subscription',
            'view_mode': 'list,form',
            'views': [
                (
                    self.env.ref(
                        'afa_extracurricular.view_afa_subscription_extracurricular_list'
                    ).id,
                    'list',
                ),
                (
                    self.env.ref('afa_service_subscription.view_afa_service_subscription_form').id,
                    'form',
                ),
            ],
            'domain': [
                ('family_id', '=', self.id),
                ('service_id.is_extracurricular', '=', True),
            ],
        }
