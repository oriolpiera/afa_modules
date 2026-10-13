from odoo import fields, models


class AfaFamilyImportLine(models.TransientModel):
    _name = 'afa.family.import.line'
    _description = 'AFA Family Import Preview Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'afa.family.import.wizard', required=True, ondelete='cascade', index=True
    )
    sequence = fields.Integer(default=10)
    # Raw file values are kept verbatim so the preview shows exactly what was uploaded.
    family_name = fields.Char()
    role = fields.Char()
    is_billing = fields.Char()
    name = fields.Char()
    email = fields.Char()
    phone = fields.Char()
    course = fields.Char()
    iban = fields.Char()
    mandate_date = fields.Char()
    # Resolved during validation.
    course_id = fields.Many2one('afa.school.course', readonly=True)
    is_payer = fields.Boolean(readonly=True)
    action = fields.Selection(
        [
            ('create', 'Create'),
            ('skip', 'Skip (family already exists)'),
            ('error', 'Error'),
        ],
        default='create',
        readonly=True,
    )
    error = fields.Char(readonly=True)
