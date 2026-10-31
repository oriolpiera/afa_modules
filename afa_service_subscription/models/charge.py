from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaServiceCharge(models.Model):
    _name = 'afa.service.charge'
    _description = 'AFA Monthly Service Invoice Charge'
    _order = 'month desc, id desc'

    subscription_id = fields.Many2one(
        'afa.service.subscription', required=True, ondelete='restrict', index=True
    )
    month = fields.Date(required=True, index=True)
    invoice_line_id = fields.Many2one('account.move.line', ondelete='set null')
    invoice_id = fields.Many2one('account.move', related='invoice_line_id.move_id', store=True)
    sponsor_invoice_line_id = fields.Many2one('account.move.line', ondelete='set null')
    sponsor_invoice_id = fields.Many2one(
        'account.move', related='sponsor_invoice_line_id.move_id', store=True
    )
    family_id = fields.Many2one('afa.family', required=True, ondelete='restrict')
    payer_id = fields.Many2one('res.partner', required=True, ondelete='restrict')
    sponsor_id = fields.Many2one('res.partner', ondelete='restrict')
    member = fields.Boolean(string='Member at Invoicing')
    price = fields.Monetary(required=True, string='Tariff Price', currency_field='currency_id')
    discount_amount = fields.Monetary(default=0, string='Discount', currency_field='currency_id')
    family_price = fields.Monetary(
        compute='_compute_family_price',
        store=True,
        string='Family Amount',
        currency_field='currency_id',
    )
    sponsor_price = fields.Monetary(
        default=0, string='Sponsor Amount', currency_field='currency_id'
    )
    subsidy_percent = fields.Float(default=0, digits=(5, 2))
    tariff_basis = fields.Selection(
        [('membership', 'Membership-based tariff'), ('member', 'Member tariff')],
        required=True,
        default='membership',
    )
    currency_id = fields.Many2one('res.currency', required=True)
    active = fields.Boolean(default=True, copy=False)

    @api.depends('price', 'discount_amount', 'sponsor_price', 'currency_id')
    def _compute_family_price(self):
        for charge in self:
            amount = max(charge.price - charge.discount_amount - charge.sponsor_price, 0)
            charge.family_price = charge.currency_id.round(amount) if charge.currency_id else amount

    def init(self):
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_service_charge_active_uniq '
            'ON afa_service_charge (subscription_id, month) WHERE active'
        )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('_afa_generate_service_invoices'):
            raise ValidationError(_('Generate charges from the monthly billing review.'))
        return super().create(vals_list)

    @api.constrains(
        'price',
        'discount_amount',
        'family_price',
        'sponsor_id',
        'sponsor_price',
        'subsidy_percent',
        'currency_id',
        'invoice_line_id',
        'sponsor_invoice_line_id',
    )
    def _check_charge_allocation(self):
        for charge in self:
            if (
                charge.price < 0
                or charge.discount_amount < 0
                or charge.sponsor_price < 0
                or not 0 <= charge.subsidy_percent <= 100
            ):
                raise ValidationError(_('Service charge amounts and subsidy must be valid.'))
            net_price = max(charge.price - charge.discount_amount, 0)
            if charge.sponsor_price > net_price:
                raise ValidationError(_('The sponsor amount cannot exceed the discounted tariff.'))
            if charge.currency_id.compare_amounts(
                charge.family_price + charge.sponsor_price, net_price
            ):
                raise ValidationError(
                    _('Family and sponsor amounts must equal the tariff after discounts.')
                )
            if charge.active and not charge.invoice_line_id and not charge.sponsor_invoice_line_id:
                raise ValidationError(_('A service charge must have at least one invoice line.'))
            if charge.active and charge.family_price and not charge.invoice_line_id:
                raise ValidationError(_('The family amount must have an invoice line.'))
            if (
                charge.active
                and charge.sponsor_price
                and (not charge.sponsor_id or not charge.sponsor_invoice_line_id)
            ):
                raise ValidationError(_('The sponsor amount must have a sponsor and invoice line.'))

    def write(self, vals):
        if (
            not self.env.context.get('_afa_cancel_service_invoice')
            or set(vals) != {'active'}
            or vals['active']
        ):
            raise ValidationError(_('Invoice charge history cannot be edited.'))
        return super().write(vals)

    def unlink(self):
        raise ValidationError(_('Invoice charge history cannot be deleted.'))
