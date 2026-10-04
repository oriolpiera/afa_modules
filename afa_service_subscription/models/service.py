from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaService(models.Model):
    _name = 'afa.service'
    _description = 'AFA Monthly Service'

    name = fields.Char(required=True)
    period_id = fields.Many2one('afa.membership.period', required=True, ondelete='restrict')
    date_start = fields.Date(required=True, help='First day of the first billable month.')
    date_end = fields.Date(required=True, help='Last day of the last billable month.')
    product_id = fields.Many2one(
        'product.product', required=True, ondelete='restrict', domain=[('sale_ok', '=', True)]
    )
    member_price = fields.Monetary(required=True, currency_field='currency_id')
    nonmember_price = fields.Monetary(required=True, currency_field='currency_id')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    window_ids = fields.One2many('afa.service.window', 'service_id', string='Change Windows')
    subscription_ids = fields.One2many('afa.service.subscription', 'service_id')

    def write(self, vals):
        if {
            'period_id',
            'date_start',
            'date_end',
            'company_id',
            'product_id',
        } & vals.keys() and self.env['afa.service.subscription'].search_count(
            [('service_id', 'in', self.ids)]
        ):
            raise ValidationError(
                _('A service with subscriptions cannot change its identity or period.')
            )
        result = super().write(vals)
        if {'period_id', 'date_start', 'date_end'} & vals.keys():
            self.mapped('window_ids')._check_window()
        return result

    @api.constrains(
        'date_start',
        'date_end',
        'period_id',
        'member_price',
        'nonmember_price',
        'product_id',
        'company_id',
    )
    def _check_configuration(self):
        for service in self:
            if (
                service.date_start
                and service.date_end
                and (
                    service.date_start.day != 1
                    or (service.date_end + timedelta(days=1)).day != 1
                    or service.date_start > service.date_end
                    or service.date_start < service.period_id.date_start
                    or service.date_end > service.period_id.date_end
                )
            ):
                raise ValidationError(
                    _('Service dates must cover complete months in the school year.')
                )
            if service.member_price < 0 or service.nonmember_price < 0:
                raise ValidationError(_('Service prices cannot be negative.'))
            product_company = service.product_id.company_id
            if service.product_id and (
                not service.product_id.sale_ok
                or product_company not in (service.company_id, self.env['res.company'])
            ):
                raise ValidationError(_('Choose a saleable product in the service company.'))


class AfaServiceWindow(models.Model):
    _name = 'afa.service.window'
    _description = 'AFA Service Change Window'
    _order = 'date_start, id'

    service_id = fields.Many2one('afa.service', required=True, ondelete='cascade')
    kind = fields.Selection([('join', 'Join'), ('leave', 'Leave')], required=True)
    date_start = fields.Date(required=True, string='Requests From')
    date_end = fields.Date(required=True, string='Requests Through')
    effective_month = fields.Date(
        required=True, help='First day of the month when this change takes effect.'
    )

    def write(self, vals):
        if self._used_windows():
            raise ValidationError(_('A window used by subscriptions cannot be changed.'))
        return super().write(vals)

    def _used_windows(self):
        return self.env['afa.service.subscription'].search_count(
            [
                '|',
                ('join_window_id', 'in', self.ids),
                ('leave_window_id', 'in', self.ids),
            ]
        )

    @api.constrains('service_id', 'kind', 'date_start', 'date_end', 'effective_month')
    def _check_window(self):
        for window in self:
            service = window.service_id
            if not all((window.date_start, window.date_end, window.effective_month)):
                continue
            if (
                window.date_start > window.date_end
                or window.effective_month.day != 1
                or window.effective_month < service.date_start
                or window.effective_month > service.date_end + timedelta(days=1)
                or (window.kind == 'join' and window.effective_month > service.date_end)
                or window.date_start < service.period_id.date_start
                or window.date_end > service.period_id.date_end
                or window.effective_month < window.date_start.replace(day=1)
            ):
                raise ValidationError(
                    _('Change window dates and effective month must fit the service period.')
                )
            if self.search_count(
                [
                    ('id', '!=', window.id),
                    ('service_id', '=', service.id),
                    ('kind', '=', window.kind),
                    ('date_start', '<=', window.date_end),
                    ('date_end', '>=', window.date_start),
                ]
            ):
                raise ValidationError(_('Change windows of the same type cannot overlap.'))

    def unlink(self):
        if self._used_windows():
            raise ValidationError(_('A window used by subscriptions cannot be deleted.'))
        return super().unlink()
