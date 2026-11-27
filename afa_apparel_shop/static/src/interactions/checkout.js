import { patch } from '@web/core/utils/patch';
import { Checkout } from '@website_sale/interactions/checkout';

patch(Checkout.prototype, {
    /**
     * Override of @website_sale to keep the delivery address section in sync
     * with the selected delivery method: school pickup orders must not show
     * address fields, and home delivery orders must show them again. The
     * section visibility is rendered server-side, so reload when it no longer
     * matches the selection.
     *
     * @param {Event} ev
     * @return {void}
     */
    async selectDeliveryMethod(ev) {
        await super.selectDeliveryMethod(...arguments);
        const deliveryAddressList = document.getElementById('delivery_address_list');
        const checkedRadio = this.el.querySelector('input[name="o_delivery_radio"]:checked');
        if (!deliveryAddressList || !checkedRadio) {
            return;
        }
        const isSchoolPickup = checkedRadio.dataset.afaSchoolPickup === 'true';
        const addressHidden = deliveryAddressList.classList.contains('d-none');
        if (isSchoolPickup !== addressHidden) {
            window.location.reload();
        }
    },
});
