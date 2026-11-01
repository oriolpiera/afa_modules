from odoo import fields, models


class AfaAcollidaImportLine(models.TransientModel):
    _name = 'afa.acollida.import.line'
    _description = 'AFA Acollida Fee Import Preview Line'
    _order = 'source_row, month, id'

    wizard_id = fields.Many2one(
        'afa.acollida.import.wizard', required=True, ondelete='cascade', index=True
    )
    sequence = fields.Integer(default=10)
    source_row = fields.Integer(readonly=True)
    family_name = fields.Char(readonly=True)
    student_name = fields.Char(readonly=True)
    parent_name = fields.Char(readonly=True)
    course_name = fields.Char(readonly=True)
    tranche = fields.Char(readonly=True)
    weekly_hours = fields.Char(readonly=True)
    base_amount = fields.Monetary(readonly=True, currency_field='currency_id')
    month = fields.Date(readonly=True)
    amount = fields.Monetary(readonly=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='wizard_id.config_id.currency_id')
    student_id = fields.Many2one('res.partner', readonly=True)
    family_id = fields.Many2one('afa.family', readonly=True)
    action = fields.Selection(
        [('create', 'Import'), ('skip', 'Skip'), ('error', 'Error')], readonly=True
    )
    message = fields.Char(readonly=True)
    warnings = fields.Char(readonly=True)
    parse_error = fields.Char(readonly=True)
    error = fields.Char(readonly=True)
