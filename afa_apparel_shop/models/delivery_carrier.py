from odoo import fields, models


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    afa_school_pickup = fields.Boolean(
        string='School Pickup (No Address)',
        help=(
            'Orders with this delivery method are collected at the school. '
            'The checkout does not require a delivery address for them.'
        ),
    )

    def _match_address(self, partner):
        # School pickup never depends on the customer's address.
        if self.afa_school_pickup:
            return True
        return super()._match_address(partner)
