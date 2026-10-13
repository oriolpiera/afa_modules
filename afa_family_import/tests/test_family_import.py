import base64
import csv
import io
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase

from .. import file_format

VALID_IBAN = 'ES9121000418450200051332'


class TestFamilyImport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.course_four = self.env['afa.school.course'].create({'name': '4t', 'sequence': 4})
        self.course_five = self.env['afa.school.course'].create({'name': '5è', 'sequence': 5})
        self.past_date = (fields.Date.today() - timedelta(days=30)).isoformat()
        self.future_date = (fields.Date.today() + timedelta(days=30)).isoformat()

    def _row(self, family, role, name, **extra):
        values = dict.fromkeys(file_format.COLUMNS, '')
        values.update({'family_name': family, 'role': role, 'name': name})
        values.update({key: str(value) for key, value in extra.items()})
        return ','.join(values[column] for column in file_format.COLUMNS)

    def _load(self, rows, **kwargs):
        content = '\n'.join([','.join(file_format.COLUMNS), *rows])
        values = {'file': base64.b64encode(content.encode()), 'filename': 'families.csv'}
        values.update(kwargs)
        wizard = self.env['afa.family.import.wizard'].create(values)
        wizard.action_load()
        return wizard

    def _errors(self, wizard):
        return {line.name: line.error for line in wizard.line_ids if line.action == 'error'}

    def _family(self, name):
        return self.env['afa.family'].with_context(active_test=False).search([('name', '=', name)])

    def test_import_creates_family_guardians_students_bank_and_mandate(self):
        wizard = self._load(
            [
                self._row(
                    'Fam Roure',
                    'guardian',
                    'Anna Roure',
                    is_billing='true',
                    email='anna@example.cat',
                    phone='+34600000001',
                    iban=VALID_IBAN,
                    mandate_date=self.past_date,
                ),
                self._row(
                    'Fam Roure',
                    'guardian',
                    'Jordi Roure',
                    email='jordi@example.cat',
                    phone='+34600000002',
                ),
                self._row('Fam Roure', 'student', 'Pol Roure', course='4t'),
                self._row('Fam Roure', 'student', 'Laia Roure', course='5è'),
            ]
        )
        self.assertFalse(self._errors(wizard))
        wizard.action_confirm()

        family = self._family('Fam Roure')
        self.assertEqual(len(family), 1)
        self.assertEqual(family.billing_partner_id.name, 'Anna Roure')
        self.assertEqual(family.billing_partner_id.afa_family_role, 'guardian')
        self.assertEqual(family.billing_partner_id.email, 'anna@example.cat')
        self.assertEqual(family.billing_partner_id.phone, '+34600000001')
        self.assertEqual(set(family.guardian_ids.mapped('name')), {'Anna Roure', 'Jordi Roure'})

        students = family.student_ids.sorted('name')
        self.assertEqual(students.mapped('name'), ['Laia Roure', 'Pol Roure'])
        self.assertEqual(students.mapped('afa_course_id'), self.course_five | self.course_four)
        self.assertTrue(all(student.afa_family_role == 'student' for student in students))

        bank = family.billing_partner_id.bank_ids
        self.assertEqual(len(bank), 1)
        self.assertEqual(''.join(bank.acc_number.split()), VALID_IBAN)

        mandate = self.env['account.banking.mandate'].search([('partner_bank_id', 'in', bank.ids)])
        self.assertEqual(len(mandate), 1)
        self.assertEqual(mandate.state, 'valid')
        self.assertEqual(mandate.format, 'sepa')
        self.assertEqual(mandate.type, 'recurrent')
        self.assertEqual(mandate.scheme, 'CORE')
        self.assertEqual(mandate.partner_id, family.billing_partner_id)
        self.assertEqual(mandate.signature_date, fields.Date.to_date(self.past_date))

    def test_single_guardian_without_marker_becomes_the_payer(self):
        wizard = self._load(
            [
                self._row('Fam Sol', 'guardian', 'Maria Sol', email='maria@example.cat'),
                self._row('Fam Sol', 'student', 'Iker Sol', course='4t'),
            ]
        )
        self.assertFalse(self._errors(wizard))
        wizard.action_confirm()
        family = self._family('Fam Sol')
        self.assertEqual(family.billing_partner_id.name, 'Maria Sol')
        self.assertEqual(family.guardian_ids, family.billing_partner_id)

    def test_existing_family_is_skipped_without_duplicates(self):
        rows = [
            self._row(
                'Fam Vega',
                'guardian',
                'Pau Vega',
                is_billing='true',
                email='pau@example.cat',
                iban=VALID_IBAN,
                mandate_date=self.past_date,
            ),
            self._row('Fam Vega', 'student', 'Nil Vega', course='4t'),
        ]
        self._load(rows).action_confirm()

        second = self._load(rows)
        self.assertEqual(set(second.line_ids.mapped('action')), {'skip'})
        with self.assertRaisesRegex(UserError, 'already exists'):
            second.action_confirm()

        family = self._family('Fam Vega')
        self.assertEqual(len(family), 1)
        self.assertEqual(len(self.env['res.partner'].search([('name', '=', 'Nil Vega')])), 1)
        self.assertEqual(len(family.billing_partner_id.bank_ids), 1)
        mandates = self.env['account.banking.mandate'].search(
            [('partner_id', 'in', family.guardian_ids.ids)]
        )
        self.assertEqual(len(mandates), 1)

    def test_unknown_course_is_reported_and_nothing_is_created(self):
        wizard = self._load(
            [
                self._row('Fam Nil', 'guardian', 'Ona Nil', is_billing='true'),
                self._row('Fam Nil', 'student', 'Bernat Nil', course='9è'),
            ]
        )
        self.assertEqual(
            self._errors(wizard)['Bernat Nil'], 'The school course "9è" does not exist.'
        )
        wizard.action_confirm()
        self.assertFalse(self._family('Fam Nil'))
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'Ona Nil')]))

    def test_two_billing_guardians_are_reported(self):
        wizard = self._load(
            [
                self._row('Fam Dos', 'guardian', 'Una Dos', is_billing='true'),
                self._row('Fam Dos', 'guardian', 'Altra Dos', is_billing='true'),
            ]
        )
        message = 'More than one billing guardian is marked.'
        self.assertEqual(self._errors(wizard), {'Una Dos': message, 'Altra Dos': message})

    def test_multiple_guardians_without_a_marker_are_reported(self):
        wizard = self._load(
            [
                self._row('Fam Marc', 'guardian', 'Un Marc'),
                self._row('Fam Marc', 'guardian', 'Dos Marc'),
            ]
        )
        message = 'Mark which guardian pays the dues.'
        self.assertEqual(self._errors(wizard), {'Un Marc': message, 'Dos Marc': message})

    def test_family_without_guardians_is_reported(self):
        wizard = self._load([self._row('Fam Orfe', 'student', 'Aina Orfe', course='4t')])
        self.assertEqual(
            self._errors(wizard), {'Aina Orfe': 'A family needs at least one guardian.'}
        )

    def test_student_without_course_is_reported(self):
        wizard = self._load(
            [
                self._row('Fam Bass', 'guardian', 'Roc Bass', is_billing='true'),
                self._row('Fam Bass', 'student', 'Aina Bass'),
            ]
        )
        self.assertEqual(self._errors(wizard), {'Aina Bass': 'A student needs a school course.'})

    def test_non_student_cannot_carry_a_course(self):
        wizard = self._load(
            [
                self._row(
                    'Fam Camp',
                    'guardian',
                    'Laia Camp',
                    is_billing='true',
                    course='4t',
                    iban=VALID_IBAN,
                    mandate_date=self.past_date,
                ),
                self._row('Fam Camp', 'student', 'Jan Camp', course='4t'),
            ]
        )
        self.assertEqual(
            self._errors(wizard), {'Laia Camp': 'Only students can have a school course.'}
        )

    def test_invalid_email_is_reported(self):
        wizard = self._load(
            [
                self._row(
                    'Fam Riu',
                    'guardian',
                    'Marta Riu',
                    is_billing='true',
                    email='marta[at]example.cat',
                ),
                self._row('Fam Riu', 'student', 'Nil Riu', course='4t'),
            ]
        )
        self.assertEqual(
            self._errors(wizard),
            {'Marta Riu': 'The email address "marta[at]example.cat" is not valid.'},
        )

    def test_invalid_iban_is_reported(self):
        wizard = self._load(
            [
                self._row(
                    'Fam Tur',
                    'guardian',
                    'Una Tur',
                    is_billing='true',
                    iban='ES9121000418450200051333',
                ),
                self._row('Fam Tur', 'student', 'Dos Tur', course='4t'),
            ]
        )
        self.assertIn('is not valid', self._errors(wizard)['Una Tur'])

    def test_unknown_role_is_reported(self):
        wizard = self._load([self._row('Fam Vila', 'guardia', 'Ana Vila', is_billing='true')])
        self.assertEqual(
            self._errors(wizard), {'Ana Vila': 'The role must be "guardian" or "student".'}
        )

    def test_future_mandate_date_is_reported(self):
        wizard = self._load(
            [
                self._row(
                    'Fam Mar',
                    'guardian',
                    'Una Mar',
                    is_billing='true',
                    iban=VALID_IBAN,
                    mandate_date=self.future_date,
                ),
                self._row('Fam Mar', 'student', 'Dos Mar', course='4t'),
            ]
        )
        self.assertEqual(
            self._errors(wizard),
            {'Una Mar': f'The mandate date "{self.future_date}" is in the future.'},
        )

    def test_malformed_mandate_date_is_reported(self):
        wizard = self._load(
            [
                self._row(
                    'Fam Neu',
                    'guardian',
                    'Una Neu',
                    is_billing='true',
                    iban=VALID_IBAN,
                    mandate_date='31/12/2026',
                ),
                self._row('Fam Neu', 'student', 'Dos Neu', course='4t'),
            ]
        )
        self.assertEqual(
            self._errors(wizard),
            {'Una Neu': 'The mandate date "31/12/2026" is not a valid date.'},
        )

    def test_billing_guardian_with_iban_requires_a_mandate_date(self):
        wizard = self._load(
            [
                self._row('Fam Bruc', 'guardian', 'Una Bruc', is_billing='true', iban=VALID_IBAN),
                self._row('Fam Bruc', 'student', 'Dos Bruc', course='4t'),
            ]
        )
        self.assertEqual(
            self._errors(wizard),
            {'Una Bruc': 'A billing guardian with an IBAN needs a mandate signature date.'},
        )

    def test_mandates_can_be_disabled(self):
        wizard = self._load(
            [
                self._row('Fam Pi', 'guardian', 'Una Pi', is_billing='true', iban=VALID_IBAN),
                self._row('Fam Pi', 'student', 'Dos Pi', course='4t'),
            ],
            create_mandates=False,
        )
        self.assertFalse(self._errors(wizard))
        wizard.action_confirm()
        family = self._family('Fam Pi')
        self.assertEqual(len(family.billing_partner_id.bank_ids), 1)
        mandates = self.env['account.banking.mandate'].search(
            [('partner_id', '=', family.billing_partner_id.id)]
        )
        self.assertFalse(mandates)

    def test_failing_family_is_reported_without_discarding_the_others(self):
        wizard = self._load(
            [
                self._row('Fam Alpha', 'guardian', 'Alpha Payer', is_billing='true'),
                self._row('Fam Beta', 'guardian', 'Beta Payer', is_billing='true'),
            ]
        )
        self.assertFalse(self._errors(wizard))
        original = type(wizard)._create_family

        def _create_family(recordset, group):
            if group[0].family_name == 'Fam Beta':
                raise ValidationError('Beta cannot be created.')
            return original(recordset, group)

        with patch.object(type(wizard), '_create_family', _create_family):
            wizard.action_confirm()

        self.assertEqual(len(self._family('Fam Alpha')), 1)
        self.assertFalse(self._family('Fam Beta'))
        # The savepoint rolled back the partially created payer of the failed family.
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'Beta Payer')]))
        beta_line = wizard.line_ids.filtered(lambda line: line.family_name == 'Fam Beta')
        self.assertEqual(beta_line.action, 'error')
        self.assertIn('Beta cannot be created', beta_line.error)

    def test_xlsx_file_is_read(self):
        try:
            import openpyxl
        except ImportError:  # pragma: no cover - depends on the Odoo image
            self.skipTest('openpyxl is not installed in this image')

        rows = [
            self._row(
                'Fam Full', 'guardian', 'Tona Full', is_billing='true', email='tona@example.cat'
            ),
            self._row('Fam Full', 'student', 'Iker Full', course='4t'),
        ]
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.append(list(file_format.COLUMNS))
        for row in rows:
            sheet.append(row.split(','))
        buffer = io.BytesIO()
        book.save(buffer)

        wizard = self.env['afa.family.import.wizard'].create(
            {
                'file': base64.b64encode(buffer.getvalue()),
                'filename': 'families.xlsx',
            }
        )
        wizard.action_load()
        self.assertFalse(self._errors(wizard))
        wizard.action_confirm()

        family = self._family('Fam Full')
        self.assertEqual(len(family), 1)
        self.assertEqual(family.billing_partner_id.name, 'Tona Full')
        self.assertEqual(family.student_ids.mapped('name'), ['Iker Full'])

    def test_missing_file_and_unsupported_extension_are_refused(self):
        wizard = self.env['afa.family.import.wizard'].create({})
        with self.assertRaises(UserError):
            wizard.action_confirm()
        with self.assertRaises(UserError):
            wizard.action_load()
        with self.assertRaisesRegex(UserError, 'CSV or'):
            self._load(
                [self._row('Fam X', 'guardian', 'X', is_billing='true')], filename='families.ods'
            )

    def test_staff_user_cannot_load_a_file(self):
        staff = self.env['res.users'].create(
            {
                'name': 'Staff',
                'login': 'import_staff',
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
            }
        )
        content = '\n'.join(
            [','.join(file_format.COLUMNS), self._row('Fam Y', 'guardian', 'Y', is_billing='true')]
        )
        wizard = self.env['afa.family.import.wizard'].create(
            {'file': base64.b64encode(content.encode()), 'filename': 'families.csv'}
        )
        with self.assertRaises(AccessError):
            wizard.with_user(staff).action_load()
        with self.assertRaises(AccessError):
            wizard.with_user(staff).action_confirm()

    def test_template_documents_the_expected_columns(self):
        self.assertEqual(file_format.TEMPLATE_CSV.splitlines()[0], ','.join(file_format.COLUMNS))
        self.assertIn('family_name', file_format.TEMPLATE_CSV)
        self.assertIn('mandate_date', file_format.TEMPLATE_CSV)

    def test_every_template_row_matches_the_column_count(self):
        rows = list(csv.reader(io.StringIO(file_format.TEMPLATE_CSV)))
        self.assertGreaterEqual(len(rows), 4)
        for row in rows:
            self.assertEqual(len(row), len(file_format.COLUMNS), msg=str(row))
        self.assertEqual(rows[1][6], '')
        self.assertEqual(rows[1][7], VALID_IBAN)
        self.assertEqual(rows[1][8], '2026-09-01')
