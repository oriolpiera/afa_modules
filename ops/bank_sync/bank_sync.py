"""Conservative bank import: default to planning, never overwrite bank lines."""

import hashlib
import html
import json
import os
import tempfile
import urllib.parse
from datetime import date, datetime, timezone
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar


class SafeHTML(HTMLParser):
    allowed: ClassVar[set[str]] = {
        'div',
        'small',
        'b',
        'strong',
        'i',
        'em',
        'p',
        'br',
        'span',
        'ul',
        'ol',
        'li',
        'blockquote',
        'table',
        'thead',
        'tbody',
        'tr',
        'th',
        'td',
        'a',
        'pre',
        'code',
    }
    suppressed: ClassVar[set[str]] = {'script', 'style', 'iframe', 'object', 'embed', 'svg', 'math'}

    def __init__(self, source_url=None, allowed_urls=()):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.depth = 0
        self.source_url = source_url
        self.allowed_origins = {
            origin for origin in (self._origin(url) for url in allowed_urls) if origin
        }

    @staticmethod
    def _origin(url):
        try:
            parsed = urllib.parse.urlsplit(url)
            if (
                parsed.scheme != 'https'
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                return None
            return parsed.scheme, parsed.hostname, parsed.port or 443
        except (TypeError, ValueError):
            return None

    def handle_starttag(self, tag, attributes):
        if tag in self.suppressed:
            self.depth += 1
        if self.depth or tag not in self.allowed:
            return
        suffix = ''
        if tag == 'a':
            href = dict(attributes).get('href') or ''
            if self.source_url and href.startswith('/') and not href.startswith('//'):
                href = urllib.parse.urljoin(self.source_url.rstrip('/') + '/', href)
            try:
                parsed = urllib.parse.urlsplit(href)
            except ValueError:
                parsed = None
            origin = self._origin(href)
            if parsed and origin in self.allowed_origins:
                suffix = f' href="{html.escape(href, quote=True)}" rel="noopener noreferrer"'
        self.output.append(f'<{tag}{suffix}>')

    def handle_endtag(self, tag):
        if tag in self.suppressed and self.depth:
            self.depth -= 1
            return
        if not self.depth and tag in self.allowed and tag != 'br':
            self.output.append(f'</{tag}>')

    def handle_startendtag(self, tag, attributes):
        self.handle_starttag(tag, attributes)
        if tag != 'br':
            self.handle_endtag(tag)

    def handle_data(self, data):
        if not self.depth:
            self.output.append(html.escape(data))


def safe_html(value, source_url=None, allowed_urls=()):
    parser = SafeHTML(source_url=source_url, allowed_urls=allowed_urls)
    parser.feed(value or '')
    parser.close()
    return ''.join(parser.output)


class CanonicalHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attributes):
        semantic = sorted(
            (key, value or '') for key, value in attributes if key in {'href', 'src', 'alt'}
        )
        self.parts.append(('start', tag, tuple(semantic)))

    def handle_startendtag(self, tag, attributes):
        self.handle_starttag(tag, attributes)
        if tag not in {'br', 'hr', 'img', 'input'}:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag not in {'br', 'hr', 'img', 'input'}:
            self.parts.append(('end', tag))

    def handle_data(self, data):
        text = ' '.join(data.split())
        if text:
            self.parts.append(('text', text))


def canonical_html(value, source_url=None, allowed_urls=()):
    parser = CanonicalHTML()
    parser.feed(safe_html(value, source_url=source_url, allowed_urls=allowed_urls))
    parser.close()
    return tuple(parser.parts)


class JsonState:
    def __init__(self, path, scope):
        self.path = Path(path)
        self.scope = scope

    def load(self):
        self.snapshot = self.path.read_bytes()
        data = json.loads(self.snapshot)
        try:
            datetime.strptime(data['last_write_date'], '%Y-%m-%d %H:%M:%S').replace(
                tzinfo=timezone.utc
            )
        except (KeyError, TypeError, ValueError):
            raise RuntimeError('A valid owner-managed UTC checkpoint is required') from None
        return data

    def save(self, data):
        if self.path.read_bytes() != self.snapshot:
            raise RuntimeError('Owner checkpoint changed during execution; preserving the edit')
        self._atomic(self.path, data)

    def load_links(self):
        path = self.path.parent / 'sync_links.json'
        if not path.exists():
            return {'scope': self.scope, 'lines': {}}
        data = json.loads(path.read_text())
        if data.get('scope') != self.scope:
            raise RuntimeError('Integration scope differs from the saved identity mapping')
        return data

    def save_links(self, data):
        self._atomic(self.path.parent / 'sync_links.json', data)

    @staticmethod
    def _atomic(path, data):
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.sync-state-')
        with os.fdopen(descriptor, 'w') as output:
            json.dump(data, output, indent=2)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)


