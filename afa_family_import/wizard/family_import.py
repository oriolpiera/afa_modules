from psycopg2 import IntegrityError

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

from .. import file_format


class AfaFamilyImportWizard(models.TransientModel):
    _name = 'afa.family.import.wizard'
    _description = 'Initial Family Load Assistant'

    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company, required=True
    )
    create_mandates = fields.Boolean(
        string='Create SEPA Mandates',
        default=True,
        help='Validate a SEPA Core recurrent mandate for the billing guardian when the file '
        'carries an IBAN and a signature date.',
    )
    file = fields.Binary()
    filename = fields.Char()
    line_ids = fields.One2many('afa.family.import.line', 'wizard_id', readonly=True)

    def _check_manager(self):
        if not self.env.su and not self.env.user.has_group('afa_family.group_family_manager'):
            raise AccessError(_('Only family managers can load families.'))

    def _action(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_template(self):
        return {
            'type': 'ir.actions.act_url',
            'url': '/afa_family_import/template',
            'target': 'self',
        }

    def action_load(self):
        self.ensure_one()
        self._check_manager()
        if not self.file:
            raise UserError(_('Select a CSV or Excel file to load.'))
        records = file_format.parse_rows(self.file, self.filename)
        self.line_ids.unlink()
        self.env['afa.family.import.line'].create(
            [self._line_values(index, record) for index, record in enumerate(records, start=1)]
        )
        self.invalidate_recordset(['line_ids'])
        self._validate()
        return self._action()

    def _line_values(self, index, record):
        values = {'wizard_id': self.id, 'sequence': index * 10}
        for column in file_format.COLUMNS:
            values[column] = record[column]
        return values

    def action_confirm(self):
        self.ensure_one()
        self._check_manager()
        if not self.line_ids:
            raise UserError(_('Load a file before confirming.'))
        self._validate()
        if self.line_ids.filtered(lambda line: line.action == 'error'):
            return self._action()
        ids_by_family = {}
        for line in self.line_ids.filtered(lambda line: line.action == 'create'):
            ids_by_family.setdefault(line.family_name, []).append(line.id)
        if not ids_by_family:
            raise UserError(_('Every family in the file already exists; nothing was imported.'))
        line_model = self.env['afa.family.import.line']
        for line_ids in ids_by_family.values():
            self._create_family_group(line_model.browse(line_ids))
        self.invalidate_recordset(['line_ids'])
        if self.line_ids.filtered(lambda line: line.action == 'error'):
            return self._action()
        return {'type': 'ir.actions.act_window_close'}

    def _create_family_group(self, group):
        try:
            with self.env.cr.savepoint():
                self._create_family(group)
        except (UserError, IntegrityError) as error:
            self.env.invalidate_all()
            line_model = self.env['afa.family.import.line']
            line_model.browse(group.ids).write({'action': 'error', 'error': self._message(error)})

    def _create_family(self, group):
        partner_model = self.env['res.partner']
        payer_line = group.filtered('is_payer')
        payer = partner_model.create(
            {
                'name': payer_line.name,
                'email': payer_line.email or False,
                'phone': payer_line.phone or False,
                'afa_family_role': 'guardian',
            }
        )
        family = self.env['afa.family'].create(
            {'name': payer_line.family_name, 'billing_partner_id': payer.id}
        )
        partners = {payer_line.id: payer}
        for line in group - payer_line:
            values = {
                'name': line.name,
                'email': line.email or False,
                'phone': line.phone or False,
                'afa_family_id': family.id,
                'afa_family_role': line.role,
            }
            if line.course_id:
                values['afa_course_id'] = line.course_id.id
            partners[line.id] = partner_model.create(values)
        for line in group:
            if line.iban:
                self._create_bank_and_mandate(line, partners[line.id])

    def _create_bank_and_mandate(self, line, partner):
        bank = (
            self.env['res.partner.bank']
            .sudo()
            .create({'acc_number': line.iban, 'partner_id': partner.id})
        )
        if not line.is_payer or not self.create_mandates:
            return
        signature = self._signature_date(line.mandate_date)
        if not signature:
            return
        self.env['account.banking.mandate'].sudo().create(
            {
                'partner_bank_id': bank.id,
                'company_id': self.company_id.id,
                'format': 'sepa',
                'type': 'recurrent',
                'scheme': 'CORE',
                'signature_date': signature,
                'state': 'valid',
            }
        )

    def _validate(self):
        self.ensure_one()
        grouped = {}
        for line in self.line_ids.sorted('sequence', 'id'):
            grouped.setdefault(line.family_name, []).append(line)
        if not grouped:
            return
        existing = set(
            self.env['afa.family']
            .with_context(active_test=False)
            .search([('name', 'in', list(grouped))])
            .mapped('name')
        )
        line_model = self.env['afa.family.import.line']
        for key, group in grouped.items():
            recordset = line_model.browse([line.id for line in group])
            if key in existing:
                recordset.write({'action': 'skip', 'error': '', 'is_payer': False})
            else:
                self._validate_family(recordset)

    def _validate_family(self, group):
        row_errors = {}
        guardians = []
        billing = []
        unpaid = []
        for line in group:
            line.is_payer = False
            reason = self._validate_line(line)
            if reason:
                row_errors[line.id] = reason
            if line.role != 'guardian':
                if file_format.parse_bool(line.is_billing):
                    unpaid.append(line)
                continue
            guardians.append(line)
            if file_format.parse_bool(line.is_billing):
                billing.append(line)
        payer = self._payer_line(group, guardians, billing, unpaid, row_errors)
        if payer:
            payer.is_payer = True
            if payer.id not in row_errors:
                self._validate_mandate_date(payer, row_errors)
        for line in group:
            line.error = row_errors.get(line.id, '')
            line.action = 'error' if row_errors.get(line.id) else 'create'

    @staticmethod
    def _payer_line(group, guardians, billing, unpaid, row_errors):
        """Report the guardian and billing conflicts, and return the line that pays."""
        if not guardians:
            for line in group:
                row_errors.setdefault(line.id, _('A family needs at least one guardian.'))
            return None
        for line in unpaid:
            row_errors.setdefault(line.id, _('Only a guardian can pay the dues.'))
        if len(billing) > 1:
            for line in billing:
                row_errors.setdefault(line.id, _('More than one billing guardian is marked.'))
            return None
        if not billing and len(guardians) > 1:
            for line in guardians:
                row_errors.setdefault(line.id, _('Mark which guardian pays the dues.'))
            return None
        if len(billing) == 1:
            return billing[0]
        if len(guardians) == 1:
            return guardians[0]
        return None

    def _validate_mandate_date(self, line, row_errors):
        if not line.iban or not self.create_mandates:
            return
        if not line.mandate_date:
            row_errors[line.id] = _(
                'A billing guardian with an IBAN needs a mandate signature date.'
            )
            return
        signature = self._signature_date(line.mandate_date)
        if not signature:
            message = _('The mandate date "%s" is not a valid date.')
            row_errors[line.id] = message % line.mandate_date
        elif signature > fields.Date.context_today(self):
            message = _('The mandate date "%s" is in the future.')
            row_errors[line.id] = message % line.mandate_date

    def _validate_line(self, line):
        if not line.family_name:
            return _('The family name is missing.')
        if line.role not in ('guardian', 'student'):
            return _('The role must be "guardian" or "student".')
        if not line.name:
            return _('The name is missing.')
        if line.email and not file_format.valid_email(line.email):
            return _('The email address "%s" is not valid.') % line.email
        if line.iban and not file_format.valid_iban(line.iban):
            return _('The IBAN "%s" is not valid.') % line.iban
        if line.role != 'student':
            if line.course:
                return _('Only students can have a school course.')
            line.course_id = False
            return ''
        if not line.course:
            return _('A student needs a school course.')
        course = self.env['afa.school.course'].search([('name', '=', line.course)], limit=1)
        if not course:
            return _('The school course "%s" does not exist.') % line.course
        line.course_id = course
        return ''

    @staticmethod
    def _signature_date(value):
        try:
            return fields.Date.to_date(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _message(error):
        return getattr(error, 'msg', None) or str(error)
