# Acollida fixed fees

Import the AFA's existing fixed-fee spreadsheet into Odoo, then review and invoice
the imported amount for each student and month. Odoo does not recalculate the fee.

## Quick path

1. Install `afa_acollida` and give operators the **AFA Family Manager** group.
2. Under **AFA Families → Configuration → Acollida Billing Setup**, create one
   configuration for the school year. Select its school-year period, saleable
   Acollida product, sales journal, inbound payment mode, and company.
3. Open **Import Fixed Fees**, select the configuration, upload the current `.xlsx`
   workbook or a UTF-8 `.csv`, and preview it. Confirm once row errors are resolved.
4. Under **AFA Families → Collections → Acollida Monthly Billing**, select the
   first day of a month, refresh the preview, and generate draft invoices.

## Workbook fields

The importer expects one row per student with these columns:

| Column | Use |
| --- | --- |
| `Alumne` | Student name, matched with the course below. |
| `PARE` | Displayed for review; Odoo's configured family billing guardian remains the payer. |
| `Curs` | School course used to disambiguate students with the same name. |
| `TRAM`, `HORES/SETMANA` | Imported tariff details used for warnings, not fee calculation. |
| `IMPORT/MES` | Base tariff reference: €24 for the first tranche (up to 5 hours/week), €43 for the second (over 5 hours/week). |
| `SETEMBRE` through `JUNY` | Final monthly amounts to invoice. A blank cell creates no charge. |

Headers are case- and accent-insensitive. XLSX cells may contain numbers or
currency-formatted values; CSV accepts localized amounts such as `24,00 €` and
common comma, semicolon, or tab separators. Weekly-hour values such as `3.45` and
`5:00` are interpreted as hours and minutes for consistency checks.

The monthly cells are authoritative. Odoo displays a non-blocking warning when
hours, tranche, base amount, or a monthly amount do not agree with the expected
tariff values. The operator may still confirm those rows. Missing or ambiguous
students, invalid amounts, duplicate rows, and conflicts with an amount already
imported for the same student/month must be resolved before confirming.

## Billing and history

- Imported charges are stored by school-year configuration, student, and month.
- Reimporting an unchanged amount skips it; it never creates a duplicate charge.
- Draft invoices are grouped by family, month, journal, and payment mode, matching
  the existing monthly service invoice grouping. Acollida and other monthly-service
  charges can share the same draft family invoice.
- Invoices are generated as drafts for normal accounting review and posting.
- Canceling an invoice preserves its charge history and deactivates those charges.
  Reimport the workbook to create replacement charges for a canceled month.

This addon covers fixed users only. Sporadic attendance and collection are out of
scope. `.xls` files are not supported; save the workbook as `.xlsx` or export it as
UTF-8 CSV.

Run the Odoo 19 test stack as described in the repository README, including
`afa_acollida` in the installation list and `/afa_acollida` in `--test-tags`.
