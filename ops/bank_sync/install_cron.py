"""Add only the reviewed Ubuntu cron entry, preserving unrelated user work."""

import argparse
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BEGIN = '# BEGIN managed AFA bank synchronization'
END = '# END managed AFA bank synchronization'


def confirmation_message(schedule, service):
    return f'Installed one cron entry: {schedule} UTC, scoped to {service}.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', required=True, help='Linux account whose crontab will be updated')
    parser.add_argument('--service', required=True, help='systemd service unit to start')
    parser.add_argument(
        '--schedule', required=True, help='Five-field cron schedule, interpreted as UTC'
    )
    parser.add_argument(
        '--backup-dir',
        required=True,
        type=Path,
        help='Existing private directory for the crontab snapshot',
    )
    arguments = parser.parse_args()

    if os.geteuid() != 0:
        raise SystemExit('Run this installer as root')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*[$]?', arguments.user):
        raise SystemExit('Invalid Linux username')
    if not re.fullmatch(r'[A-Za-z0-9_.@-]+\.service', arguments.service):
        raise SystemExit('Invalid systemd service unit')
    schedule_fields = arguments.schedule.split()
    if len(schedule_fields) != 5 or any(
        not re.fullmatch(r'[0-9*/,-]+', field) for field in schedule_fields
    ):
        raise SystemExit('Schedule must contain five numeric cron fields')
    if not arguments.backup_dir.is_dir() or arguments.backup_dir.is_symlink():
        raise SystemExit('Backup directory must already exist and must not be a symlink')

    os.umask(0o077)
    timezone_name = subprocess.check_output(
        ['timedatectl', 'show', '--property=Timezone', '--value'],
        text=True,
    ).strip()
    if timezone_name not in {'UTC', 'Etc/UTC'}:
        raise SystemExit('Host cron timezone is not UTC; refusing an ambiguous schedule')
    result = subprocess.run(
        ['crontab', '-u', arguments.user, '-l'],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode and 'no crontab' not in result.stderr.lower():
        raise SystemExit('Could not read current Ubuntu crontab')
    original = result.stdout if result.returncode == 0 else ''
    if BEGIN in original or END in original or arguments.service in original:
        raise SystemExit('Bank cron entry already exists; review rather than overwrite it')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = arguments.backup_dir / f'{arguments.user}-crontab-before-bank-{stamp}.txt'
    with backup.open('x') as output:
        output.write(original)
    backup.chmod(0o600)
    entry = f'{arguments.schedule} /usr/bin/sudo -n /usr/bin/systemctl start {arguments.service}'
    updated = (
        original.rstrip('\n')
        + ('\n\n' if original else '')
        + BEGIN
        + '\n'
        + entry
        + '\n'
        + END
        + '\n'
    )
    check = subprocess.run(
        ['crontab', '-u', arguments.user, '-l'],
        text=True,
        capture_output=True,
        check=False,
    )
    if (check.stdout if check.returncode == 0 else '') != original:
        raise SystemExit('Ubuntu crontab changed during preparation; preserving the newer work')
    subprocess.run(['crontab', '-u', arguments.user, '-'], input=updated, text=True, check=True)
    actual = subprocess.check_output(['crontab', '-u', arguments.user, '-l'], text=True)
    if actual != updated:
        raise SystemExit(
            'Cron verification failed; original content retained in the private backup'
        )
    print(confirmation_message(arguments.schedule, arguments.service))


if __name__ == '__main__':
    main()
