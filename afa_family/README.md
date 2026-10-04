# AFA Families

Install on Odoo 19 Community with `base` and `contacts`; no accounting module is
required. Assign the **AFA Family Manager** group to users who manage families.
The Families menu contains list and form views with guardian and student sections.
The Members button opens Contacts filtered to the current family. Managers may also
assign family roles and membership from a contact's form.

Each partner has at most one AFA family and one role (`guardian` or `student`). A family
can have several guardians and students. The initial billing guardian must be an
unassigned guardian partner; creating the family links that existing partner to it.
After creation, choose a guardian already linked to that family as payer. Moving,
demoting or deleting the current payer is rejected until a replacement is selected.
This link never uses `res.partner.parent_id` and does not duplicate partners.

Student contacts are excluded from generic Contacts searches and direct reads for
non-managers by a global record rule on a stored technical student flag. Family
linkage and role fields are restricted to managers at field and mutation level;
unrelated contacts remain available under their existing Contacts permissions.
The rule treats all student-role contacts as
private because this addon does not store an age or minor flag. Managers can still
read and maintain all family contacts. Only managers can delete family members.
The manager group grants Contact access directly; it does not imply the broader
Contact/Creation group or change non-manager Contact permissions.

`billing_partner_id` identifies the intended recipient for **future** invoices; no
invoice recipient is changed by this addon. Posted invoices keep their recorded
partner. Invoice creation/integration is outside FAM-1 and requires explicit wiring
in a later accounting-aware feature. The regression test checks that changing the
family payer does not change a previously captured partner reference; it does not
exercise `account.move` because this addon deliberately does not depend on `account`.

## Fictitious demo contacts

Installing with demo enabled adds the Cedar and Maple example families. Each
has two guardian contacts, two student contacts, and one designated guardian
payer. No real names, addresses, or contact details are included. The payer
contact is created unassigned first; creating its family links that existing
contact, then the remaining guardians and students link to the family. The
records are in the manifest's `demo` list, so normal data-only installations
do not include them. See the root README for the isolated Odoo 19 test command.
