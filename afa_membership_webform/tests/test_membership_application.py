from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase

VALID_IBAN = 'ES9121000418450200051332'


class TestMembershipApplication(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.course = cls.env['afa.school.course'].create({'name': 'P3', 'sequence': 3})

    def _application(self, **overrides):
        values = {
            'name': 'Aina Sol',
            'family_name': 'Família Sol',
            'guardian1_name': 'Aina Sol',
            'guardian1_vat': 'DNI1001',
            'email': 'aina@example.cat',
            'address': 'Carrer de l’Escola, 1, les Preses',
            'phone_numbers': '+34600000001',
            'wants_membership': True,
            'iban': VALID_IBAN,
            'mandate_accepted': True,
            'mandate_accepted_at': fields.Datetime.now(),
            'mandate_terms_version': '2026-01',
            'student_ids': [
                (
                    0,
                    0,
                    {
                        'name': 'Pol Sol',
                        'birthday': '2020-03-15',
                        'course_id': self.course.id,
                    },
                )
            ],
        }
        values.update(overrides)
        return self.env['afa.membership.application'].create(values)

    def test_approval_creates_family_contacts_and_sepa_mandate(self):
        application = self._application(guardian2_name='Joan Sol', guardian2_vat='DNI1002')

        action = application.action_approve()

        family = application.family_id
        self.assertEqual(application.state, 'approved')
        self.assertEqual(action['res_model'], 'afa.family')
        self.assertEqual(action['res_id'], family.id)
        self.assertTrue(family.manual_member)
        self.assertEqual(family.billing_partner_id.name, 'Aina Sol')
        self.assertEqual(family.billing_partner_id.vat, 'DNI1001')
        self.assertEqual(family.billing_partner_id.email, 'aina@example.cat')
        self.assertEqual(family.billing_partner_id.street, 'Carrer de l’Escola, 1, les Preses')
        self.assertEqual(set(family.guardian_ids.mapped('name')), {'Aina Sol', 'Joan Sol'})
        student = family.student_ids
        self.assertEqual(student.name, 'Pol Sol')
        self.assertEqual(student.afa_birthdate, fields.Date.to_date('2020-03-15'))
        self.assertEqual(student.afa_course_id, self.course)

        bank = family.billing_partner_id.bank_ids
        self.assertEqual(len(bank), 1)
        self.assertEqual(''.join(bank.acc_number.split()), VALID_IBAN)
        mandate = self.env['account.banking.mandate'].search([('partner_bank_id', '=', bank.id)])
        self.assertEqual(len(mandate), 1)
        self.assertEqual(mandate.state, 'draft')
        self.assertEqual(mandate.format, 'sepa')
        self.assertEqual(mandate.scheme, 'CORE')
        self.assertEqual(mandate.type, 'recurrent')
        self.assertEqual(mandate.partner_id, family.billing_partner_id)
        self.assertEqual(mandate.signature_date, application.mandate_accepted_at.date())

    def test_approval_without_membership_does_not_create_bank_data(self):
        application = self._application(
            wants_membership=False,
            iban=False,
            mandate_accepted=False,
            mandate_accepted_at=False,
            mandate_terms_version=False,
        )

        application.action_approve()

        self.assertFalse(application.family_id.manual_member)
        self.assertFalse(application.family_id.billing_partner_id.bank_ids)
        self.assertFalse(
            self.env['account.banking.mandate'].search(
                [('partner_id', '=', application.family_id.billing_partner_id.id)]
            )
        )

    def test_rejection_does_not_create_family_or_contacts(self):
        application = self._application()

        application.action_reject()

        self.assertEqual(application.state, 'rejected')
        self.assertFalse(application.family_id)
        self.assertFalse(self.env['res.partner'].search([('vat', '=', 'DNI1001')]))

    def test_approval_reuses_unassigned_guardian_by_dni(self):
        guardian = self.env['res.partner'].create({'name': 'Old Name', 'vat': 'DNI1001'})
        self.env['res.partner.bank'].sudo().create(
            {'acc_number': VALID_IBAN, 'partner_id': guardian.id}
        )
        application = self._application()

        application.action_approve()

        self.assertEqual(application.family_id.billing_partner_id, guardian)
        self.assertEqual(self.env['res.partner'].search_count([('vat', '=', 'DNI1001')]), 1)
        self.assertEqual(len(guardian.bank_ids), 1)
        self.assertEqual(guardian.name, 'Aina Sol')

    def test_approval_rejects_guardian_already_linked_to_a_family(self):
        guardian = self.env['res.partner'].create(
            {'name': 'Aina Sol', 'vat': 'DNI1001', 'afa_family_role': 'guardian'}
        )
        self.env['afa.family'].create(
            {'name': 'Existing family', 'billing_partner_id': guardian.id}
        )
        application = self._application()

        with self.assertRaisesRegex(UserError, 'already belongs to an assigned family'):
            application.action_approve()

        self.assertEqual(application.state, 'pending')
        self.assertFalse(application.family_id)

    def test_invalid_iban_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, 'valid IBAN'):
            self._application(iban='ES0000000000000000000000')

    def test_non_manager_cannot_review_applications(self):
        user = self.env['res.users'].create(
            {
                'name': 'AFA Application Non-manager',
                'login': 'afa_application_non_manager',
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
            }
        )
        application = self._application()

        with self.assertRaises(AccessError):
            application.with_user(user).action_approve()
