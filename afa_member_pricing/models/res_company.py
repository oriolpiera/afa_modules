from odoo import _, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    afa_member_pricelist_id = fields.Many2one(
        'product.pricelist', string='AFA Member Pricelist', ondelete='restrict'
    )
    afa_nonmember_pricelist_id = fields.Many2one(
        'product.pricelist', string='AFA Non-member Pricelist', ondelete='restrict'
    )

    def _afa_pricelist_for_partner(self, partner, *, public=False):
        self.ensure_one()
        family = self.env['afa.family']
        if not public and partner:
            guardian = partner.sudo()
            if guardian.afa_family_role != 'guardian':
                guardian = guardian.commercial_partner_id
            if guardian.afa_family_role == 'guardian':
                family = guardian.afa_family_id
        member = bool(family and family.sudo().is_member)
        return self.afa_member_pricelist_id if member else self.afa_nonmember_pricelist_id

    def _check_afa_pricelists(self):
        for company in self:
            member = company.afa_member_pricelist_id
            nonmember = company.afa_nonmember_pricelist_id
            if bool(member) != bool(nonmember):
                raise ValidationError(_('Configure both AFA pricelists together.'))
            if member and (member == nonmember or member.currency_id != nonmember.currency_id):
                raise ValidationError(
                    _('AFA pricelists must be distinct and use the same currency.')
                )
            if member and (not member.website_id or member.website_id != nonmember.website_id):
                raise ValidationError(_('Assign both AFA pricelists to the same website.'))
            for pricelist in member | nonmember:
                if not pricelist.active or pricelist.company_id not in (
                    company,
                    self.env['res.company'],
                ):
                    raise ValidationError(
                        _('AFA pricelists must be active and belong to the company.')
                    )
            if member and (member.selectable or member.code):
                raise ValidationError(
                    _('The AFA member pricelist must not be selectable or have a promotional code.')
                )

    def write(self, vals):
        result = super().write(vals)
        if {'afa_member_pricelist_id', 'afa_nonmember_pricelist_id'} & vals.keys():
            self._check_afa_pricelists()
        return result
