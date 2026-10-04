from odoo.http import request

from odoo.addons.website_sale.controllers.main import WebsiteSale


class AfaWebsiteSale(WebsiteSale):
    def _apply_selectable_pricelist(self, pricelist_id):
        if pricelist_id == request.website.company_id.sudo().afa_member_pricelist_id.id:
            return False
        return super()._apply_selectable_pricelist(pricelist_id)

    def _apply_pricelist(self, pricelist=None):
        if pricelist and pricelist == request.website.company_id.sudo().afa_member_pricelist_id:
            return
        return super()._apply_pricelist(pricelist=pricelist)
