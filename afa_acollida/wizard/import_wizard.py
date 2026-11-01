import hashlib
from collections import defaultdict
from datetime import date
from decimal import Decimal

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError

from . import file_format

_TRANCHES = {
    '1r': 1,
    'primer': 1,
    '1er': 1,
    '2n': 2,
    '2on': 2,
    'segon': 2,
}
_TRANCHE_PRICES = {1: Decimal('24.00'), 2: Decimal('43.00')}
_MONTH_SELECTION = [(str(number), name.title()) for name, number in file_format.MONTHS]


class AfaAcollidaImportWizard(models.TransientModel):
    _name = 'afa.acollida.import.wizard'
    _description = 'Import Fixed Acollida Fees'

    config_id = fields.Many2one('afa.acollida.config', required=True)
    import_month = fields.Selection(
        selection=_MONTH_SELECTION,
        required=True,
        default=lambda self: self._default_import_month(),
    )
    file = fields.Binary()
    filename = fields.Char()
    line_ids = fields.One2many('afa.acollida.import.line', 'wizard_id', readonly=True)
    preview_checksum = fields.Char(readonly=True, copy=False)
    preview_config_id = fields.Many2one('afa.acollida.config', readonly=True, copy=False)
    preview_month = fields.Selection(selection=_MONTH_SELECTION, readonly=True, copy=False)
    preview_message = fields.Char(readonly=True, copy=False)

    @api.model
    def _default_import_month(self):
        current_month = fields.Date.context_today(self).month
        return str(
            current_month
            if current_month in {number for _name, number in file_format.MONTHS}
            else 9
        )

    def _file_checksum(self):
        self.ensure_one()
        content = self.file or b''
        if isinstance(content, str):
            content = content.encode('ascii')
        return hashlib.sha256(content).hexdigest() if content else False

    @api.onchange('file', 'config_id', 'import_month')
    def _onchange_import_inputs(self):
        for wizard in self:
            if wizard.preview_checksum and (
                wizard.preview_checksum != wizard._file_checksum()
                or wizard.preview_config_id != wizard.config_id
                or wizard.preview_month != wizard.import_month
            ):
                wizard.line_ids = [Command.clear()]
                wizard.preview_checksum = False
                wizard.preview_config_id = False
                wizard.preview_month = False
                wizard.preview_message = _(
                    'The file or school year changed. Preview the import again before confirming.'
                )

    def _check_manager(self):
        if not self.env.su and not self.env.user.has_group('afa_family.group_family_manager'):
            raise AccessError(_('Only family managers can import Acollida fees.'))

    def _action(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_preview(self):
        self.ensure_one()
        self._check_manager()
        if not self.file:
            raise UserError(_('Select an Excel or CSV file to preview.'))
        if not self.config_id:
            raise UserError(_('Select the Acollida school-year configuration.'))
        records = file_format.parse_rows(self.file, self.filename, int(self.import_month))
        self.line_ids.unlink()
        self.preview_message = False
        values = []
        for record in records:
            row_values, parse_error = self._expand_record(record)
            for line_values in row_values:
                line_values.update(
                    {
                        'wizard_id': self.id,
                        'sequence': record['row_number'] * 100 + len(values),
                        'parse_error': parse_error,
                    }
                )
                values.append(line_values)
        self.env['afa.acollida.import.line'].create(values)
        self.invalidate_recordset(['line_ids'])
        self.preview_checksum = self._file_checksum()
        self.preview_config_id = self.config_id
        self.preview_month = self.import_month
        self._validate_lines()
        return self._action()

    def _expand_record(self, record):
        try:
            base_amount = file_format.parse_amount(record['base_amount'])
        except (TypeError, ValueError) as error:
            base_amount = None
            parse_error = str(error)
        else:
            parse_error = ''

        month_number = int(self.import_month)
        month_name = dict(_MONTH_SELECTION)[self.import_month]
        try:
            amount = file_format.parse_amount(record[f'month_{month_number}'])
        except (TypeError, ValueError) as error:
            parse_error = '; '.join(filter(None, (parse_error, str(error))))
            amount = None
        month = self._month_date(month_number)
        if not month:
            parse_error = '; '.join(
                filter(
                    None,
                    (parse_error, _('The service period does not include %s.') % month_name),
                )
            )

        common = {
            'source_row': record['row_number'],
            'family_name': record['family'],
            'student_name': record['student'],
            'parent_name': record['parent'],
            'course_name': record['course'],
            'tranche': record['tranche'],
            'weekly_hours': str(record['weekly_hours'] or ''),
            'base_amount': float(base_amount or 0),
        }
        if not amount:
            line_values = dict(
                common, amount=0, action='skip', message=_('No monthly amounts to import.')
            )
            return [line_values], parse_error
        return [dict(common, month=month, amount=float(amount))], parse_error

    def _month_date(self, month_number):
        self.ensure_one()
        period = self.config_id.period_id
        if not period.date_start or not period.date_end:
            return False
        matches = []
        for year in range(period.date_start.year, period.date_end.year + 1):
            try:
                candidate = date(year, month_number, 1)
            except ValueError:
                continue
            if period.date_start <= candidate <= period.date_end:
                matches.append(candidate)
        return matches[0] if len(matches) == 1 else False

    def _validate_lines(self):
        self.ensure_one()
        lines = self.line_ids.sorted(
            key=lambda line: (line.source_row, line.month or date.min, line.id)
        )
        if not lines:
            return
        families_by_key = self._families_by_key()
        existing = self.env['afa.acollida.charge'].search(
            [('config_id', '=', self.config_id.id), ('active', '=', True)]
        )
        existing_by_key = defaultdict(list)
        for charge in existing:
            existing_by_key[(charge.family_id.id, charge.month)].append(charge)
        by_row = defaultdict(list)
        for line in lines:
            by_row[line.source_row].append(line)
        resolved_family_rows = {}
        for row_lines in by_row.values():
            self._validate_row(
                row_lines,
                families_by_key,
                existing_by_key,
                resolved_family_rows,
            )

    def _families_by_key(self):
        families_by_key = defaultdict(list)
        for family in self.env['afa.family'].search([]):
            families_by_key[file_format.normalize_text(family.name)].append(family)
        return families_by_key

    def _validate_row(self, row_lines, families_by_key, existing_by_key, resolved_family_rows):
        row = row_lines[0]
        for line in row_lines:
            line.write(
                {
                    'family_id': False,
                    'action': 'error',
                    'message': '',
                    'warnings': '',
                    'error': '',
                }
            )
        parse_error = next((line.parse_error for line in row_lines if line.parse_error), False)
        if parse_error:
            self._mark_row_error(row_lines, parse_error)
            return
        if not any(line.month and line.amount for line in row_lines):
            row.write({'action': 'skip', 'message': _('No monthly amounts to import.')})
            return

        family, error = self._resolve_family(row, families_by_key)
        if error:
            self._mark_row_error(row_lines, error)
            return
        if not family.billing_partner_id:
            self._mark_row_error(row_lines, _('The family has no billing guardian in Odoo.'))
            return
        previous_row = resolved_family_rows.get(family.id)
        if previous_row:
            error = _('The family appears more than once in this import file.')
            self._mark_row_error(row_lines, error)
            self._mark_row_error(previous_row, error)
            return
        resolved_family_rows[family.id] = row_lines

        for line in row_lines:
            line.family_id = family
            line.warnings = self._row_warnings(
                row, monthly_amount=line.amount if line.month else False
            )
            self._validate_charge_line(line, family, existing_by_key)

    def _resolve_family(self, line, families_by_key):
        family_name = (line.family_name or '').strip()
        if not family_name:
            return False, _('Family is required.')
        families = families_by_key.get(file_format.normalize_text(family_name), [])
        if not families:
            return False, _('No family named "%s" was found.') % family_name
        if len(families) > 1:
            return False, _('More than one family named "%s" was found.') % family_name
        return families[0], False

    def _validate_charge_line(self, line, family, existing_by_key):
        if not line.month or not line.amount:
            line.write({'action': 'skip', 'message': _('No monthly amount to import.')})
            return
        existing = existing_by_key.get((family.id, line.month), [])
        if not existing:
            line.action = 'create'
        elif len(existing) == 1 and existing[0].amount == line.amount:
            line.write({'action': 'skip', 'message': _('This amount has already been imported.')})
        else:
            line.write(
                {
                    'action': 'error',
                    'error': _('An Acollida charge already exists for this family and month.'),
                }
            )

    @staticmethod
    def _mark_row_error(lines, message):
        for line in lines:
            line.write({'action': 'error', 'error': message, 'message': ''})

    def _row_warnings(self, line, monthly_amount=None):
        warnings = []
        if not (line.weekly_hours or '').strip():
            hours = None
            warnings.append(_('Weekly hours are missing.'))
        else:
            try:
                hours = file_format.parse_hours(line.weekly_hours)
            except (ValueError, TypeError):
                hours = None
                warnings.append(_('Weekly hours could not be interpreted.'))

        tranche_text = file_format.normalize_text(line.tranche)
        tranche = _TRANCHES.get(tranche_text)
        if not tranche_text:
            warnings.append(_('The tranche is missing.'))
        elif not tranche:
            warnings.append(_('The tranche is not recognized.'))
        expected_tranche = (1 if hours <= 5 else 2) if hours is not None else False
        if tranche and expected_tranche and tranche != expected_tranche:
            warnings.append(_('The tranche does not match the weekly hours.'))

        check_tranche = tranche or expected_tranche
        if check_tranche and line.base_amount:
            expected_base = float(_TRANCHE_PRICES[check_tranche])
            if line.base_amount != expected_base:
                warnings.append(_('The base monthly amount does not match the tranche.'))
            reduced_base = float(_TRANCHE_PRICES[check_tranche] * Decimal('0.75'))
            if monthly_amount and monthly_amount not in {expected_base, reduced_base}:
                warnings.append(_('The monthly amount differs from the base or three-week tariff.'))
        elif monthly_amount and not line.base_amount:
            warnings.append(_('The base monthly amount is missing.'))
        return '; '.join(warnings)

    def action_confirm(self):
        self.ensure_one()
        self._check_manager()
        if not self.line_ids:
            raise UserError(_('Preview a file before confirming the import.'))
        if (
            not self.preview_checksum
            or self.preview_checksum != self._file_checksum()
            or self.preview_config_id != self.config_id
            or self.preview_month != self.import_month
        ):
            self.line_ids.unlink()
            self.preview_checksum = False
            self.preview_config_id = False
            self.preview_month = False
            self.preview_message = _(
                'The file or school year changed. Preview the import again before confirming.'
            )
            return self._action()

        self._validate_lines()
        if self.line_ids.filtered(lambda line: line.action == 'error'):
            return self._action()
        to_import = self.line_ids.filtered(lambda line: line.action == 'create')
        if not to_import:
            self.preview_message = _('There are no new Acollida charges to import.')
            return self._action()

        for family in to_import.mapped('family_id').sorted('id'):
            self.env.cr.execute('SELECT id FROM afa_family WHERE id = %s FOR UPDATE', [family.id])
        self.env.invalidate_all()
        self._validate_lines()
        if self.line_ids.filtered(lambda line: line.action == 'error'):
            return self._action()
        to_import = self.line_ids.filtered(lambda line: line.action == 'create')
        if not to_import:
            self.preview_message = _('There are no new Acollida charges to import.')
            return self._action()
        self.env['afa.acollida.charge'].with_context(_afa_import_acollida_charges=True).create(
            [
                {
                    'config_id': self.config_id.id,
                    'family_id': line.family_id.id,
                    'month': line.month,
                    'amount': line.amount,
                    'base_amount': line.base_amount,
                    'tranche': line.tranche,
                    'weekly_hours': line.weekly_hours,
                    'parent_name': line.parent_name,
                }
                for line in to_import
            ]
        )
        return {'type': 'ir.actions.act_window_close'}
