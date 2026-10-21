from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaExtracurricularAid(models.Model):
    _name = 'afa.extracurricular.aid'
    _description = 'AFA Extracurricular Scholarship'
    _order = 'period_id desc, family_id'

    family_id = fields.Many2one('afa.family', required=True, ondelete='restrict', index=True)
    period_id = fields.Many2one(
        'afa.membership.period', required=True, ondelete='restrict', index=True
    )
    sponsor_id = fields.Many2one(
        'res.partner',
        string='Sponsor',
        required=True,
        ondelete='restrict',
        domain=[('is_company', '=', True)],
    )
    subsidy_percent = fields.Float(string='Council Share (%)', required=True, digits=(5, 2))
    tariff_basis = fields.Selection(
        [
            ('membership', 'Use the family membership tariff'),
            ('member', 'Always use the member tariff'),
        ],
        required=True,
        string='Tariff Basis',
    )

    def init(self):
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_extracurricular_aid_family_period_uniq '
            'ON afa_extracurricular_aid (family_id, period_id)'
        )

    @api.model
    def _lock_families(self, family_ids):
        for family_id in sorted(set(family_ids) - {False, None}):
            self.env.cr.execute('SELECT id FROM afa_family WHERE id = %s FOR UPDATE', [family_id])
        self.env.invalidate_all()

    @api.model_create_multi
    def create(self, vals_list):
        self._lock_families([vals.get('family_id') for vals in vals_list])
        try:
            with self.env.cr.savepoint():
                return super().create(vals_list)
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_extracurricular_aid_family_period_uniq':
                raise
            raise ValidationError(
                _('A family can only have one extracurricular scholarship per school year.')
            ) from error

    def write(self, vals):
        if {
            'family_id',
            'period_id',
            'sponsor_id',
            'subsidy_percent',
            'tariff_basis',
        } & vals.keys():
            family_ids = self.mapped('family_id').ids
            if vals.get('family_id'):
                family_ids.append(vals['family_id'])
            self._lock_families(family_ids)
        if {'family_id', 'period_id'} & vals.keys() and self.env[
            'afa.service.charge'
        ].sudo().with_context(active_test=False).search_count([('aid_id', 'in', self.ids)]):
            raise ValidationError(
                _('A scholarship used by billed charges cannot change family or school year.')
            )
        return super().write(vals)

    def unlink(self):
        self._lock_families(self.mapped('family_id').ids)
        if (
            self.env['afa.service.charge']
            .sudo()
            .with_context(active_test=False)
            .search_count([('aid_id', 'in', self.ids)])
        ):
            raise ValidationError(_('A scholarship used by billed charges cannot be deleted.'))
        return super().unlink()

    @api.constrains('family_id', 'period_id', 'sponsor_id', 'subsidy_percent', 'tariff_basis')
    def _check_configuration(self):
        for aid in self:
            if not 0 <= aid.subsidy_percent <= 100:
                raise ValidationError(_('The Council share must be between 0 and 100 percent.'))
            if aid.sponsor_id and not aid.sponsor_id.is_company:
                raise ValidationError(_('The scholarship sponsor must be a company contact.'))
            if aid.sponsor_id == aid.family_id.billing_partner_id:
                raise ValidationError(
                    _('The scholarship sponsor and the family billing guardian must differ.')
                )
            if self.search_count(
                [
                    ('id', '!=', aid.id),
                    ('family_id', '=', aid.family_id.id),
                    ('period_id', '=', aid.period_id.id),
                ]
            ):
                raise ValidationError(
                    _('A family can only have one extracurricular scholarship per school year.')
                )


class AfaFamily(models.Model):
    _inherit = 'afa.family'

    extracurricular_aid_ids = fields.One2many(
        'afa.extracurricular.aid',
        'family_id',
        string='Extracurricular Scholarships',
        groups='afa_family.group_family_manager',
    )
