# AFA Voting

Family voting for Odoo 19 Community, integrated with `afa_family`. Each invited
family receives one ballot addressed to its `billing_partner_id`; options and
participants are frozen when the voting is published.

## Installation and setup

Install `afa_voting` from Apps or with the Odoo command line. It depends on
`afa_family`, `mail`, and `website`. Configure the outgoing mail server and make
sure each participating family's billing guardian has an email address. Grant
**AFA Voting Manager** to staff who create and administer ballots. Grant **AFA
Voting Results User** only to internal users who may view aggregate results.
Voting managers can additionally inspect invitations and identifiable votes.

Create a draft, add at least two options, select participating families in the
Participants tab or open **AFA Families → Families** and use **Add to Voting** on
a family list's **Actions** menu to select several families and choose a draft
voting. Set the start and end times, then
publish. Publishing creates invitations and queues
email. The cron closes open ballots after their deadline (within five minutes).
Managers can resend invitations to pending families; a resend rotates the
credential and invalidates the previous link. A billing guardian reassignment
while voting is open updates the pending invitation's recipient and rotates and
resends its link. Superseded credentials and recipient snapshots are retained in
manager-only invitation history with revoked status; only their hashes are
stored. A family that already voted remains unable to vote again.

## Private links and privacy

Invitation links are bearer credentials: anyone who possesses a link can use it.
The link does **not** independently verify the recipient's real-world identity.
Share it only with the intended guardian. Tokens are generated with a
cryptographically secure random generator and the invitation table stores only
their SHA-256 hashes. The bearer token is carried in the URL fragment, which is
not sent in the HTTP request; the landing page removes it from the address bar
and sends it in a POST body to keep it out of access logs and referrer headers.
During delivery, Odoo's standard mail queue necessarily
contains the link until the message is sent/cleaned up. The token is never
included in application logs. Public pages reveal only the ballot and options;
they do not reveal family names, recipients, individual votes, or aggregate
results. Submitted votes are final, identifiable to voting managers, and limited
to one per family.

## Results and exports

The Results tab shows participant and vote totals, pending count, participation
rate, and aggregate counts and percentages per option. Managers can export a
participant-status CSV and an aggregate-results CSV. Individual votes and
invitation records are restricted to voting managers.

The voting menu is nested under **AFA Families**. The backend interface has a
Catalan (`ca_ES`) translation.

## Tests

The repository's Odoo 19 test stack is documented in the root README. With
`compose.test.yaml`, run:

```sh
docker compose -f compose.test.yaml up -d db
docker compose -f compose.test.yaml run --rm odoo -d afa_voting_test -i afa_voting --load-language=ca_ES --test-enable --test-tags /afa_voting --stop-after-init --log-level=test --db_host=db --db_user=odoo --db_password=odoo
```
