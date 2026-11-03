import re
from datetime import date

from odoo import _, fields, http
from odoo.http import request

from ..models.membership_application import (
    MANDATE_TERMS_VERSION,
    _normalize_guardian_id,
    _valid_guardian_id,
)

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$')
_MAX_STUDENTS = 20


class AfaMembershipWebformController(http.Controller):
    @http.route('/alta-socia', type='http', auth='public', website=True, methods=['GET'])
    def membership_form(self, **_kwargs):
        return self._render_form()

    @http.route(
        '/alta-socia/submit',
        type='http',
        auth='public',
        website=True,
        methods=['POST'],
    )
    def submit_membership_application(self, **_kwargs):
        form = request.httprequest.form
        submitted_values = self._form_values(form)

        if self._text(form.get('website_url')):
            return request.redirect('/alta-socia/gracies')
        error = self._validate(
            submitted_values['guardian1_name'],
            submitted_values['guardian1_vat'],
            submitted_values['guardian1_email'],
            submitted_values['guardian1_phone'],
            submitted_values['guardian2_name'],
            submitted_values['guardian2_vat'],
            submitted_values['guardian2_email'],
            submitted_values['guardian2_phone'],
            submitted_values['address'],
            submitted_values['wants_membership'],
            submitted_values['iban'],
            submitted_values['mandate_accepted'],
            submitted_values['student_rows'],
        )
        if error:
            return self._render_form(error, status=400, values=submitted_values)

        wants_membership = submitted_values['wants_membership'] == 'yes'
        mandate_accepted = wants_membership and submitted_values['mandate_accepted']
        application_values = {
            'name': submitted_values['guardian1_name'],
            'company_id': request.website.company_id.id,
            'family_name': _('Família de %s') % submitted_values['guardian1_name'],
            'guardian1_name': submitted_values['guardian1_name'],
            'guardian1_vat': submitted_values['guardian1_vat'],
            'guardian1_email': submitted_values['guardian1_email'],
            'guardian1_phone': submitted_values['guardian1_phone'],
            'guardian2_name': submitted_values['guardian2_name'],
            'guardian2_vat': submitted_values['guardian2_vat'],
            'guardian2_email': submitted_values['guardian2_email'],
            'guardian2_phone': submitted_values['guardian2_phone'],
            'address': submitted_values['address'],
            'wants_membership': wants_membership,
            'iban': submitted_values['iban'] if wants_membership else False,
            'mandate_accepted': mandate_accepted,
            'mandate_accepted_at': (fields.Datetime.now() if mandate_accepted else False),
            'mandate_terms_version': (MANDATE_TERMS_VERSION if mandate_accepted else False),
            'student_ids': [
                (
                    0,
                    0,
                    {
                        'name': student['name'],
                        'birthday': student['birthday'],
                        'course_id': student['course_id'],
                    },
                )
                for student in submitted_values['student_rows']
            ],
        }
        request.env['afa.membership.application'].sudo().create(application_values)
        return request.redirect('/alta-socia/gracies')

    @http.route('/alta-socia/gracies', type='http', auth='public', website=True, methods=['GET'])
    def membership_application_thanks(self, **_kwargs):
        return request.render('afa_membership_webform.membership_application_thanks')

    def _render_form(self, error=None, status=200, values=None):
        response = request.render(
            'afa_membership_webform.membership_application_form',
            {
                'courses': request.env['afa.school.course'].sudo().search([]),
                'error': error,
                'values': values or self._empty_form_values(),
            },
        )
        response.status_code = status
        if error:
            response.headers['Cache-Control'] = 'no-store'
        return response

    def _form_values(self, form):
        student_names = form.getlist('student_name')
        student_birthdays = form.getlist('student_birthday')
        student_courses = form.getlist('student_course')
        student_count = max(len(student_names), len(student_birthdays), len(student_courses), 1)
        students = []
        for index in range(student_count):
            name = self._text(student_names[index]) if index < len(student_names) else ''
            birthday = (
                self._text(student_birthdays[index]) if index < len(student_birthdays) else ''
            )
            course_value = (
                self._text(student_courses[index]) if index < len(student_courses) else ''
            )
            students.append(
                {
                    'name': name,
                    'birthday': birthday,
                    'course_id': int(course_value) if course_value.isdigit() else False,
                }
            )
        return {
            'guardian1_name': self._text(form.get('guardian1_name')),
            'guardian1_vat': _normalize_guardian_id(form.get('guardian1_vat')),
            'guardian1_email': self._text(form.get('guardian1_email')).lower(),
            'guardian1_phone': self._text(form.get('guardian1_phone')),
            'guardian2_name': self._text(form.get('guardian2_name')),
            'guardian2_vat': _normalize_guardian_id(form.get('guardian2_vat')),
            'guardian2_email': self._text(form.get('guardian2_email')).lower(),
            'guardian2_phone': self._text(form.get('guardian2_phone')),
            'address': self._text(form.get('address')),
            'wants_membership': form.get('wants_membership') or '',
            'iban': self._text(form.get('iban')).replace(' ', '').upper(),
            'mandate_accepted': form.get('mandate_accepted') == 'yes',
            'student_rows': students,
        }

    @staticmethod
    def _empty_form_values():
        return {
            'student_rows': [{'name': '', 'birthday': '', 'course_id': False}],
            'wants_membership': '',
            'mandate_accepted': False,
        }

    @staticmethod
    def _text(value):
        return (value or '').strip()

    def _validate(
        self,
        guardian1_name,
        guardian1_vat,
        guardian1_email,
        guardian1_phone,
        guardian2_name,
        guardian2_vat,
        guardian2_email,
        guardian2_phone,
        address,
        wants_membership,
        iban,
        mandate_accepted,
        student_rows,
    ):
        return (
            self._validate_guardians(
                guardian1_name,
                guardian1_vat,
                guardian2_name,
                guardian2_vat,
                guardian2_email,
                guardian2_phone,
            )
            or self._validate_contact(
                guardian1_email,
                guardian1_phone,
                guardian2_email,
                guardian2_phone,
                address,
            )
            or self._validate_students(student_rows)
            or self._validate_membership(wants_membership == 'yes', iban, mandate_accepted)
        )

    @staticmethod
    def _validate_guardians(
        guardian1_name,
        guardian1_vat,
        guardian2_name,
        guardian2_vat,
        guardian2_email,
        guardian2_phone,
    ):
        if not guardian1_name or not guardian1_vat:
            return 'Cal indicar el nom i el DNI del primer tutor o tutora.'
        if len(guardian1_name) > 120 or not _valid_guardian_id(guardian1_vat):
            return 'Reviseu la longitud del nom i del DNI del primer tutor o tutora.'
        if any((guardian2_name, guardian2_vat, guardian2_email, guardian2_phone)) and not (
            guardian2_name and guardian2_vat
        ):
            return 'Si afegiu un segon tutor o tutora, indiqueu-ne el nom i el DNI.'
        if len(guardian2_name or '') > 120 or (
            guardian2_vat and not _valid_guardian_id(guardian2_vat)
        ):
            return 'Reviseu la longitud del nom i del DNI del segon tutor o tutora.'

    @staticmethod
    def _validate_contact(
        guardian1_email,
        guardian1_phone,
        guardian2_email,
        guardian2_phone,
        address,
    ):
        if not _EMAIL_RE.fullmatch(guardian1_email):
            return 'Introduïu un correu vàlid per al primer tutor o tutora.'
        if guardian2_email and not _EMAIL_RE.fullmatch(guardian2_email):
            return 'Introduïu un correu vàlid per al segon tutor o tutora.'
        if len(guardian1_email) > 254 or len(guardian2_email) > 254:
            return 'L’adreça electrònica és massa llarga.'
        if not guardian1_phone or len(guardian1_phone) > 200 or len(guardian2_phone) > 200:
            return 'Indiqueu un telèfon vàlid per al primer tutor o tutora.'
        if not address or len(address) > 500:
            return 'Indiqueu una adreça completa vàlida.'

    def _validate_students(self, student_rows):
        if not student_rows or len(student_rows) > _MAX_STUDENTS:
            return f'Indiqueu entre 1 i {_MAX_STUDENTS} alumnes.'
        courses = request.env['afa.school.course'].sudo().search([])
        valid_course_ids = set(courses.ids)
        for student in student_rows:
            name = student['name']
            birthday = student['birthday']
            course_id = student['course_id']
            if not name or len(name) > 120 or not course_id or course_id not in valid_course_ids:
                return 'Cada alumne ha de tenir nom i un curs vàlid.'
            try:
                birth_date = date.fromisoformat(birthday)
            except ValueError:
                return 'Introduïu una data de naixement vàlida per a cada alumne.'
            if birth_date > fields.Date.context_today(request.env['afa.membership.application']):
                return 'La data de naixement no pot ser futura.'

    @staticmethod
    def _validate_membership(wants_membership, iban, mandate_accepted):
        if wants_membership:
            from ..models.membership_application import _valid_iban

            if not _valid_iban(iban):
                return 'Introduïu un IBAN vàlid.'
            if not mandate_accepted:
                return 'Per fer-se sòcia cal acceptar l’autorització de domiciliació SEPA.'
        return ''
