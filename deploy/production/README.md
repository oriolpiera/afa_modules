# Production deployment

This stack runs Odoo 19 Community, PostgreSQL 18, Caddy-managed HTTPS, and daily
local backups. It is separate from `compose.test.yaml` and must not use its
development credentials.

## Server layout

The Compose file is installed as `/opt/afa/compose.yaml`; paths in it expect:

- `/opt/afa/afa_modules`: a clean checkout of the intended `afa_modules` branch.
- `/opt/afa/.oca-bank-payment`: OCA bank-payment 19.0 at
  `fdd5d4040b235a4c688b2aec30611d57dd246b64`.
- `/opt/afa/.oca-account-payment`: OCA account-payment 19.0 at
  `376d01852a9c4b689683e697abc1488432459590`.
- `/opt/afa/.oca-account-reconcile`, `/opt/afa/.oca-bank-statement-import`,
  `/opt/afa/.oca-l10n-spain`, and `/opt/afa/.oca-web`: matching OCA 19.0
  repositories. The web checkout is pinned to
  `521be3733122c64cc19ec4f5aac5c49e1198f92b`.
- `/opt/afa/.oca-mis-builder`: OCA/mis-builder 19.0 at
  `e8e7e927c2c5553cf10a60129293cc6b9a7c5fc8`.
- `/opt/afa/Caddyfile`, `/opt/afa/odoo.conf`, and `/opt/afa/.env`.
- `/opt/afa/backups`: private local backup directory.

The `.env` file contains `DOMAIN` and random `POSTGRES_PASSWORD`,
`ODOO_MASTER_PASSWORD`, and `ODOO_LOGIN_PASSWORD` values and must be mode
`0600`. Set `DOMAIN` to the hostname pointed at this server. The Odoo config
holds the database and master passwords; keep it root-owned and readable only
by the Odoo container's group. Its `addons_path` must include
`/mnt/oca-payment`, `/mnt/oca-account-payment`, `/mnt/oca-reconcile`,
`/mnt/oca-import`, `/mnt/oca-spain`, `/mnt/oca-mis-builder`, and `/mnt/oca-web`,
matching the Compose mounts. Neither file belongs in Git or a backup shared
publicly.

## Initial startup

1. Install Docker Engine and Compose, then allow inbound SSH, HTTP, and HTTPS in
   the host/provider firewalls. Do not publish PostgreSQL or Odoo's ports.
2. Ensure the Caddy hostname resolves to this server and place the Compose file,
   Caddyfile, repository checkout, and pinned OCA checkout in the paths above.
3. Set the production hostname in `DOMAIN`, generate the three secrets, write
   the protected `.env` and `odoo.conf`, and validate the configuration:

   ```sh
   cd /opt/afa
   docker compose config -q
   docker compose pull
   docker compose up -d db
   docker compose --profile initialize run --rm initialize
   ```

   The initializer installs all thirteen AFA addons and the `mis_builder` and
   `l10n_es_mis_report` reporting modules without demo data into the new
   `afa_prod` database. Set the initial Odoo `admin` password from the protected
   `.env` before making the web service public:

   ```sh
   set -a && . ./.env && set +a
   docker compose run --rm --no-deps -e ODOO_LOGIN_PASSWORD odoo \
     odoo shell --config=/etc/odoo/odoo.conf \
     </opt/afa/set_admin_password.py
   ```
4. Start the application and reverse proxy:

   ```sh
   docker compose up -d
   ```

   Caddy obtains and renews the TLS certificate automatically. Verify
   `https://<hostname>/web/login` and the certificate from outside the server.

## Backups and operations

The backup service writes a PostgreSQL custom-format dump and a filestore
archive once per day, retains 14 days, and stores files under `/opt/afa/backups`
with owner-only access. These copies are on the same VPS and are not a substitute
for encrypted off-site backups. Regularly copy them to separate storage and test
restoration before importing real family or accounting data.

Inspect status and logs with `docker compose ps` and `docker compose logs`. Before
updating Odoo or addons, take and verify a backup, deploy a reviewed `main`
revision and its matching pinned OCA dependencies, then run the required module
upgrades before restarting the web service.

## Install Spanish financial report templates on an existing database

After deploying the pinned `.oca-mis-builder` checkout and Compose changes,
ensure `/mnt/oca-mis-builder` is present in the production `addons_path`.
Follow the backup and clean-checkout gates in the production runbook, then stop
Odoo and install the reporting modules on `afa_prod`:

```sh
docker compose stop odoo
docker compose run --rm --no-deps odoo --config=/etc/odoo/odoo.conf \
  -d afa_prod -i mis_builder,l10n_es_mis_report \
  --stop-after-init --workers=0 --max-cron-threads=1
docker compose up -d odoo
```

Do not run the initializer against an existing production database. The
Spanish templates are available under Accounting > Reporting > MIS after
installation; create a report and select the appropriate Spanish P&L template.

The Apps filter in Odoo only shows addons marked as applications. To install
OCA technical modules that do not set `application = True`, clear that filter
and search by the module's technical name.

## OCA web addons

The production stack mounts the pinned OCA/web 19.0 checkout at
`/mnt/oca-web`. To install `web_responsive`, update the Apps list and install
the technical module; its dependencies (`web`, `web_tour`, and `mail`) are part
of the standard Odoo installation.
