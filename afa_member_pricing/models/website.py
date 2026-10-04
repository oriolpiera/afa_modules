from odoo import models
from odoo.http import request


class Website(models.Model):
    _inherit = 'website'

    def _get_and_cache_current_pricelist(self):
        self.ensure_one()
        company = self.company_id.sudo()
        if company.afa_member_pricelist_id and company.afa_nonmember_pricelist_id:
            user = self.env.user
            cached_id = request.session.get('website_sale_current_pl')
            if (
                request.session.get('afa_pricing_user_id') == user.id
                and cached_id
                in (
                    company.afa_member_pricelist_id.id,
                    company.afa_nonmember_pricelist_id.id,
                )
                and (not user._is_public() or cached_id != company.afa_member_pricelist_id.id)
            ):
                cached = self.env['product.pricelist'].sudo().browse(cached_id)
                if cached._is_available_on_website(self):
                    return cached
            pricelist = company._afa_pricelist_for_partner(
                user.partner_id, public=user._is_public()
            )
            if pricelist._is_available_on_website(self):
                request.session['website_sale_current_pl'] = pricelist.id
                request.session.pop('website_sale_selected_pl_id', None)
                request.session['afa_pricing_user_id'] = user.id
                return pricelist.sudo()
        return super()._get_and_cache_current_pricelist()

    def is_pricelist_available(self, pl_id):
        self.ensure_one()
        member_pricelist = self.company_id.sudo().afa_member_pricelist_id
        if member_pricelist and pl_id == member_pricelist.id:
            return False
        return super().is_pricelist_available(pl_id)

    def _get_and_cache_current_cart(self):
        previous_id = request.session.get('sale_order_id')
        cart = super()._get_and_cache_current_cart()
        if (
            cart
            and not request.env.cr.readonly
            and (not previous_id or request.httprequest.path == '/shop/cart')
        ):
            cart._afa_revalidate_cart()
        return cart
