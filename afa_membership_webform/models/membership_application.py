import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

MANDATE_TERMS_VERSION = '2026-01'
_IBAN_COUNTRY_LENGTHS = {'ES': 24}
_IBAN_RE = re.compile(r'^[A-Z0-9]+$')


def _valid_iban(value):
    iban = ''.join((value or '').split()).upper()
    if not 15 <= len(iban) <= 34 or not _IBAN_RE.fullmatch(iban):
        return False
    expected_length = _IBAN_COUNTRY_LENGTHS.get(iban[:2])
    if expected_length and len(iban) != expected_length:
        return False
    rearranged = iban[4:] + iban[:4]
    digits = ''.join(char if char.isdigit() else str(ord(char) - 55) for char in rearranged)
    return int(digits) % 97 == 1


class AfaMembershipApplication(models.Model):
    _name = 'afa.membership.application'
    _description = 'AFA Membership Application'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, default=lambda self: _('New membership application'))
    family_name = fields.Char(required=True, groups='afa_family.group_family_manager')
    state = fields.Selection(
        [
            ('pending', 'Pending Review'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        default='pending',
        required=True,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, readonly=True
    )
    guardian1_name = fields.Char(required=True, groups='afa_family.group_family_manager')
    guardian1_vat = fields.Char(required=True, groups='afa_family.group_family_manager')
    guardian2_name = fields.Char(groups='afa_family.group_family_manager')
    guardian2_vat = fields.Char(groups='afa_family.group_family_manager')
    email = fields.Char(required=True, groups='afa_family.group_family_manager')
    address = fields.Text(required=True, groups='afa_family.group_family_manager')
    phone_numbers = fields.Char(required=True, groups='afa_family.group_family_manager')
    student_ids = fields.One2many(
        'afa.membership.application.student',
        'application_id',
        string='Students',
        groups='afa_family.group_family_manager',
    )
    wants_membership = fields.Boolean(groups='afa_family.group_family_manager')
    iban = fields.Char(groups='afa_family.group_family_manager')
    mandate_accepted = fields.Boolean(groups='afa_family.group_family_manager')
    mandate_accepted_at = fields.Datetime(readonly=True, groups='afa_family.group_family_manager')
    mandate_terms_version = fields.Char(readonly=True, groups='afa_family.group_family_manager')
    rejection_reason = fields.Text(groups='afa_family.group_family_manager')
    family_id = fields.Many2one(
        'afa.family', readonly=True, ondelete='restrict', groups='afa_family.group_family_manager'
    )
    reviewed_by_id = fields.Many2one(
        'res.users', readonly=True, groups='afa_family.group_family_manager'
    )
    reviewed_at = fields.Datetime(readonly=True, groups='afa_family.group_family_manager')

    @api.constrains(
        'guardian1_name',
        'guardian1_vat',
        'guardian2_name',
        'guardian2_vat',
        'email',
        'address',
        'phone_numbers',
        'wants_membership',
        'iban',
        'mandate_accepted',
        'mandate_accepted_at',
        'student_ids',
    )
    def _check_application(self):
        for application in self:
            if not application.guardian1_name or not application.guardian1_vat:
                raise ValidationError(_('The first guardian name and ID are required.'))
            if bool(application.guardian2_name) != bool(application.guardian2_vat):
                raise ValidationError(
                    _('The second guardian name and ID must be provided together.')
                )
            if not application.email or '@' not in application.email:
                raise ValidationError(_('Enter a valid contact email address.'))
            if not application.address or not application.phone_numbers:
                raise ValidationError(_('The address and at least one contact phone are required.'))
            if not application.student_ids:
                raise ValidationError(_('Add at least one student.'))
            if application.wants_membership:
                if not _valid_iban(application.iban):
                    raise ValidationError(_('Enter a valid IBAN for membership payments.'))
                if not application.mandate_accepted or not application.mandate_accepted_at:
                    raise ValidationError(_('Accept the SEPA direct debit authorization.'))

    def _check_manager(self):
        if not self.env.su and not self.env.user.has_group('afa_family.group_family_manager'):
            raise AccessError(_('Only family managers can review membership applications.'))

    def action_approve(self):
        self.ensure_one()
        self._check_manager()
        self._lock_for_review()
        if self.state != 'pending':
            raise UserError(_('Only pending applications can be approved.'))

        payer = self._get_or_create_guardian(
            self.guardian1_name,
            self.guardian1_vat,
            email=self.email,
            phone=self.phone_numbers,
            street=self.address,
        )
        family = self.env['afa.family'].create(
            {
                'name': self.family_name or _('Família de %s') % self.guardian1_name,
                'billing_partner_id': payer.id,
                'manual_member': self.wants_membership,
            }
        )
        if self.guardian2_name:
            guardian = self._get_or_create_guardian(self.guardian2_name, self.guardian2_vat)
            guardian.write({'afa_family_id': family.id})

        for student in self.student_ids:
            self.env['res.partner'].create(
                {
                    'name': student.name,
                    'afa_birthdate': student.birthday,
                    'afa_family_id': family.id,
                    'afa_family_role': 'student',
                    'afa_course_id': student.course_id.id,
                }
            )

        if self.wants_membership:
            normalized_iban = ''.join(self.iban.split()).upper()
            bank = payer.bank_ids.sudo().filtered(
                lambda account: ''.join(account.acc_number.split()).upper() == normalized_iban
            )[:1]
            if not bank:
                bank = (
                    self.env['res.partner.bank']
                    .sudo()
                    .create({'acc_number': normalized_iban, 'partner_id': payer.id})
                )
            self.env['account.banking.mandate'].sudo().create(
                {
                    'partner_bank_id': bank.id,
                    'company_id': self.company_id.id,
                    'format': 'sepa',
                    'type': 'recurrent',
                    'scheme': 'CORE',
                    'signature_date': self.mandate_accepted_at.date(),
                    'state': 'draft',
                }
            )

        self.write(
            {
                'state': 'approved',
                'family_id': family.id,
                'reviewed_by_id': self.env.user.id,
                'reviewed_at': fields.Datetime.now(),
            }
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Family'),
            'res_model': 'afa.family',
            'res_id': family.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_reject(self):
        self.ensure_one()
        self._check_manager()
        self._lock_for_review()
        if self.state != 'pending':
            raise UserError(_('Only pending applications can be rejected.'))
        self.write(
            {
                'state': 'rejected',
                'reviewed_by_id': self.env.user.id,
                'reviewed_at': fields.Datetime.now(),
            }
        )
        return True

    def _lock_for_review(self):
        self.env.cr.execute(
            'SELECT id FROM afa_membership_application WHERE id = %s FOR UPDATE',
            [self.id],
        )
        self.invalidate_recordset(['state'])

    def _get_or_create_guardian(self, name, vat, **extra_values):
        Partner = self.env['res.partner']
        normalized_vat = vat.strip().upper()
        self.env.cr.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', [normalized_vat])
        partner = Partner.sudo().search([('vat', '=ilike', normalized_vat)], limit=2)
        if len(partner) > 1:
            raise UserError(_('More than one contact uses guardian ID %s.') % vat)
        values = {
            'name': name.strip(),
            'vat': normalized_vat,
            'afa_family_role': 'guardian',
            **{key: value for key, value in extra_values.items() if value},
        }
        if partner:
            if partner.afa_family_id or partner.afa_family_role == 'student':
                raise UserError(
                    _('Guardian ID %s already belongs to an assigned family contact.') % vat
                )
            partner.write(values)
            return partner
        return Partner.create(values)


class AfaMembershipApplicationStudent(models.Model):
    _name = 'afa.membership.application.student'
    _description = 'AFA Membership Application Student'
    _order = 'id'

    application_id = fields.Many2one(
        'afa.membership.application', required=True, ondelete='cascade', index=True
    )
    name = fields.Char(required=True, groups='afa_family.group_family_manager')
    birthday = fields.Date(required=True, groups='afa_family.group_family_manager')
    course_id = fields.Many2one(
        'afa.school.course', required=True, groups='afa_family.group_family_manager'
    )

    @api.constrains('name', 'birthday', 'course_id')
    def _check_student(self):
        for student in self:
            if not student.name or not student.birthday or not student.course_id:
                raise ValidationError(_('Student name, birth date and course are required.'))
            if student.birthday > fields.Date.context_today(student):
                raise ValidationError(_('A student birth date cannot be in the future.'))
