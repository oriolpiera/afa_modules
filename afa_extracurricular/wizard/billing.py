from odoo import _, fields, models


class AfaServiceBilling(models.TransientModel):
    _inherit = 'afa.service.billing'

    def _snapshot(self, subscription):
        snapshot = super()._snapshot(subscription)
        if not subscription.is_extracurricular:
            snapshot['aid_id'] = False
            return snapshot

        aid = self.env['afa.extracurricular.aid'].search(
            [
                ('family_id', '=', subscription.family_id.id),
                ('period_id', '=', subscription.service_id.period_id.id),
            ],
            limit=1,
        )
        snapshot['aid_id'] = aid.id or False
        service = subscription.service_id
        tariff = service.member_price if aid and aid.tariff_basis == 'member' else snapshot['price']
        tariff = service.currency_id.round(tariff)
        next_month = fields.Date.add(self.month, months=1)
        absences = self.env['afa.service.group.absence'].search(
            [
                ('group_id', '=', subscription.group_id.id),
                ('session_date', '>=', self.month),
                ('session_date', '<', next_month),
            ]
        )
        discount_amount = service.currency_id.round(sum(absences.mapped('discount_amount')))
        discounted_tariff = service.currency_id.round(max(tariff - discount_amount, 0))
        snapshot.update(
            {
                'price': tariff,
                'discount_amount': discount_amount,
                'family_price': discounted_tariff,
                'sponsor_price': 0,
            }
        )
        if not aid:
            return snapshot

        sponsor_price = service.currency_id.round(discounted_tariff * aid.subsidy_percent / 100)
        snapshot.update(
            {
                'family_price': service.currency_id.round(discounted_tariff - sponsor_price),
                'sponsor_id': aid.sponsor_id.id,
                'sponsor_price': sponsor_price,
                'subsidy_percent': aid.subsidy_percent,
                'tariff_basis': aid.tariff_basis,
            }
        )
        if sponsor_price and aid.sponsor_id == subscription.family_id.billing_partner_id:
            snapshot['billing_error'] = _(
                'The sponsor and family billing guardian must be different contacts.'
            )
        return snapshot

    def _billing_line_values(self, values, snapshot):
        values = super()._billing_line_values(values, snapshot)
        values['aid_id'] = snapshot.get('aid_id') or False
        return values

    def _snapshot_matches_line(self, line, snapshot):
        return super()._snapshot_matches_line(line, snapshot) and (
            (line.aid_id.id or False) == (snapshot.get('aid_id') or False)
        )

    def _charge_snapshot_values(self, snapshot):
        values = super()._charge_snapshot_values(snapshot)
        values['aid_id'] = snapshot.get('aid_id') or False
        return values

    def _lock_additional_billing_resources(self, selected):
        super()._lock_additional_billing_resources(selected)
        group_ids = sorted(set(selected.mapped('subscription_id.group_id').ids))
        for group_id in group_ids:
            self.env.cr.execute(
                'SELECT id FROM afa_service_group WHERE id = %s FOR UPDATE', [group_id]
            )


class AfaServiceBillingLine(models.TransientModel):
    _inherit = 'afa.service.billing.line'

    aid_id = fields.Many2one('afa.extracurricular.aid', readonly=True)
