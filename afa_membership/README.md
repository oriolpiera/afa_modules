# AFA Membership

`afa_membership` adds a persistent family membership intention, July–June school
years, and family-period dues invoices to Odoo 19 Community. It depends on
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
4. Mark **Intends to Be a Member** on the family. This persistent choice makes
   the family a member for all AFA pricing and billing purposes before the annual
   dues are invoiced or paid. A returned SEPA debit suspends membership while
   that dues invoice remains unpaid, including across school years; paying it
   successfully later restores membership without clearing the family flag. A
   posted customer credit note reversing the current dues invoice also revokes
   membership, even if Odoo still displays the original invoice as `paid`; draft,
   canceled, and unrelated credit notes do not. Returns of course or service
   invoices do not affect membership.

The link's **Invoice Link Status** remains a payment-workflow status, separate
from the family's effective membership:
`pending` before a year or while dues are unpaid, `active` when its paid invoice
qualifies during the year, `expired` after June 30, and `canceled` when the link
is archived. Valid From/Through come from its school year and cannot be edited
on the link. Archiving is administrative; an archived link never counts as
invoice eligibility. Archived links remain visible in **Family Period Links**
so managers can inspect their canceled status. The family form shows the current
school year and dues invoice reference (not a link to an accounting record that
family-only managers cannot open). The intention and derived status can only be
changed by AFA Family Managers. Contacts includes a read-only **AFA Member** column
for family managers; it reflects the contact's family's effective membership and
is not a separate per-contact membership value.
Use the **Intends to Be a Member** filter in the Families list when preparing the
annual dues collection.

When upgrading from the previous invoice-based mode, currently eligible paid-dues
families are automatically marked as intending to remain members. Other families
can be reviewed and marked by an AFA Family Manager.

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
