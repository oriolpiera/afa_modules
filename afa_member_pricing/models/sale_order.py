from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.http import request


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    afa_family_id = fields.Many2one(
        'afa.family',
        string='AFA Family',
        compute='_compute_afa_family_id',
        compute_sudo=True,
        groups='afa_family.group_family_manager',
    )

    @api.depends('partner_id')
    def _compute_afa_family_id(self):
        for order in self:
            guardian = order.partner_id.sudo()
            if guardian.afa_family_role != 'guardian':
                guardian = guardian.commercial_partner_id
            order.afa_family_id = (
                guardian.afa_family_id if guardian.afa_family_role == 'guardian' else False
            )

    @api.depends('partner_id', 'company_id')
    def _compute_pricelist_id(self):
        super()._compute_pricelist_id()
        for order in self.filtered(lambda o: o.state in ('draft', 'sent') and o.partner_id):
            company = order.company_id.sudo()
            if company.afa_member_pricelist_id and company.afa_nonmember_pricelist_id:
                public = bool(order.website_id and request and request.env.user._is_public())
                order.pricelist_id = company._afa_pricelist_for_partner(
                    order.partner_id, public=public
                )

    def _afa_revalidate_cart(self):
        self.ensure_one()
        if not self.website_id or self.state != 'draft':
            return False
        company = self.company_id.sudo()
        if not (company.afa_member_pricelist_id and company.afa_nonmember_pricelist_id):
            return False
        public = bool(request and request.env.user._is_public())
        if request and not public and self.partner_id != request.env.user.partner_id:
            raise ValidationError(_('This cart belongs to another customer.'))
        expected = company._afa_pricelist_for_partner(self.partner_id, public=public)
        if self.pricelist_id == expected:
            return False
        self.pricelist_id = expected
        if request:
            request.session['website_sale_current_pl'] = expected.id
            request.session.pop('website_sale_selected_pl_id', None)
            request.pricelist = expected
        return True

    def _check_cart_is_ready_to_be_paid(self):
        if self.website_id and self.state == 'draft':
            company = self.company_id.sudo()
            if company.afa_member_pricelist_id and company.afa_nonmember_pricelist_id:
                public = bool(request and request.env.user._is_public())
                if request and not public and self.partner_id != request.env.user.partner_id:
                    raise ValidationError(_('This cart belongs to another customer.'))
                expected = company._afa_pricelist_for_partner(self.partner_id, public=public)
                if self.pricelist_id != expected:
                    raise ValidationError(
                        _('Your eligibility has changed. Review your cart before paying.')
                    )
        return super()._check_cart_is_ready_to_be_paid()

    def write(self, vals):
        drafts = self.filtered(lambda order: order.state in ('draft', 'sent'))
        old_partners = (
            {order.id: order.partner_id.id for order in drafts} if 'partner_id' in vals else {}
        )
        old_pricelists = (
            {order.id: order.pricelist_id.id for order in drafts}
            if {'partner_id', 'pricelist_id'} & vals.keys()
            else {}
        )
        result = super().write(vals)
        if old_pricelists and not self.env.context.get('_afa_repricing'):
            for order in drafts:
                if order.pricelist_id.id != old_pricelists.get(order.id) or (
                    'partner_id' in vals and order.partner_id.id != old_partners[order.id]
                ):
                    order._afa_recompute_quotation_prices()
        return result

    def _afa_recompute_quotation_prices(self):
        for order in self:
            if order.website_id:
                order.with_context(_afa_repricing=True)._recompute_prices()
                continue

            manually_priced = self.env['sale.order.line']
            agreed_prices = {}
            agreed_discounts = {}
            for line in order._get_update_prices_lines():
                currency = line.currency_id or order.company_id.currency_id
                if currency.compare_amounts(line.technical_price_unit, line.price_unit):
                    manually_priced |= line
                    agreed_prices[line.id] = line.price_unit
                if line.afa_manual_discount:
                    agreed_discounts[line.id] = line.discount

            order.with_context(_afa_repricing=True)._recompute_prices()
            for line in manually_priced:
                line.with_context(_afa_repricing=True).price_unit = agreed_prices[line.id]
            for line_id, discount in agreed_discounts.items():
                self.env['sale.order.line'].browse(line_id).with_context(
                    _afa_repricing=True
                ).discount = discount

    def action_confirm(self):
        for order in self.filtered(lambda so: so.state in ('draft', 'sent') and not so.website_id):
            company = order.company_id.sudo()
            if company.afa_member_pricelist_id and company.afa_nonmember_pricelist_id:
                expected = company._afa_pricelist_for_partner(order.partner_id)
                if order.pricelist_id != expected:
                    raise ValidationError(
                        _(
                            'Family membership has changed. Update this quotation to the '
                            'applicable pricelist before confirming it.'
                        )
                    )
        return super().action_confirm()
