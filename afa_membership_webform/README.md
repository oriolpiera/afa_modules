# AFA Membership Web Form

This addon replaces the public Google Form with an Odoo website form and a
manager-reviewed membership application. Install it together with the AFA
Website, Family, Membership, School Courses, and SEPA addons.

Public submissions are stored as **Pending Review**. They do not create family
contacts or a mandate until an AFA Family Manager approves the application.
Approval creates or reuses an unassigned guardian matched by DNI, creates the
family and student contacts, records the selected school courses, and—when a
SEPA authorization was accepted—creates the payer's bank account and a draft
recurrent SEPA Core mandate. The mandate can cover membership dues and any
contracted Acollida or extracurricular services. A manager must validate the
mandate after confirming the bank accepts the electronic authorization process.
The application records the explicit authorization timestamp and terms version.
Rejected submissions create no family or contact records.

Configure the school's course ladder in **AFA Families → Configuration → School
Courses** before publishing the form; the course selector uses those records.

Application records, including DNI, student birth dates, and IBAN, are available
only to AFA Family Managers. The public route keeps Odoo's HTTP CSRF protection
enabled, validates all submitted values on the server, and never includes bank
details in notifications. A honeypot rejects basic automated submissions.
Student rows can be added dynamically; submissions are bounded to 20 students
to limit abusive requests.

## SEPA setup dependency

The electronic authorization text and evidence required by a creditor's bank
must be confirmed with the bank before using the generated mandates for live
collections. Configure the company, creditor identifier, payment mode, and
bank journal as described in the [`afa_sepa` guide](../afa_sepa/README.md).

## Local tests

Use a fresh database with the isolated Odoo 19 test stack:

```sh
docker compose -f compose.test.yaml run --rm odoo -d afa_membership_webform_test -i afa_membership_webform --test-enable --test-tags /afa_membership_webform --stop-after-init --log-level=test --db_host=db --db_user=odoo --db_password=odoo
```

Check the `odoo.tests.result` summary and confirm the application and website
tests ran. Odoo may report test failures without returning a failing process
exit code.