class BankSync:
    def __init__(self, source, target, state, scope, source_journal=None, target_journal=None):
        self.source = source
        self.target = target
        self.state = state
        self.scope = scope
        self.source_journal = source_journal if source_journal is not None else source.journal
        self.target_journal = target_journal if target_journal is not None else target.journal
        self.source_url = source.client.url
        self.target_url = target.client.url
        self.allowed_link_urls = (self.source_url, self.target_url)

    @staticmethod
    def journal_id(row):
        value = row['journal_id']
        return value[0] if isinstance(value, (list, tuple)) else value

    def _legacy_matches(self, source, rows):
        reference = source.get('payment_ref') or ''
        matches = []
        monetary_legacy = []
        for row in rows:
            if str(row.get('unique_import_id') or '').startswith(f'afa-bank-sync:{self.scope}:'):
                continue
            label = row.get('payment_ref') or ''
            same_money = row['date'] == source['date'] and Decimal(str(row['amount'])) == Decimal(
                str(source['amount'])
            )
            if same_money:
                monetary_legacy.append(row)
            same_label = (
                label == reference
                or (
                    bool(reference)
                    and label.startswith(reference + ' [Contacte: ')
                    and label.endswith(']')
                )
                or (
                    not reference
                    and label.startswith('[Contacte: ')
                    and label.endswith(']')
                    and source.get('ref')
                    and row.get('ref') == source['ref']
                )
            )
            if same_money and same_label:
                matches.append(row)
        return reference, matches, monetary_legacy

    def _resolve_legacy(self, source, rows):
        reference, matches, monetary_legacy = self._legacy_matches(source, rows)
        if not matches and monetary_legacy:
            raise RuntimeError(
                'Ambiguous legacy monetary match has a different description; '
                'manual review required'
            )
        if len(matches) > 1 and source.get('ref'):
            exact = [row for row in matches if row.get('ref') == source['ref']]
            if len(exact) == 1:
                matches = exact
        if len(matches) > 1:
            raise RuntimeError('Ambiguous legacy destination matches; manual review required')
        if matches:
            self._validate_legacy_match(source, reference, matches[0])
        return matches[0] if matches else None

    def _validate_legacy_match(self, source, reference, match):
        if not reference.strip() and not source.get('ref'):
            raise RuntimeError('Insufficient legacy identity; manual review required')
        if source.get('ref') and match.get('ref') != source['ref']:
            raise RuntimeError('Legacy reference differs; manual review required')
        equivalent_sources = [
            row
            for row in self.source.identity_lines()
            if row['date'] == source['date']
            and Decimal(str(row['amount'])) == Decimal(str(source['amount']))
            and (row.get('payment_ref') or '') == reference
            and (not source.get('ref') or row.get('ref') == source['ref'])
        ]
        if len(equivalent_sources) != 1:
            raise RuntimeError('Multiple source records may claim this legacy identity')

    def resolve(self, source, links):
        marker = f'afa-bank-sync:{self.scope}:{source["id"]}'
        known = links['lines'].get(str(source['id']))
        candidates = getattr(self.target, 'candidates', None)
        all_rows = candidates(source, marker, known) if candidates else self.target.lines()
        if any(
            (row.get('unique_import_id') == marker or known == row['id'])
            and self.journal_id(row) != self.target_journal
            for row in all_rows
        ):
            raise RuntimeError('Saved destination identity moved outside the approved journal')
        rows = [row for row in all_rows if self.journal_id(row) == self.target_journal]
        identified = [
            row for row in rows if row.get('unique_import_id') == marker or known == row['id']
        ]
        if known and not identified:
            raise RuntimeError(
                'Previously mapped destination line is missing; manual review required'
            )
        if identified:
            if len(identified) != 1:
                raise RuntimeError('Multiple destination identities; manual review required')
            row = identified[0]
            if row['date'] != source['date'] or Decimal(str(row['amount'])) != Decimal(
                str(source['amount'])
            ):
                raise RuntimeError('Existing financial values differ; no overwrite is allowed')
            return row
        return self._resolve_legacy(source, rows)

    def copy_messages(self, source_id, destination_id, apply):
        existing = self.target.messages(destination_id) if destination_id else []
        identifiers = {message.get('message_id') for message in existing}
        bodies = {
            canonical_html(message.get('body') or '', self.source_url, self.allowed_link_urls)
            for message in existing
        }
        count = 0
        for message in self.source.messages(source_id):
            body = message.get('body') or ''
            if not isinstance(body, str) or not body.strip():
                continue
            body = safe_html(body, self.source_url, self.allowed_link_urls)
            author = message.get('author_id') or [False, 'Origen']
            rendered = (
                '<div><small><b>[Sincronitzat] Autor:</b> '
                f'{html.escape(author[1])} ({html.escape(message.get("date") or "")})'
                f'</small><br/>{body}</div>'
            )
            content = hashlib.sha256(rendered.encode()).hexdigest()[:20]
            target_host = urllib.parse.urlsplit(self.target_url).hostname
            identifier = f'<afa-bank-sync.{self.scope}.{message["id"]}.{content}@{target_host}>'
            canonical = canonical_html(rendered, self.source_url, self.allowed_link_urls)
            if identifier in identifiers or canonical in bodies:
                continue
            count += 1
            if apply:
                self.target.create_message(
                    {
                        'model': 'account.bank.statement.line',
                        'res_id': destination_id,
                        'body': rendered,
                        'message_id': identifier,
                        'message_type': 'comment',
                        'subtype_id': 2,
                    }
                )
            identifiers.add(identifier)
            bodies.add(canonical)
        return count

    def run(self, apply=False):
        state = self.state.load()
        checkpoint = state['last_write_date']
        links = self.state.load_links()
        rows = self.source.lines_since(checkpoint)
        # Resolve the whole batch before creating any financial records.
        claimed = {}
        for row in rows:
            if self.journal_id(row) != self.source_journal:
                raise RuntimeError('Unexpected source journal; no import allowed')
            if type(row.get('id')) is not int or row['id'] < 1:
                raise RuntimeError('Invalid source identity')
            try:
                date.fromisoformat(row['date'])
                datetime.strptime(row['create_date'], '%Y-%m-%d %H:%M:%S').replace(
                    tzinfo=timezone.utc
                )
                datetime.strptime(row['write_date'], '%Y-%m-%d %H:%M:%S').replace(
                    tzinfo=timezone.utc
                )
                amount = Decimal(str(row['amount']))
                if not amount.is_finite():
                    raise ValueError
            except (KeyError, TypeError, ValueError, ArithmeticError):
                raise RuntimeError('Invalid source banking values; no import allowed') from None
            if row['write_date'] < checkpoint:
                raise RuntimeError('Source result precedes the owner checkpoint')
            existing = self.resolve(row, links)
            if existing:
                previous = claimed.setdefault(existing['id'], row['id'])
                if previous != row['id']:
                    raise RuntimeError('Distinct source lines claim the same legacy line')
        result = {
            'dry_run': not apply,
            'source_lines': len(rows),
            'new_lines': 0,
            'existing_lines': 0,
            'new_messages': 0,
            'checkpoint_advanced': False,
        }
        for row in rows:
            marker = f'afa-bank-sync:{self.scope}:{row["id"]}'
            existing = self.resolve(row, links)
            if existing:
                result['existing_lines'] += 1
                destination_id = existing['id']
            else:
                result['new_lines'] += 1
                destination_id = None
                if apply:
                    payload = {
                        key: row.get(key) or False
                        for key in ('date', 'amount', 'payment_ref', 'ref', 'narration')
                    }
                    payload['amount'] = float(row['amount'])
                    payload.update(journal_id=self.target_journal, unique_import_id=marker)
                    payload['narration'] = (
                        safe_html(
                            row.get('narration') or '',
                            self.source_url,
                            self.allowed_link_urls,
                        )
                        or False
                    )
                    source_partner = row.get('partner_id')
                    name = source_partner[1] if source_partner else row.get('partner_name') or ''
                    if name:
                        payload['partner_name'] = name
                        partner = self.target.partner_id(name)
                        if partner:
                            payload['partner_id'] = partner
                    destination_id = self.target.create_line(payload)
            if apply:
                links['lines'][str(row['id'])] = destination_id
                self.state.save_links(links)
            result['new_messages'] += self.copy_messages(row['id'], destination_id, apply)
            checkpoint = max(checkpoint, row['write_date'])
        if apply and rows:
            state['last_write_date'] = checkpoint
            self.state.save(state)
            result['checkpoint_advanced'] = True
        return result


