"""CSV parsing helpers for extracurricular enrollment imports."""

import base64
import csv
import io
import re
import unicodedata

from odoo import _
from odoo.exceptions import UserError

COLUMNS = ('course', 'student', 'phone', 'activity', 'group')
REQUIRED_COLUMNS = ('course', 'student', 'activity', 'group')

_ALIASES = {
    'course': 'course',
    'curs': 'course',
    'student': 'student',
    'student_name': 'student',
    'name': 'student',
    'nen': 'student',
    'alumne': 'student',
    'phone': 'phone',
    'phone_number': 'phone',
    'telefon': 'phone',
    'activity': 'activity',
    'extracurricular': 'activity',
    'extraescolar': 'activity',
    'group': 'group',
    'grup': 'group',
}


def _normalize_header(value):
    text = unicodedata.normalize('NFKD', value or '')
    text = ''.join(char for char in text if not unicodedata.combining(char)).lower()
    return re.sub(r'[^a-z0-9]+', '_', text).strip('_')


def parse_rows(raw):
    """Decode an uploaded CSV into dictionaries with canonical column names."""
    try:
        text = base64.b64decode(raw).decode('utf-8-sig', errors='replace')
    except (ValueError, TypeError) as error:
        raise UserError(_('The uploaded file is not a valid CSV.')) from error

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel

    rows = csv.reader(io.StringIO(text), dialect)
    header = None
    canonical_header = []
    records = []
    for row in rows:
        if not any((cell or '').strip() for cell in row):
            continue
        if header is None:
            header = row
            canonical_header = [_ALIASES.get(_normalize_header(cell)) for cell in row]
            recognized = [column for column in canonical_header if column]
            repeated = sorted({column for column in recognized if recognized.count(column) > 1})
            if repeated:
                raise UserError(_('The CSV contains repeated columns: %s.') % ', '.join(repeated))
            missing = [column for column in REQUIRED_COLUMNS if column not in recognized]
            if missing:
                raise UserError(_('The CSV is missing required columns: %s.') % ', '.join(missing))
            continue

        record = dict.fromkeys(COLUMNS, '')
        for column, value in zip(canonical_header, row, strict=False):
            if column:
                record[column] = (value or '').strip()
        records.append(record)

    if not records:
        raise UserError(_('The CSV contains no data rows.'))
    return records
