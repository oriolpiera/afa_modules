# Initial family load

Install `afa_family_import` after the family, school course and SEPA addons. It adds
**AFA Families → Load Families**, a family-manager-only assistant that creates complete
families from a CSV or Excel file, which is what an AFA needs for its first load of the
school year.

Download the CSV template from the assistant and fill one **row per person**, keeping the
rows of a family together under the same `family_name`:

| Column | Meaning |
| --- | --- |
| `family_name` | Family name; rows sharing it become one family. |
| `role` | `guardian` or `student`. |
| `is_billing` | `true` on the guardian who pays the dues. |
| `name` | Person name. |
| `email`, `phone` | Contact data, optional. |
| `course` | Course name for students; the course must already exist. |
| `iban` | IBAN of that person, optional. |
| `mandate_date` | SEPA signature date, `YYYY-MM-DD`, for the billing guardian. |

Headers are matched ignoring case and spaces. For each new family the assistant creates
the billing guardian first, then the family linked to it, then the remaining guardians and
students with their course, then a bank account for every row carrying an IBAN and, for the
billing guardian, a valid SEPA Core recurrent mandate.

The **Load File** button only validates and previews: every rejected row shows the reason
and nothing is written yet. A family needs at least one guardian and at most one billing
guardian; a family with a single guardian and no marker automatically designates it. A
student must carry a course and only students may carry one, IBANs are checked with the
ISO 13616 mod-97 checksum and a mandate date cannot be in the future. Uncheck **Create SEPA
Mandates** to store IBANs without generating mandates.

**Confirm Import** creates each family in its own savepoint: a family that fails is rolled
back and reported while the rest still imports. The assistant stays open whenever at least
one family failed, so the reasons stay on screen; it only closes once every family is in.
A family whose name already exists, including archived families, is skipped, so re-running
the same file never duplicates families, people, bank accounts or mandates.