def main():
    import argparse
    import fcntl

    from odoo_gateway import SourceGateway, TargetGateway, journal_currency
    from probe_access import load_configuration

    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--apply', action='store_true', help='Explicitly permit new destination records'
    )
    mode.add_argument('--dry-run', action='store_true', help='Read-only planning (the default)')
    arguments = parser.parse_args()
    configuration, _ = load_configuration(arguments.config, arguments.state)
    scope = hashlib.sha256(
        '|'.join(
            configuration[key]
            for key in (
                'SRC_URL',
                'SRC_DB',
                'JOURNAL_ID_ORIGIN',
                'DST_URL',
                'DST_DB',
                'JOURNAL_ID_DESTINATION',
            )
        ).encode()
    ).hexdigest()[:16]
    source = SourceGateway(configuration)
    target = TargetGateway(configuration, scope, apply=arguments.apply)
    if journal_currency(source.client, source.journal) != journal_currency(
        target.client, target.journal
    ):
        raise RuntimeError('Bank journal currencies differ; no automatic conversion is permitted')
    state = JsonState(arguments.state, scope)
    if arguments.apply:
        descriptor = os.open(
            arguments.state.parent / 'sync.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, 'w') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(
                    json.dumps({'status': 'skipped', 'reason': 'another execution holds the lock'})
                )
                return
            result = BankSync(source, target, state, scope).run(apply=True)
    else:
        result = BankSync(source, target, state, scope).run()
    print(json.dumps({'status': 'ok', **result}, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:  # noqa: BLE001 - hide remote tracebacks and sensitive values
        # Remote bodies, arbitrary values and tracebacks can contain credentials
        # or banking details. RuntimeError messages in this module are fixed policy text.
        message = (
            str(error)
            if isinstance(error, RuntimeError)
            else 'Execution failed; inspect configuration privately'
        )
        print(
            json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'reason': message})
        )
        raise SystemExit(1) from None
