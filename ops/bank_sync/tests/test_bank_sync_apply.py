import sys
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bank_sync import BankSync


class FakeState:
    def __init__(self, fail_next_save=False):
        self.data = {'last_write_date': '2026-11-10 19:56:38'}
        self.links = {'scope': 'test-scope', 'lines': {}}
        self.fail_next_save = fail_next_save
        self.save_calls = 0

    def load(self):
        return deepcopy(self.data)

    def load_links(self):
        return deepcopy(self.links)

    def save_links(self, links):
        self.links = deepcopy(links)

    def save(self, data):
        if self.fail_next_save:
            self.fail_next_save = False
            raise RuntimeError('simulated checkpoint failure')
        self.save_calls += 1
        self.data = deepcopy(data)


class FakeSource:
    journal = 20

    def __init__(self, rows):
        self.client = SimpleNamespace(url='https://source.example.invalid')
        self.rows = rows

    def lines_since(self, checkpoint):
        return self.rows

    def messages(self, source_id):
        return []

    def identity_lines(self):
        return self.rows


class FakeTarget:
    journal = 12

    def __init__(self, rows=()):
        self.client = SimpleNamespace(url='https://destination.example.invalid')
        self.rows = {row['id']: deepcopy(row) for row in rows}
        self.create_line_calls = []
        self.create_message_calls = []
        self.next_id = max(self.rows, default=100) + 1

    def candidates(self, source, marker, known):
        return [
            row
            for row in self.rows.values()
            if row['id'] == known
            or row.get('unique_import_id') == marker
            or (row.get('date') == source['date'] and row.get('amount') == source['amount'])
        ]

    def messages(self, destination_id):
        return []

    def create_line(self, payload):
        self.create_line_calls.append(deepcopy(payload))
        destination_id = self.next_id
        self.next_id += 1
        self.rows[destination_id] = {
            **payload,
            'id': destination_id,
            'journal_id': (self.journal, 'Destination'),
        }
        return destination_id

    def create_message(self, payload):
        self.create_message_calls.append(deepcopy(payload))

    def partner_id(self, name):
        return False


def source_line(line_id, date, amount, payment_ref='Source transaction'):
    return {
        'id': line_id,
        'journal_id': (20, 'Source'),
        'date': date,
        'create_date': '2026-11-11 10:00:00',
        'write_date': '2026-11-11 10:00:00',
        'amount': amount,
        'payment_ref': payment_ref,
        'ref': f'bank-{line_id}',
        'narration': False,
        'partner_id': False,
        'partner_name': False,
    }


class BankSyncApplyTests(unittest.TestCase):
    def make_sync(self, source_rows, destination_rows=(), fail_next_save=False):
        source = FakeSource(source_rows)
        target = FakeTarget(destination_rows)
        state = FakeState(fail_next_save=fail_next_save)
        return BankSync(source, target, state, 'test-scope'), target, state

    def test_dry_run_plans_a_new_line_without_writing(self):
        sync, target, state = self.make_sync([source_line(1, '2026-11-11', 12.5)])

        result = sync.run()

        self.assertEqual(result['new_lines'], 1)
        self.assertFalse(result['checkpoint_advanced'])
        self.assertEqual(target.create_line_calls, [])
        self.assertEqual(target.create_message_calls, [])
        self.assertEqual(state.save_calls, 0)

    def test_retry_after_checkpoint_failure_does_not_duplicate_line(self):
        sync, target, state = self.make_sync(
            [source_line(1, '2026-11-11', 12.5)],
            fail_next_save=True,
        )

        with self.assertRaisesRegex(RuntimeError, 'simulated checkpoint failure'):
            sync.run(apply=True)
        result = sync.run(apply=True)

        self.assertEqual(len(target.create_line_calls), 1)
        self.assertEqual(result['existing_lines'], 1)
        self.assertTrue(result['checkpoint_advanced'])
        self.assertEqual(state.data['last_write_date'], '2026-11-11 10:00:00')

    def test_ambiguous_legacy_match_aborts_before_any_destination_write(self):
        source_rows = [
            source_line(1, '2026-11-11', 12.5),
            source_line(2, '2025-10-20', 75.0, payment_ref='Source label'),
        ]
        legacy_row = {
            'id': 700,
            'journal_id': (12, 'Destination'),
            'date': '2025-10-20',
            'amount': 75.0,
            'payment_ref': 'Different legacy label',
            'ref': False,
        }
        sync, target, state = self.make_sync(source_rows, [legacy_row])

        with self.assertRaisesRegex(RuntimeError, 'different description'):
            sync.run(apply=True)

        self.assertEqual(target.create_line_calls, [])
        self.assertEqual(target.create_message_calls, [])
        self.assertEqual(state.save_calls, 0)
