from odoo import fields, models


class AfaExtracurricularImportLine(models.TransientModel):
    _name = 'afa.extracurricular.import.line'
    _description = 'Extracurricular Enrollment Import Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'afa.extracurricular.import.wizard', required=True, ondelete='cascade', index=True
    )
    sequence = fields.Integer(default=10)
    course = fields.Char()
    student_name = fields.Char()
    phone = fields.Char()
    activity_name = fields.Char()
    group_name = fields.Char()
    course_id = fields.Many2one('afa.school.course', string='Matched Course', readonly=True)
    student_id = fields.Many2one('res.partner', readonly=True)
    service_id = fields.Many2one('afa.service', readonly=True)
    group_id = fields.Many2one('afa.service.group', readonly=True)
    join_window_id = fields.Many2one('afa.service.window', readonly=True)
    action = fields.Selection(
        [('create', 'Create'), ('skip', 'Skip'), ('error', 'Error')], readonly=True
    )
    error = fields.Text(readonly=True)
