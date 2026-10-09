from ast import literal_eval
from datetime import date
from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestMembershipDomain(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Period = self.env['afa.membership.period']
        self.Membership = self.env['afa.membership']
        guardian = self.env['res.partner'].create(
            {'name': 'Membership Guardian', 'afa_family_role': 'guardian'}
        )
        self.family = self.env['afa.family'].create(
            {'name': 'Membership Family', 'billing_partner_id': guardian.id}
        )
        self.period = self.Period.create(
            {'name': '2026/27', 'date_start': '2026-07-01', 'date_end': '2027-06-30'}
        )

    def test_school_year_bounds_include_july_first_and_june_thirtieth(self):
        self.assertEqual(str(self.period.date_start), '2026-07-01')
        self.assertEqual(str(self.period.date_end), '2027-06-30')
        self.assertTrue(self.period.date_start <= self.period.date_end)

    def test_link_dates_and_unpaid_state_follow_school_year(self):
        link = self.Membership.create({'family_id': self.family.id, 'period_id': self.period.id})
        self.assertEqual(link.date_start, date(2026, 7, 1))
        self.assertEqual(link.date_end, date(2027, 6, 30))
        for day, expected in (
            (date(2026, 6, 30), 'pending'),
            (date(2026, 7, 1), 'pending'),
            (date(2027, 6, 30), 'pending'),
            (date(2027, 7, 1), 'expired'),
        ):
            with patch('odoo.fields.Date.context_today', return_value=day):
                self.env.invalidate_all()
                self.assertEqual(link.state, expected)
        link.active = False
        with patch('odoo.fields.Date.context_today', return_value=date(2027, 7, 1)):
            self.env.invalidate_all()
            self.assertEqual(link.state, 'canceled')

    def test_derived_link_state_and_validity_dates_cannot_be_written(self):
        link = self.Membership.create({'family_id': self.family.id, 'period_id': self.period.id})
        for field, value in (
            ('state', 'active'),
            ('date_start', '2026-07-01'),
            ('date_end', '2027-06-30'),
        ):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                link.write({field: value})
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self.Membership.create(
                    {'family_id': self.family.id, 'period_id': self.period.id, field: value}
                )

    def test_invalid_school_year_dates_are_rejected_on_create_and_write(self):
        for start, end in (
            ('2026-06-30', '2027-06-30'),
            ('2026-07-01', '2027-07-01'),
            ('2027-07-01', '2027-06-30'),
        ):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self.Period.create({'name': 'Invalid', 'date_start': start, 'date_end': end})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.period.write({'date_end': '2027-06-29'})
        self.assertEqual(str(self.period.date_end), '2027-06-30')

    def test_overlapping_period_is_rejected_but_adjacent_year_is_allowed(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.Period.create(
                {'name': 'Duplicate', 'date_start': '2026-07-01', 'date_end': '2027-06-30'}
            )
        adjacent = self.Period.create(
            {'name': '2027/28', 'date_start': '2027-07-01', 'date_end': '2028-06-30'}
        )
        self.assertEqual(str(adjacent.date_start), '2027-07-01')
        self.Membership.create({'family_id': self.family.id, 'period_id': self.period.id})
        self.Membership.create({'family_id': self.family.id, 'period_id': adjacent.id})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            adjacent.write({'date_start': '2026-07-01'})

    def test_duplicate_active_link_is_rejected_on_create_and_reactivation(self):
        first = self.Membership.create({'family_id': self.family.id, 'period_id': self.period.id})
        self.assertIn(first, self.family.membership_ids)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.Membership.create({'family_id': self.family.id, 'period_id': self.period.id})
        archived = self.Membership.create(
            {'family_id': self.family.id, 'period_id': self.period.id, 'active': False}
        )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            archived.write({'active': True})

    def test_duplicate_active_link_on_reassignment_is_rejected(self):
        second_guardian = self.env['res.partner'].create(
            {'name': 'Second Guardian', 'afa_family_role': 'guardian'}
        )
        second_family = self.env['afa.family'].create(
            {'name': 'Second Family', 'billing_partner_id': second_guardian.id}
        )
        self.Membership.create({'family_id': self.family.id, 'period_id': self.period.id})
        other = self.Membership.create({'family_id': second_family.id, 'period_id': self.period.id})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            other.write({'family_id': self.family.id})

    def test_database_rejects_duplicate_period_even_without_orm(self):
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.cr.execute(
                'INSERT INTO afa_membership_period (name, date_start, date_end) '
                'VALUES (%s, %s, %s)',
                ('Duplicate SQL year', '2026-07-01', '2027-06-30'),
            )

    def test_database_rejects_active_duplicate_but_allows_archived_replacement(self):
        first = self.Membership.create({'family_id': self.family.id, 'period_id': self.period.id})
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.cr.execute(
                'INSERT INTO afa_membership (family_id, period_id, active) VALUES (%s, %s, %s)',
                (self.family.id, self.period.id, True),
            )
        first.write({'active': False})
        replacement = self.Membership.create(
            {'family_id': self.family.id, 'period_id': self.period.id}
        )
        self.assertTrue(replacement.active)
        self.assertFalse(first.active)

    def test_manager_access_and_unprivileged_denial(self):
        users = self.env['res.users'].with_context(no_reset_password=True)
        user = users.create(
            {
                'name': 'Membership Staff',
                'login': 'membership-staff-test',
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
            }
        )
        for model, vals in (
            (
                self.Period,
                {'name': '2027/28', 'date_start': '2027-07-01', 'date_end': '2028-06-30'},
            ),
            (self.Membership, {'family_id': self.family.id, 'period_id': self.period.id}),
        ):
            with self.assertRaises(AccessError), self.cr.savepoint():
                model.with_user(user).create(vals)
        manager = self.env['res.users'].create(
            {
                'name': 'Membership Manager',
                'login': 'membership-manager-test',
                'group_ids': [(6, 0, [self.env.ref('afa_family.group_family_manager').id])],
            }
        )
        link = self.Membership.with_user(manager).create(
            {'family_id': self.family.id, 'period_id': self.period.id}
        )
        self.assertEqual(link.with_user(manager).period_id, self.period)
        for model in (self.Period, self.Membership):
            self.assertFalse(model.with_user(user).has_access('read'))
            self.assertFalse(model.with_user(user).has_access('write'))
            self.assertFalse(model.with_user(user).has_access('unlink'))
        with self.assertRaises(AccessError), self.cr.savepoint():
            link.with_user(user).write({'active': False})

    def test_new_link_without_period_does_not_crash_state_compute(self):
        draft = self.Membership.new({'family_id': self.family.id})
        self.assertEqual(draft.state, 'pending')
        self.assertFalse(draft.is_invoice_member_on(date(2026, 9, 1)))

    def test_archived_link_remains_visible_in_manager_action(self):
        link = self.Membership.create({'family_id': self.family.id, 'period_id': self.period.id})
        link.active = False
        self.assertFalse(self.Membership.search([('id', '=', link.id)]))
        action = self.env.ref('afa_membership.action_afa_membership')
        context = literal_eval(action.context or '{}')
        visible = self.Membership.with_context(**context).search([('id', '=', link.id)])
        self.assertEqual(visible, link)
        self.assertEqual(visible.state, 'canceled')
