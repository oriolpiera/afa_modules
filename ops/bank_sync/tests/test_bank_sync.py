import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bank_sync import canonical_html, safe_html
from odoo_gateway import SourceGateway
from probe_access import NoRedirectHandler, load_configuration


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.fields_requested = None

    def execute(self, model, method, arguments, keywords):
        self.fields_requested = keywords['fields']
        last_id = next(value[2] for value in arguments[0] if value[0] == 'id')
        return [row for row in self.rows if row['id'] > last_id]


class BankSyncSelectionTests(unittest.TestCase):
    def test_ignores_old_line_edits_but_keeps_new_or_new_dated_lines(self):
        checkpoint = '2026-11-10 19:56:38'
        rows = [
            {
                'id': 1,
                'date': '2025-10-21',
                'create_date': '2025-10-21 10:00:00',
                'write_date': '2026-11-11 10:00:00',
            },
            {
                'id': 2,
                'date': '2025-10-17',
                'create_date': '2026-11-11 10:00:00',
                'write_date': '2026-11-11 10:00:00',
            },
            {
                'id': 3,
                'date': '2026-11-11',
                'create_date': '2025-10-21 10:00:00',
                'write_date': '2026-11-11 10:00:00',
            },
            {
                'id': 4,
                'date': '2026-11-09',
                'create_date': '2025-10-21 10:00:00',
                'write_date': '2026-11-11 10:00:00',
            },
            {
                'id': 5,
                'date': '2025-10-17',
                'create_date': checkpoint,
                'write_date': '2026-11-11 10:00:00',
            },
        ]
        client = FakeClient(rows)
        gateway = SourceGateway.__new__(SourceGateway)
        gateway.client = client
        gateway.journal = 20

        result = gateway.lines_since(checkpoint)

        self.assertEqual([row['id'] for row in result], [2, 3, 5])
        self.assertIn('create_date', client.fields_requested)


class ConfigurationTests(unittest.TestCase):
    def write_private_files(self, directory, source_url, source_host):
        config_path = directory / 'bank-sync.env'
        config_path.write_text(
            f'SRC_URL={source_url}\n'
            f'SRC_ALLOWED_HOST={source_host}\n'
            'SRC_DB=source_database\nSRC_USER_ID=1\nSRC_API_KEY=placeholder\n'
            'DST_URL=https://destination.example.invalid\n'
            'DST_ALLOWED_HOST=destination.example.invalid\n'
            'DST_DB=destination_database\nDST_USER_ID=1\nDST_API_KEY=placeholder\n'
            'JOURNAL_ID_ORIGIN=1\nJOURNAL_ID_DESTINATION=2\n'
        )
        config_path.chmod(0o600)
        state_path = directory / 'sync_state.json'
        state_path.write_text(json.dumps({'last_write_date': '2026-11-10 19:56:38'}))
        state_path.chmod(0o600)
        return config_path, state_path

    def test_accepts_domains_from_private_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path, state_path = self.write_private_files(
                directory,
                'https://source.example.invalid',
                'source.example.invalid',
            )

            configuration, checkpoint = load_configuration(config_path, state_path)

        self.assertEqual(configuration['SRC_ALLOWED_HOST'], 'source.example.invalid')
        self.assertEqual(checkpoint, '2026-11-10 19:56:38')

    def test_rejects_url_outside_configured_host_allowlist(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path, state_path = self.write_private_files(
                directory,
                'https://unexpected.example.invalid',
                'source.example.invalid',
            )

            with self.assertRaisesRegex(RuntimeError, 'out-of-scope'):
                load_configuration(config_path, state_path)

    def test_html_links_use_configured_odoo_domains(self):
        cleaned = safe_html(
            '<a href="/web#id=1">source</a>'
            '<a href="https://destination.example.invalid/web">destination</a>'
            '<a href="https://outside.example.invalid/">outside</a>',
            source_url='https://source.example.invalid',
            allowed_urls=(
                'https://source.example.invalid',
                'https://destination.example.invalid',
            ),
        )

        self.assertIn('href="https://source.example.invalid/web#id=1"', cleaned)
        self.assertIn('href="https://destination.example.invalid/web"', cleaned)
        self.assertNotIn('href=', cleaned.split('>outside<')[1])

    def test_canonical_html_preserves_configured_internal_links(self):
        source = '<a href="/web#id=1">line</a>'
        destination = '<a href="https://source.example.invalid/web#id=1">line</a>'
        allowed = ('https://source.example.invalid', 'https://destination.example.invalid')

        self.assertEqual(
            canonical_html(source, 'https://source.example.invalid', allowed),
            canonical_html(destination, 'https://source.example.invalid', allowed),
        )

    def test_http_client_does_not_follow_redirects_with_api_credentials(self):
        handler = NoRedirectHandler()

        self.assertIsNone(
            handler.redirect_request(
                request=None,
                file=None,
                code=307,
                message='temporary redirect',
                headers={},
                new_url='https://outside.example.invalid/jsonrpc',
            )
        )


if __name__ == '__main__':
    unittest.main()
