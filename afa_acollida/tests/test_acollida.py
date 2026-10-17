import base64
import csv
import io
from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase

from ..wizard import file_format


class TestAcollida(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env['account.chart.template'].try_loading('generic_coa', self.env.company)
        self.journal = self.env['account.journal'].search(
            [('company_id', '=', self.env.company.id), ('type', '=', 'sale')], limit=1
        )
        inbound_method = self.env['account.payment.method'].search(
            [('payment_type', '=', 'inbound')], limit=1
        )
        self.payment_mode = self.env['account.payment.mode'].create(
            {
                'name': 'Acollida Direct Debit',
                'company_id': self.env.company.id,
                'payment_method_id': inbound_method.id,
                'bank_account_link': 'variable',
            }
        )
        self.product = self.env['product.product'].create(
            {'name': 'Acollida Fee', 'list_price': 43.0}
        )
        self.product.with_company(
            self.env.company
        ).property_account_income_id = self.journal.default_account_id
        self.course = self.env['afa.school.course'].create({'name': '3r Primària', 'sequence': 930})
        guardian = self.env['res.partner'].create(
            {'name': 'Billing Guardian', 'afa_family_role': 'guardian'}
        )
        self.family = self.env['afa.family'].create(
            {'name': 'Acollida Family', 'billing_partner_id': guardian.id}
        )
        self.other_guardian = self.env['res.partner'].create(
            {
                'name': 'Other Guardian',
                'afa_family_id': self.family.id,
                'afa_family_role': 'guardian',
            }
        )
        self.student = self._student('Student One')
        self.period = self.env['afa.membership.period'].create(
            {
                'name': '2026/27',
                'date_start': '2026-07-01',
                'date_end': '2027-06-30',
            }
        )
        self.config = self.env['afa.acollida.config'].create(
            {
                'period_id': self.period.id,
                'product_id': self.product.id,
                'invoice_journal_id': self.journal.id,
                'payment_mode_id': self.payment_mode.id,
            }
        )

    def _student(self, name):
        return self.env['res.partner'].create(
            {
                'name': name,
                'afa_family_id': self.family.id,
                'afa_family_role': 'student',
                'afa_course_id': self.course.id,
            }
        )

    def _csv(self, rows):
        headers = [
            'Alumne',
            'PARE',
            'Curs',
            'TRAM',
            'HORES/ SETMANA',
            'IMPORT/MES',
            'SETEMBRE',
            'OCTUBRE',
            'NOVEMBRE',
            'DESEMBRE',
            'GENER',
            'FEBRER',
            'MARÇ',
            'ABRIL',
            'MAIG',
            'JUNY',
        ]
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow(headers)
        for row in rows:
            writer.writerow(
                [
                    row.get('student', self.student.name),
                    row.get('parent', self.other_guardian.name),
                    row.get('course', '3er'),
                    row.get('tranche', '1r'),
                    row.get('hours', '3.45'),
                    row.get('base', '24,00 €'),
                    row.get('september', '18,00 €'),
                    row.get('october', '24,00 €'),
                    row.get('november', ''),
                    row.get('december', ''),
                    row.get('january', ''),
                    row.get('february', ''),
                    row.get('march', ''),
                    row.get('april', ''),
                    row.get('may', ''),
                    row.get('june', ''),
                ]
            )
        return output.getvalue()

    def _import(self, content):
        wizard = self.env['afa.acollida.import.wizard'].create(
            {
                'config_id': self.config.id,
                'filename': 'acollida.csv',
                'file': base64.b64encode(content.encode()),
            }
        )
        wizard.action_preview()
        return wizard

    def _bill(self, month='2026-09-01'):
        wizard = self.env['afa.acollida.billing'].create({'month': month})
        wizard.action_preview()
        return wizard

    def test_file_helpers_parse_localized_amounts_hours_and_course_names(self):
        self.assertEqual(file_format.parse_amount('1.234,50 €'), 1234.50)
        self.assertEqual(file_format.parse_amount('24.00 €'), 24.0)
        self.assertEqual(file_format.parse_hours('3.45'), 3.75)
        self.assertEqual(file_format.parse_hours('5:00'), 5)
        self.assertEqual(file_format.normalize_course('3er Primària'), '3r')
        self.assertEqual(file_format.normalize_course('3r'), '3r')
        with self.assertRaises(ValueError):
            file_format.parse_amount('NaN')
        with self.assertRaises(ValueError):
            file_format.parse_hours('NaN')

    def test_import_preserves_month_amounts_and_empty_months_create_no_charge(self):
        wizard = self._import(self._csv([{}]))
        self.assertEqual(wizard.line_ids.mapped('action'), ['create', 'create'])
        self.assertFalse(any(wizard.line_ids.mapped('warnings')))
        wizard.action_confirm()

        charges = self.env['afa.acollida.charge'].search(
            [('student_id', '=', self.student.id), ('active', '=', True)]
        )
        self.assertEqual(sorted(charges.mapped('month')), [date(2026, 9, 1), date(2026, 10, 1)])
        self.assertEqual(
            {charge.month: charge.amount for charge in charges},
            {date(2026, 9, 1): 18, date(2026, 10, 1): 24},
        )
        self.assertTrue(all(charge.base_amount == 24 for charge in charges))
        self.assertTrue(all(charge.parent_name == self.other_guardian.name for charge in charges))

    def test_inconsistency_warnings_do_not_block_confirmation(self):
        wizard = self._import(self._csv([{'hours': '7:00', 'tranche': '1r', 'base': '24,00 €'}]))
        self.assertEqual(wizard.line_ids.mapped('action'), ['create', 'create'])
        self.assertTrue(
            all(
                'tranche does not match' in warning
                for warning in wizard.line_ids.mapped('warnings')
            )
        )

        wizard.action_confirm()

        self.assertEqual(
            self.env['afa.acollida.charge'].search_count(
                [('student_id', '=', self.student.id), ('active', '=', True)]
            ),
            2,
        )

    def test_import_matches_students_by_name_and_normalized_course(self):
        wizard = self._import(self._csv([{}]))
        self.assertEqual(set(wizard.line_ids.mapped('student_id').ids), {self.student.id})
        self.assertEqual(set(wizard.line_ids.mapped('family_id').ids), {self.family.id})

    def test_reimport_skips_identical_charges_and_rejects_changed_amount(self):
        content = self._csv([{}])
        self._import(content).action_confirm()
        repeated = self._import(content)
        self.assertEqual(set(repeated.line_ids.mapped('action')), {'skip'})
        repeated.action_confirm()
        self.assertEqual(
            self.env['afa.acollida.charge'].search_count(
                [('student_id', '=', self.student.id), ('active', '=', True)]
            ),
            2,
        )

        changed = self._import(self._csv([{'september': '19,00 €'}]))
        september = changed.line_ids.filtered(lambda line: line.month == date(2026, 9, 1))
        october = changed.line_ids.filtered(lambda line: line.month == date(2026, 10, 1))
        self.assertEqual(september.action, 'error')
        self.assertEqual(october.action, 'skip')
        changed.action_confirm()
        self.assertEqual(
            self.env['afa.acollida.charge'].search_count(
                [('student_id', '=', self.student.id), ('active', '=', True)]
            ),
            2,
        )

    def test_ambiguous_student_blocks_confirmation(self):
        self._student(self.student.name)
        wizard = self._import(self._csv([{}]))

        self.assertEqual(set(wizard.line_ids.mapped('action')), {'error'})
        self.assertTrue(
            all('More than one student' in error for error in wizard.line_ids.mapped('error'))
        )
        wizard.action_confirm()
        self.assertFalse(self.env['afa.acollida.charge'].search([]))

    def test_blank_student_and_course_are_reported_and_blank_hours_warn(self):
        invalid = self._import(self._csv([{'student': '', 'course': '', 'hours': ''}]))
        self.assertEqual(set(invalid.line_ids.mapped('action')), {'error'})
        self.assertTrue(
            all(
                'Student name and course are required' in error
                for error in invalid.line_ids.mapped('error')
            )
        )

        missing_hours = self._import(self._csv([{'hours': ''}]))
        self.assertEqual(set(missing_hours.line_ids.mapped('action')), {'create'})
        self.assertTrue(
            all(
                'Weekly hours are missing' in warning
                for warning in missing_hours.line_ids.mapped('warnings')
            )
        )
        missing_hours.action_confirm()

    def test_billing_manager_without_accounting_can_preview_but_not_generate(self):
        self._import(self._csv([{}])).action_confirm()
        reviewer = self.env['res.users'].create(
            {
                'name': 'Acollida Billing Reviewer',
                'login': 'acollida-billing-reviewer',
                'group_ids': [
                    Command.set(
                        [
                            self.env.ref('base.group_user').id,
                            self.env.ref('afa_family.group_family_manager').id,
                        ]
                    )
                ],
                'company_id': self.env.company.id,
                'company_ids': [Command.set([self.env.company.id])],
            }
        )
        billing = (
            self.env['afa.acollida.billing'].with_user(reviewer).create({'month': '2026-09-01'})
        )

        billing.action_preview()

        self.assertEqual(len(billing.line_ids), 1)
        self.assertTrue(billing.line_ids.include)
        with self.assertRaises(AccessError):
            billing.action_generate()

    def test_imported_charge_keeps_the_family_at_import_time(self):
        self._import(self._csv([{}])).action_confirm()
        other_guardian = self.env['res.partner'].create(
            {'name': 'New Billing Guardian', 'afa_family_role': 'guardian'}
        )
        other_family = self.env['afa.family'].create(
            {'name': 'New Acollida Family', 'billing_partner_id': other_guardian.id}
        )
        self.student.write({'afa_family_id': other_family.id})

        charges = self.env['afa.acollida.charge'].search(
            [('student_id', '=', self.student.id), ('active', '=', True)]
        )
        self.assertEqual(set(charges.mapped('family_id').ids), {self.family.id})
        billing = self._bill()
        self.assertEqual(set(billing.line_ids.mapped('family_id').ids), {self.family.id})

    def test_imported_charges_generate_one_family_invoice_with_month_amounts(self):
        second_student = self._student('Student Two')
        wizard = self._import(
            self._csv(
                [
                    {},
                    {'student': second_student.name, 'september': '32,25 €', 'october': ''},
                ]
            )
        )
        wizard.action_confirm()
        billing = self._bill()
        self.assertEqual(len(billing.line_ids), 2)

        result = billing.action_generate()
        invoice = self.env['account.move'].browse(result['domain'][0][2][0])

        self.assertEqual(invoice.partner_id, self.family.billing_partner_id)
        self.assertEqual(invoice.journal_id, self.journal)
        self.assertEqual(invoice.payment_mode_id, self.payment_mode)
        self.assertEqual(invoice.afa_service_family_id, self.family)
        self.assertEqual(invoice.afa_service_month, date(2026, 9, 1))
        self.assertEqual(sorted(invoice.invoice_line_ids.mapped('price_unit')), [18, 32.25])
        self.assertEqual(len(invoice.afa_acollida_charge_ids), 2)
        self.assertEqual(
            set(invoice.afa_acollida_charge_ids.mapped('student_id').ids),
            {self.student.id, second_student.id},
        )

    def test_canceled_invoice_deactivates_history_and_allows_reimport(self):
        content = self._csv([{}])
        self._import(content).action_confirm()
        invoice = self.env['account.move'].browse(self._bill().action_generate()['domain'][0][2][0])
        original_charges = invoice.afa_acollida_charge_ids
        with self.assertRaises(ValidationError):
            original_charges.with_context(_afa_cancel_acollida_invoice=True).write(
                {'active': False}
            )

        invoice.button_cancel()

        self.assertFalse(any(original_charges.mapped('active')))
        self._import(content).action_confirm()
        self.assertEqual(
            self.env['afa.acollida.charge']
            .with_context(active_test=False)
            .search_count([('student_id', '=', self.student.id)]),
            3,
        )
        self.assertEqual(
            self.env['afa.acollida.charge'].search_count(
                [('student_id', '=', self.student.id), ('active', '=', True)]
            ),
            2,
        )

    def test_configuration_company_is_immutable_after_charge_history(self):
        self._import(self._csv([{'october': ''}])).action_confirm()
        invoice = self.env['account.move'].browse(self._bill().action_generate()['domain'][0][2][0])
        invoice.button_cancel()
        self.assertFalse(self.env['afa.acollida.charge'].search([('active', '=', True)]))

        other_company = self.env['res.company'].create({'name': 'Other Acollida Company'})
        with self.assertRaises(ValidationError):
            self.config.write({'company_id': other_company.id})

    def test_acollida_and_monthly_service_share_family_invoice(self):
        self._import(self._csv([{}])).action_confirm()
        acollida_invoice = self.env['account.move'].browse(
            self._bill().action_generate()['domain'][0][2][0]
        )
        service = self.env['afa.service'].create(
            {
                'name': 'Afternoon Care',
                'period_id': self.period.id,
                'date_start': '2026-09-01',
                'date_end': '2027-06-30',
                'product_id': self.product.id,
                'invoice_journal_id': self.journal.id,
                'payment_mode_id': self.payment_mode.id,
                'member_price': 24,
                'nonmember_price': 43,
            }
        )
        join = self.env['afa.service.window'].create(
            {
                'service_id': service.id,
                'kind': 'join',
                'date_start': '2026-09-01',
                'date_end': '2026-09-30',
                'effective_month': '2026-09-01',
            }
        )
        with patch('odoo.fields.Date.context_today', return_value=date(2026, 9, 10)):
            self.env['afa.service.subscription'].create(
                {
                    'service_id': service.id,
                    'student_id': self.student.id,
                    'join_window_id': join.id,
                }
            )
        monthly = self.env['afa.service.billing'].create({'month': '2026-09-01'})
        monthly.action_preview()

        result = monthly.action_generate()

        invoice = self.env['account.move'].browse(result['domain'][0][2][0])
        self.assertEqual(invoice, acollida_invoice)
        self.assertEqual(len(invoice.invoice_line_ids), 2)
        self.assertEqual(len(invoice.afa_acollida_charge_ids), 1)
        self.assertEqual(len(invoice.afa_service_charge_ids), 1)

    def test_xlsx_import_uses_active_sheet_and_numeric_amounts(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest('openpyxl is not installed in this image')
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(
            [
                'Alumne',
                'PARE',
                'Curs',
                'TRAM',
                'HORES/ SETMANA',
                'IMPORT/MES',
                'SETEMBRE',
                'OCTUBRE',
                'NOVEMBRE',
                'DESEMBRE',
                'GENER',
                'FEBRER',
                'MARÇ',
                'ABRIL',
                'MAIG',
                'JUNY',
            ]
        )
        sheet.append(
            [
                self.student.name,
                self.other_guardian.name,
                '3er',
                '1r',
                3.45,
                24,
                18,
                24,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ]
        )
        content = io.BytesIO()
        workbook.save(content)
        wizard = self.env['afa.acollida.import.wizard'].create(
            {
                'config_id': self.config.id,
                'filename': 'fees.xlsx',
                'file': base64.b64encode(content.getvalue()),
            }
        )

        wizard.action_preview()

        self.assertEqual(wizard.line_ids.mapped('amount'), [18, 24])
        self.assertFalse(any(wizard.line_ids.mapped('error')))
