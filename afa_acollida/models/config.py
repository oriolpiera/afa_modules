from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AfaAcollidaConfig(models.Model):
    _name = 'afa.acollida.config'
    _description = 'AFA Acollida Billing Configuration'
    _order = 'period_id desc, id desc'

    name = fields.Char(related='period_id.name', store=True, readonly=True)
    period_id = fields.Many2one(
        'afa.membership.period', required=True, ondelete='restrict', index=True
    )
    product_id = fields.Many2one(
        'product.product', required=True, ondelete='restrict', domain=[('sale_ok', '=', True)]
    )
    invoice_journal_id = fields.Many2one(
        'account.journal',
        string='Invoice Journal',
        required=True,
        domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]",
        check_company=True,
    )
    payment_mode_id = fields.Many2one(
        'account.payment.mode',
        string='Payment Mode',
        required=True,
        domain="[('payment_type', '=', 'inbound'), ('company_id', '=', company_id)]",
        check_company=True,
    )
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    charge_ids = fields.One2many('afa.acollida.charge', 'config_id', readonly=True)

    def init(self):
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS afa_acollida_config_period_uniq '
            'ON afa_acollida_config (period_id)'
        )

    @api.model_create_multi
    def create(self, vals_list):
        try:
            with self.env.cr.savepoint():
                return super().create(vals_list)
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_acollida_config_period_uniq':
                raise
            raise ValidationError(
                _('Only one Acollida configuration is allowed per school year.')
            ) from error

    def write(self, vals):
        if 'period_id' in vals and self.env['afa.acollida.charge'].with_context(
            active_test=False
        ).search_count([('config_id', 'in', self.ids)]):
            raise ValidationError(
                _('A configuration with imported charges cannot change school year.')
            )
        try:
            with self.env.cr.savepoint():
                result = super().write(vals)
                self.flush_recordset(['period_id'])
                return result
        except IntegrityError as error:
            if error.diag.constraint_name != 'afa_acollida_config_period_uniq':
                raise
            raise ValidationError(
                _('Only one Acollida configuration is allowed per school year.')
            ) from error

    @api.constrains(
        'period_id', 'product_id', 'invoice_journal_id', 'payment_mode_id', 'company_id'
    )
    def _check_configuration(self):
        for config in self:
            if self.search_count(
                [('id', '!=', config.id), ('period_id', '=', config.period_id.id)]
            ):
                raise ValidationError(
                    _('Only one Acollida configuration is allowed per school year.')
                )
            if config.product_id and (
                not config.product_id.sale_ok
                or config.product_id.company_id not in (config.company_id, self.env['res.company'])
            ):
                raise ValidationError(_('Choose a saleable product in the configuration company.'))
            if config.invoice_journal_id and (
                config.invoice_journal_id.type != 'sale'
                or config.invoice_journal_id.company_id != config.company_id
            ):
                raise ValidationError(_('Choose a sales journal in the configuration company.'))
            if config.payment_mode_id and (
                config.payment_mode_id.payment_type != 'inbound'
                or config.payment_mode_id.company_id != config.company_id
            ):
                raise ValidationError(
                    _('Choose an inbound payment mode in the configuration company.')
                )

    def unlink(self):
        if (
            self.env['afa.acollida.charge']
            .with_context(active_test=False)
            .search_count([('config_id', 'in', self.ids)])
        ):
            raise ValidationError(_('A configuration with imported charges cannot be deleted.'))
        return super().unlink()
