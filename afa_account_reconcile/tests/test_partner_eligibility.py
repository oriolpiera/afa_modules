from lxml import etree

from odoo.tests.common import TransactionCase


class TestPartnerEligibility(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Partner = self.env['res.partner']
        self.Family = self.env['afa.family']

        self.billing_guardian = self.Partner.create(
            {'name': 'Billing Guardian', 'afa_family_role': 'guardian'}
        )
        self.family = self.Family.create(
            {
                'name': 'Family',
                'billing_partner_id': self.billing_guardian.id,
            }
        )
        self.other_guardian = self.Partner.create(
            {
                'name': 'Other Guardian',
                'afa_family_id': self.family.id,
                'afa_family_role': 'guardian',
            }
        )
        self.student = self.Partner.create(
            {
                'name': 'Student',
                'afa_family_id': self.family.id,
                'afa_family_role': 'student',
            }
        )
        self.external_contact = self.Partner.create({'name': 'External Contact'})
        self.vendor = self.Partner.create({'name': 'Vendor', 'supplier_rank': 1})

    def test_eligible_partners_include_billing_guardians_and_non_family_contacts(self):
        candidates = (
            self.billing_guardian
            | self.other_guardian
            | self.student
            | self.external_contact
            | self.vendor
        )

        eligible = self.Partner.search(
            [
                ('id', 'in', candidates.ids),
                ('afa_is_accounting_partner_eligible', '=', True),
            ]
        )

        self.assertSetEqual(
            set(eligible.ids),
            {self.billing_guardian.id, self.external_contact.id, self.vendor.id},
        )

    def test_eligibility_follows_billing_guardian_reassignment(self):
        self.family.write({'billing_partner_id': self.other_guardian.id})

        self.assertFalse(self.billing_guardian.afa_is_accounting_partner_eligible)
        self.assertTrue(self.other_guardian.afa_is_accounting_partner_eligible)
        self.assertFalse(self.student.afa_is_accounting_partner_eligible)

    def test_accounting_users_can_filter_without_reading_family_fields(self):
        accounting_user = self.env['res.users'].create(
            {
                'name': 'Accounting User',
                'login': 'afa-accounting-user',
                'group_ids': [(6, 0, [self.env.ref('account.group_account_user').id])],
            }
        )
        accounting_partners = self.Partner.with_user(accounting_user)
        fields = accounting_partners.fields_get()

        self.assertIn('afa_is_accounting_partner_eligible', fields)
        self.assertNotIn('afa_family_id', fields)
        self.assertNotIn('afa_family_role', fields)
        eligible = accounting_partners.search(
            [
                ('id', 'in', (self.billing_guardian | self.other_guardian | self.student).ids),
                ('afa_is_accounting_partner_eligible', '=', True),
            ]
        )
        self.assertEqual(eligible, self.billing_guardian)

    def test_bank_statement_partner_selectors_filter_ineligible_family_members(self):
        selectors = (
            (
                'account_statement_base.account_bank_statement_line_form',
                'form',
                'partner_id',
                "[('afa_is_accounting_partner_eligible', '=', True)]",
            ),
            (
                'account_statement_base.account_bank_statement_line_tree',
                'list',
                'partner_id',
                "[('afa_is_accounting_partner_eligible', '=', True)]",
            ),
            (
                'account_reconcile_oca.bank_statement_line_form_add_view',
                'form',
                'partner_id',
                "[('afa_is_accounting_partner_eligible', '=', True)]",
            ),
            (
                'account_reconcile_oca.bank_statement_line_form_reconcile_view',
                'form',
                'manual_partner_id',
                "[('parent_id', '=', False), ('afa_is_accounting_partner_eligible', '=', True)]",
            ),
        )

        for view_xmlid, view_type, field_name, expected_domain in selectors:
            with self.subTest(view=view_xmlid, field=field_name):
                view = self.env.ref(view_xmlid)
                result = self.env['account.bank.statement.line'].get_view(
                    view_id=view.id,
                    view_type=view_type,
                )
                arch = etree.fromstring(result['arch'])
                field = arch.xpath(f"//field[@name='{field_name}']")[0]
                self.assertEqual(field.get('domain'), expected_domain)
