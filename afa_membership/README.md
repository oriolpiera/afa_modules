# AFA Membership

`afa_membership` adds July–June school years, family-period dues invoices, and a
configurable manual membership mode to Odoo 19 Community. It depends on
`afa_family`, `account`, and `product`; `afa_family` can still be installed alone.

## Manager workflow

1. Install both addons and assign **AFA Family Manager** to staff managing
   families. Accounting access is also needed to create, post, and reconcile
   invoices; being a family manager alone does not grant accounting access.
2. Create a school year under **AFA Families → School Years**. For example,
   **2026/27** runs from **2026-07-01** through **2027-06-30**, inclusive.
3. Create a **Family Period Link** for that year. Choose a saleable dues product
   with a positive price and select **Create Dues Invoice**. The selected
   billing guardian becomes the invoice recipient at creation; later family
    payer changes do not rewrite that invoice. Only one non-canceled invoice is
    authoritative for each link. A canceled invoice remains linked as history and
    may be replaced from the link form.
4. Post the invoice and reconcile the full payment. In default **invoice** mode,
   the family is a member while today is within the linked school year and the
   invoice is currently posted and fully `paid`. Partial payments, unrelated
   partner invoices, and draft invoices never qualify. A posted customer credit
   note reversing that exact invoice revokes membership, even if Odoo still
   displays the original invoice as `paid`; draft, canceled, and unrelated
   credit notes do not.

The link's **Invoice Link Status** is separate from family membership mode:
`pending` before a year or while dues are unpaid, `active` when its paid invoice
qualifies during the year, `expired` after June 30, and `canceled` when the link
is archived. Valid From/Through come from its school year and cannot be edited
on the link. Archiving is administrative; an archived link never counts as
invoice-mode membership. Archived links remain visible in **Family Period Links**
so managers can inspect their canceled status.

## Manual mode

A system administrator can select **Manual Family Flag** in Settings → AFA
Membership. An AFA Family Manager then edits **Manual Membership** on the family
form. This flag remains as set across July 1 until a manager changes it, even
without an invoice or period link. Switching back to invoice mode does not
erase the flag. The family form shows read-only effective status and, in invoice
mode, the current school year and invoice reference (not a link to an accounting
record that family-only managers cannot open). Neither the derived status nor
the setting can be changed by ordinary family staff. No membership flag is added
to contacts.

## Local tests

Use the isolated Odoo 19 stack from the [repository README](../README.md).
Choose a **new unused database name** for each test installation; never reuse a
live UI database:

```sh
docker compose -f compose.test.yaml run --rm -e AFA_EXPECT_DEMO=1 odoo -d afa_membership_fresh_example -i afa_family,afa_membership --with-demo --test-enable --test-tags /afa_family,/afa_membership --stop-after-init --log-level=test --db_host=db --db_user=odoo --db_password=odoo
```

Inspect the `odoo.tests.result` summary for zero failures and errors, and verify
that both addon test classes started. Odoo may report test failures without a
failing process exit code. This local example does not constitute remote CI
evidence.
