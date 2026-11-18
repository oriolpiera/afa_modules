# AFA bank statement synchronization

These scripts copy bank statement lines and missing chatter comments from one
Odoo instance to another. Configuration and runtime state must stay outside
the repository; the checked-in environment file is only a placeholder template.

## Configure privately

1. Copy `bank-sync.env.example` to a private directory outside this checkout.
2. Set the two Odoo URLs, their exact allowed hostnames, database names, API
   users and keys, and bank journal IDs.
3. Create the state directory with mode `0700`, then create `sync_state.json`
   inside it with mode `0600` or stricter.

The initial state file must exist before the first run:

```json
{
  "last_write_date": "2026-01-01 00:00:00"
}
```

Replace the example with the intended UTC cutover time in `YYYY-MM-DD HH:MM:SS`
format. The watermark selects lines created since that time or with a bank date
after its date. An earlier watermark requests more history and may encounter
legacy-match safeguards; a later watermark can skip lines. Do not move it
forward just to bypass a failed import.

The configured URL must use HTTPS on port 443, contain no credentials, query,
or fragment, and its hostname must exactly match the corresponding
`*_ALLOWED_HOST`. The scripts do not contain deployment domains.

## Run

Always review the dry-run before permitting destination writes:

```sh
python3 bank_sync.py \
  --config /private/path/bank-sync.env \
  --state /private/state/sync_state.json \
  --dry-run
```

Only after reviewing the counts, explicitly use `--apply` to create missing
bank lines and comments. Existing bank lines are never overwritten. The sync
selects lines created since the checkpoint or whose bank date is newer than
the checkpoint date; write-date-only changes to older lines are ignored.

`probe_access.py` performs read-only endpoint and field checks. Its JSON report
defaults to `access-probe.json` beside the state file; use a private state
directory or provide `--output` explicitly.

## Cron installer

`install_cron.py` changes a user's crontab and must be run as root. It requires
an existing private backup directory, a service unit, a user, and a five-field
UTC cron schedule. Review the proposed schedule and service before running it;
the installer refuses duplicate entries and preserves a private snapshot.

The cron entry uses `sudo -n /usr/bin/systemctl start <service>`. If the selected
cron user is not root, grant only that command for the configured service using
`visudo`, for example:

```sudoers
<cron-user> ALL=(root) NOPASSWD: /usr/bin/systemctl start <service>.service
```

Replace both placeholders. Verify permission without starting the service:

```sh
sudo -u <cron-user> sudo -n -l /usr/bin/systemctl start <service>.service
```

## Tests

Run the standard-library regression tests with:

```sh
python3 -m unittest discover -s tests -v
```
