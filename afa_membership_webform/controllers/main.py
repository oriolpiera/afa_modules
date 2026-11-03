import re
from datetime import date

from odoo import _, fields, http
from odoo.http import request

from ..models.membership_application import MANDATE_TERMS_VERSION

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$')
_MAX_STUDENTS = 20


class AfaMembershipWebformController(http.Controller):
    @http.route('/alta-socia', type='http', auth='public', website=True, methods=['GET'])
    def membership_form(self, **_kwargs):
        return request.render(
            'afa_membership_webform.membership_application_form',
            {'courses': request.env['afa.school.course'].sudo().search([])},
        )

    @http.route(
        '/alta-socia/submit',
        type='http',
        auth='public',
        website=True,
        methods=['POST'],
    )
    def submit_membership_application(self, **_kwargs):
        form = request.httprequest.form
        guardian1_name = self._text(form.get('guardian1_name'))
        guardian1_vat = self._text(form.get('guardian1_vat')).upper()
        guardian2_name = self._text(form.get('guardian2_name'))
        guardian2_vat = self._text(form.get('guardian2_vat')).upper()
        email = self._text(form.get('email')).lower()
        address = self._text(form.get('address'))
        phone_numbers = self._text(form.get('phone_numbers'))
        wants_membership = form.get('wants_membership') == 'yes'
        iban = self._text(form.get('iban')).replace(' ', '').upper()
        mandate_accepted = form.get('mandate_accepted') == 'yes'
        names = [self._text(value) for value in form.getlist('student_name')]
        birthdays = [self._text(value) for value in form.getlist('student_birthday')]
        course_ids = [self._text(value) for value in form.getlist('student_course')]

        if self._text(form.get('website_url')):
            return request.redirect('/alta-socia/gracies')
        error = self._validate(
            guardian1_name,
            guardian1_vat,
            guardian2_name,
            guardian2_vat,
            email,
            address,
            phone_numbers,
            wants_membership,
            iban,
            mandate_accepted,
            names,
            birthdays,
            course_ids,
        )
        if error:
            return self._render_form(error, status=400)

        values = {
            'name': guardian1_name,
            'company_id': request.website.company_id.id,
            'family_name': _('Família de %s') % guardian1_name,
            'guardian1_name': guardian1_name,
            'guardian1_vat': guardian1_vat,
            'guardian2_name': guardian2_name,
            'guardian2_vat': guardian2_vat,
            'email': email,
            'address': address,
            'phone_numbers': phone_numbers,
            'wants_membership': wants_membership,
            'iban': iban if wants_membership else False,
            'mandate_accepted': mandate_accepted if wants_membership else False,
            'mandate_accepted_at': fields.Datetime.now() if wants_membership else False,
            'mandate_terms_version': MANDATE_TERMS_VERSION if mandate_accepted else False,
            'student_ids': [
                (
                    0,
                    0,
                    {
                        'name': name,
                        'birthday': birthday,
                        'course_id': int(course_id),
                    },
                )
                for name, birthday, course_id in zip(names, birthdays, course_ids, strict=True)
            ],
        }
        request.env['afa.membership.application'].sudo().create(values)
        return request.redirect('/alta-socia/gracies')

    @http.route('/alta-socia/gracies', type='http', auth='public', website=True, methods=['GET'])
    def membership_application_thanks(self, **_kwargs):
        return request.render('afa_membership_webform.membership_application_thanks')

    def _render_form(self, error, status=200):
        response = request.render(
            'afa_membership_webform.membership_application_form',
            {
                'courses': request.env['afa.school.course'].sudo().search([]),
                'error': error,
            },
        )
        response.status_code = status
        return response

    @staticmethod
    def _text(value):
        return (value or '').strip()

    def _validate(
        self,
        guardian1_name,
        guardian1_vat,
        guardian2_name,
        guardian2_vat,
        email,
        address,
        phone_numbers,
        wants_membership,
        iban,
        mandate_accepted,
        names,
        birthdays,
        course_ids,
    ):
        return (
            self._validate_guardians(guardian1_name, guardian1_vat, guardian2_name, guardian2_vat)
            or self._validate_contact(email, address, phone_numbers)
            or self._validate_students(names, birthdays, course_ids)
            or self._validate_membership(wants_membership, iban, mandate_accepted)
        )

    @staticmethod
    def _validate_guardians(guardian1_name, guardian1_vat, guardian2_name, guardian2_vat):
        if not guardian1_name or not guardian1_vat:
            return 'Cal indicar el nom i el DNI del primer tutor o tutora.'
        if len(guardian1_name) > 120 or len(guardian1_vat) > 32:
            return 'Reviseu la longitud del nom i del DNI del primer tutor o tutora.'
        if bool(guardian2_name) != bool(guardian2_vat):
            return 'Si afegiu un segon tutor o tutora, indiqueu-ne el nom i el DNI.'
        if len(guardian2_name) > 120 or len(guardian2_vat) > 32:
            return 'Reviseu la longitud del nom i del DNI del segon tutor o tutora.'

    @staticmethod
    def _validate_contact(email, address, phone_numbers):
        if not _EMAIL_RE.fullmatch(email):
            return 'Introduïu una adreça electrònica vàlida.'
        if len(email) > 254:
            return 'L’adreça electrònica és massa llarga.'
        if not address or not phone_numbers:
            return 'Cal indicar l’adreça completa i almenys un telèfon de contacte.'
        if len(address) > 500 or len(phone_numbers) > 200:
            return 'Reviseu la longitud de l’adreça i dels telèfons.'

    def _validate_students(self, names, birthdays, course_ids):
        if not names or len(names) > _MAX_STUDENTS:
            return f'Indiqueu entre 1 i {_MAX_STUDENTS} alumnes.'
        if len(names) != len(birthdays) or len(names) != len(course_ids):
            return 'Reviseu les dades de cada alumne: nom, data de naixement i curs.'
        courses = request.env['afa.school.course'].sudo().search([])
        valid_course_ids = set(courses.ids)
        for name, birthday, course_id in zip(names, birthdays, course_ids, strict=True):
            if (
                not name
                or len(name) > 120
                or not course_id.isdigit()
                or int(course_id) not in valid_course_ids
            ):
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
