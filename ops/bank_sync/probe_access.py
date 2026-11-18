"""Read-only Odoo API probe. Never print credentials or banking values."""

import argparse
import json
import os
import re
import secrets
import stat
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ALLOWED_METHODS = {'read', 'search', 'search_read', 'search_count', 'fields_get'}
ALLOWED_MODELS = {
    'account.journal',
    'account.bank.statement.line',
    'res.company',
    'res.currency',
    'mail.message',
    'res.partner',
}


def _check_private_file(path, config_path):
    info = path.stat()
    mode = stat.S_IMODE(info.st_mode)
    credential_directory = os.environ.get('CREDENTIALS_DIRECTORY')
    leased = (
        path == config_path
        and credential_directory
        and path.parent == Path(credential_directory)
        and mode in {0o400, 0o440}
        and info.st_uid in {0, os.geteuid()}
        and info.st_gid in {0, os.getegid()}
        and not stat.S_IMODE(path.parent.stat().st_mode) & 0o007
    )
    if path.is_symlink() or (mode & 0o077 and not leased):
        raise RuntimeError('Configuration must remain private and not be a symlink')


def _read_configuration(config_path):
    values = {}
    for raw in config_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        key, value = line.split('=', 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _validate_endpoint(values, prefix, hostname_pattern):
    try:
        url = urllib.parse.urlsplit(values[prefix + '_URL'])
        port = url.port
    except (KeyError, ValueError):
        raise RuntimeError(f'Invalid {prefix} endpoint') from None
    expected_host = values.get(prefix + '_ALLOWED_HOST', '').strip()
    if (
        not re.fullmatch(hostname_pattern, expected_host)
        or url.scheme != 'https'
        or url.hostname != expected_host.lower()
        or port not in (None, 443)
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in ('', '/')
    ):
        raise RuntimeError(f'Unexpected {prefix} endpoint; refusing an out-of-scope request')
    if not re.fullmatch(r'[1-9][0-9]*', values.get(prefix + '_USER_ID', '')):
        raise RuntimeError('Invalid configured API identity')


def _read_checkpoint(state_path):
    state = json.loads(state_path.read_text())
    checkpoint = state.get('last_write_date')
    if not isinstance(checkpoint, str):
        raise TypeError('Owner-managed checkpoint must be a string')
    try:
        datetime.strptime(checkpoint, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    except ValueError:
        raise RuntimeError('Invalid owner-managed UTC checkpoint') from None
    return checkpoint


def load_configuration(config_path, state_path):
    config_path = Path(config_path)
    state_path = Path(state_path)
    for path in (config_path, state_path):
        _check_private_file(path, config_path)

    values = _read_configuration(config_path)
    for key in ('SRC_API_KEY', 'DST_API_KEY', 'SRC_DB', 'DST_DB'):
        if not values.get(key):
            raise RuntimeError(f'Missing required private configuration: {key}')
    hostname_pattern = (
        r'(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)'
        r'(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*'
    )
    for prefix in ('SRC', 'DST'):
        _validate_endpoint(values, prefix, hostname_pattern)
    for key in ('JOURNAL_ID_ORIGIN', 'JOURNAL_ID_DESTINATION'):
        if not re.fullmatch(r'[1-9][0-9]*', values.get(key, '')):
            raise RuntimeError('Invalid configured journal')
    checkpoint = _read_checkpoint(state_path)
    return values, checkpoint


class ReadOnlyOdoo:
    def __init__(self, configuration, prefix):
        self.label = prefix
        self.url = configuration[prefix + '_URL'].rstrip('/')
        self.database = configuration[prefix + '_DB']
        self.user_id = int(configuration[prefix + '_USER_ID'])
        self.api_key = configuration[prefix + '_API_KEY']

    def request(self, service, method, arguments):
        payload = {
            'jsonrpc': '2.0',
            'method': 'call',
            'id': secrets.randbits(31),
            'params': {'service': service, 'method': method, 'args': arguments},
        }
        request = urllib.request.Request(
            self.url + '/jsonrpc',
            json.dumps(payload).encode(),
            {'Content-Type': 'application/json', 'User-Agent': 'AFA-bank-sync-readonly-probe'},
        )
        try:
            opener = urllib.request.build_opener(NoRedirectHandler)
            with opener.open(request, timeout=30) as response:
                content = response.read(16 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as error:
            raise RuntimeError(
                f'{self.label}: HTTP status {error.code}; response contents hidden'
            ) from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError(
                f'{self.label}: verified HTTPS connection failed; details hidden'
            ) from None
        if len(content) > 16 * 1024 * 1024:
            raise RuntimeError('Unexpectedly large metadata response')
        try:
            result = json.loads(content)
        except (ValueError, UnicodeError):
            raise RuntimeError(f'{self.label}: response was not JSON; contents hidden') from None
        if 'error' in result:
            name = result['error'].get('data', {}).get('name', 'remote_error')
            if not isinstance(name, str) or not re.fullmatch(
                r'[A-Za-z_][A-Za-z0-9_.]{0,100}', name
            ):
                name = 'remote_error'
            raise RuntimeError(f'{self.label}: {name}; remote message and traceback hidden')
        return result['result']

    def execute(self, model, method, arguments, keywords=None):
        if model not in ALLOWED_MODELS or method not in ALLOWED_METHODS:
            raise RuntimeError('Read-only probe refuses this API operation')
        return self.request(
            'object',
            'execute_kw',
            [
                self.database,
                self.user_id,
                self.api_key,
                model,
                method,
                arguments,
                keywords or {},
            ],
        )


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    arguments = parser.parse_args()
    os.umask(0o077)
    configuration, checkpoint = load_configuration(arguments.config, arguments.state)
    report = {'read_only': True, 'checkpoint_modified': False, 'endpoints': {}}
    interesting = {
        'id',
        'date',
        'amount',
        'payment_ref',
        'ref',
        'narration',
        'partner_id',
        'partner_name',
        'create_date',
        'write_date',
        'unique_import_id',
        'is_reconciled',
    }
    for prefix, journal_key in (('SRC', 'JOURNAL_ID_ORIGIN'), ('DST', 'JOURNAL_ID_DESTINATION')):
        client = ReadOnlyOdoo(configuration, prefix)
        version = client.request('common', 'version', [])
        journal = client.execute(
            'account.journal',
            'read',
            [[int(configuration[journal_key])]],
            {'fields': ['id', 'type']},
        )
        if len(journal) != 1 or journal[0]['type'] != 'bank':
            raise RuntimeError(f'{prefix}: configured journal is not exactly one bank journal')
        fields = client.execute(
            'account.bank.statement.line', 'fields_get', [], {'attributes': ['type']}
        )
        count = client.execute(
            'account.bank.statement.line',
            'search_count',
            [
                [
                    ('journal_id', '=', int(configuration[journal_key])),
                ]
            ],
        )
        report['endpoints'][prefix] = {
            'server_version': version.get('server_version'),
            'bank_journal_verified': True,
            'journal_line_count': count,
            'supported_fields': {
                key: value['type'] for key, value in fields.items() if key in interesting
            },
        }
        if prefix == 'SRC':
            if (
                fields.get('write_date', {}).get('type') != 'datetime'
                or fields.get('create_date', {}).get('type') != 'datetime'
            ):
                raise RuntimeError('Source creation and modification timestamps must be available')
            report['source_rows_since_owner_checkpoint'] = client.execute(
                'account.bank.statement.line',
                'search_count',
                [
                    [
                        ('journal_id', '=', int(configuration[journal_key])),
                        ('write_date', '>=', checkpoint),
                    ]
                ],
            )
    output_path = arguments.output or arguments.state.parent / 'access-probe.json'
    with output_path.open('x') as output:
        json.dump(report, output, indent=2, sort_keys=True)
        output.write('\n')
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
