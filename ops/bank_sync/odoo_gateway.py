"""Narrow Odoo RPC adapters: source is always read-only, destination is create-only."""

import unicodedata
from datetime import datetime, timezone

from probe_access import ReadOnlyOdoo

BANK_FIELDS = [
    'id',
    'journal_id',
    'date',
    'create_date',
    'amount',
    'payment_ref',
    'ref',
    'narration',
    'partner_id',
    'partner_name',
    'write_date',
    'unique_import_id',
    'is_reconciled',
]
CONTEXT = {
    'tracking_disable': True,
    'mail_create_nosubscribe': True,
    'mail_create_nolog': True,
    'mail_notify_force_send': False,
}


def read_all(client, model, domain, fields):
    rows = []
    last = 0
    while True:
        page = client.execute(
            model,
            'search_read',
            [domain + [('id', '>', last)]],
            {'fields': fields, 'limit': 500, 'order': 'id asc'},
        )
        if not page:
            break
        if any(type(row.get('id')) is not int or row['id'] <= last for row in page):
            raise RuntimeError('Invalid API pagination identity')
        rows.extend(page)
        if len(rows) > 25000:
            raise RuntimeError('Review bound exceeded; no automatic import permitted')
        last = page[-1]['id']
        if len(page) < 500:
            break
    return rows


def journal_currency(client, journal):
    rows = client.execute(
        'account.journal',
        'read',
        [[journal]],
        {'fields': ['id', 'type', 'currency_id', 'company_id']},
    )
    if len(rows) != 1 or rows[0]['type'] != 'bank':
        raise RuntimeError('Configured journal is not a bank journal')
    currency = rows[0]['currency_id']
    if not currency:
        company = client.execute(
            'res.company', 'read', [[rows[0]['company_id'][0]]], {'fields': ['currency_id']}
        )
        currency = company[0]['currency_id']
    result = client.execute('res.currency', 'read', [[currency[0]]], {'fields': ['name']})
    return result[0]['name']


class SourceGateway:
    def __init__(self, configuration):
        self.client = ReadOnlyOdoo(configuration, 'SRC')
        self.journal = int(configuration['JOURNAL_ID_ORIGIN'])
        self.population = None

    def lines_since(self, checkpoint):
        cutoff = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        rows = read_all(
            self.client,
            'account.bank.statement.line',
            [
                ('journal_id', '=', self.journal),
                ('write_date', '>=', checkpoint),
                ('write_date', '<=', cutoff),
            ],
            BANK_FIELDS,
        )
        checkpoint_date = checkpoint[:10]
        # Revisit newly created lines and newer bank dates, but ignore later
        # edits to older lines; the write-date checkpoint alone is too broad.
        relevant = [
            row for row in rows if row['create_date'] >= checkpoint or row['date'] > checkpoint_date
        ]
        return sorted(relevant, key=lambda row: (row['write_date'], row['id']))

    def identity_lines(self):
        if self.population is None:
            self.population = read_all(
                self.client,
                'account.bank.statement.line',
                [('journal_id', '=', self.journal)],
                ['id', 'date', 'amount', 'payment_ref', 'ref'],
            )
        return self.population

    def messages(self, line_id):
        return read_all(
            self.client,
            'mail.message',
            [
                ('model', '=', 'account.bank.statement.line'),
                ('res_id', '=', line_id),
                ('message_type', 'in', ['comment', 'notification']),
            ],
            ['id', 'body', 'author_id', 'date'],
        )


class TargetGateway:
    def __init__(self, configuration, scope, apply=False):
        self.client = ReadOnlyOdoo(configuration, 'DST')
        self.journal = int(configuration['JOURNAL_ID_DESTINATION'])
        self.scope = scope
        self.apply = apply

    def lines(self):
        return read_all(
            self.client,
            'account.bank.statement.line',
            [('journal_id', '=', self.journal)],
            BANK_FIELDS,
        )

    def candidates(self, source, marker, known):
        choices = [
            '|',
            ('unique_import_id', '=', marker),
            '&',
            ('journal_id', '=', self.journal),
            '&',
            ('date', '=', source['date']),
            ('amount', '=', source['amount']),
        ]
        if known:
            choices = ['|', ('id', '=', known)] + choices
        # Identity lookup is global so a mapping accidentally moved to a different
        # journal cannot silently be recreated. Financial legacy matches stay scoped.
        return read_all(self.client, 'account.bank.statement.line', choices, BANK_FIELDS)

    def messages(self, line_id):
        return read_all(
            self.client,
            'mail.message',
            [
                ('model', '=', 'account.bank.statement.line'),
                ('res_id', '=', line_id),
            ],
            ['id', 'body', 'message_id'],
        )

    def partner_id(self, name):
        def normalized(value):
            return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())

        variants = {name}
        if ',' in name:
            first, second = name.split(',', 1)
            variants.add(second.strip() + ' ' + first.strip())
        found = set()
        for variant in variants:
            rows = self.client.execute(
                'res.partner',
                'search_read',
                [
                    [
                        ('active', '=', True),
                        ('name', '=ilike', variant),
                    ]
                ],
                {'fields': ['id', 'name'], 'limit': 25},
            )
            if len(rows) == 25:
                return False
            found.update(
                row['id'] for row in rows if normalized(row['name']) == normalized(variant)
            )
        return next(iter(found)) if len(found) == 1 else False

    def _create(self, model, payload):
        if not self.apply or model not in {'account.bank.statement.line', 'mail.message'}:
            raise RuntimeError('Write forbidden outside explicit destination apply mode')
        return self.client.request(
            'object',
            'execute_kw',
            [
                self.client.database,
                self.client.user_id,
                self.client.api_key,
                model,
                'create',
                [payload],
                {'context': CONTEXT},
            ],
        )

    def create_line(self, payload):
        if payload.get('journal_id') != self.journal or not str(
            payload.get('unique_import_id', '')
        ).startswith(f'afa-bank-sync:{self.scope}:'):
            raise RuntimeError('Destination create escaped the approved journal or identity scope')
        result = self._create('account.bank.statement.line', payload)
        if isinstance(result, list):
            if len(result) != 1:
                raise RuntimeError('Unexpected bank-line create response')
            result = result[0]
        if type(result) is not int or result < 1:
            raise RuntimeError('Invalid created destination identity')
        return result

    def create_message(self, payload):
        if payload.get('model') != 'account.bank.statement.line':
            raise RuntimeError('Comment target is outside the approved model')
        rows = self.client.execute(
            'account.bank.statement.line', 'read', [[payload['res_id']]], {'fields': ['journal_id']}
        )
        if len(rows) != 1 or rows[0]['journal_id'][0] != self.journal:
            raise RuntimeError('Comment target is outside the approved bank journal')
        return self._create('mail.message', payload)
