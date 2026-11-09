import hashlib
import hmac

from psycopg2 import IntegrityError

from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request


class AfaVotingController(http.Controller):
    @http.route(
        '/afa/vote',
        type='http',
        auth='public',
        website=True,
        methods=['GET'],
        sitemap=False,
    )
    def voting_link_landing(self, **_kwargs):
        response = request.render('afa_voting.voting_link_landing')
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @http.route(
        '/afa/vote/open',
        type='http',
        auth='public',
        website=True,
        methods=['POST'],
        sitemap=False,
    )
    def voting_page(self, **_kwargs):
        token = (request.httprequest.form.get('token') or '').strip()
        invitation = self._find_invitation(token)
        if not invitation or not self._is_usable(invitation):
            return self._generic_error()
        response = request.render(
            'afa_voting.voting_page',
            {
                'voting': invitation.voting_id,
                'options': invitation.voting_id.option_ids,
                'token': token,
                'error': False,
            },
        )
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @http.route(
        '/afa/vote/submit',
        type='http',
        auth='public',
        website=True,
        methods=['POST'],
        sitemap=False,
    )
    def submit_vote(self, **_kwargs):
        form = request.httprequest.form
        token = (form.get('token') or '').strip()
        option_id = form.get('option_id') or ''
        if not token or not option_id.isdigit():
            return self._generic_error()
        invitation = self._find_invitation(token)
        if not invitation:
            return self._generic_error()
        invitation = invitation.sudo()
        request.env.cr.execute(
            'SELECT id FROM afa_voting_invitation WHERE id = %s FOR UPDATE', [invitation.id]
        )
        invitation.invalidate_recordset()
        if not self._is_usable(invitation):
            return self._generic_error()
        option = request.env['afa.voting.option'].sudo().browse(int(option_id)).exists()
        if not option or option.voting_id != invitation.voting_id:
            return self._generic_error()
        try:
            with request.env.cr.savepoint():
                request.env['afa.voting.vote'].sudo().with_context(_voting_cast_vote=True).create(
                    {
                        'voting_id': invitation.voting_id.id,
                        'family_id': invitation.family_id.id,
                        'invitation_id': invitation.id,
                        'recipient_partner_id': invitation.recipient_partner_id.id,
                        'option_id': option.id,
                        'voted_at': fields.Datetime.now(),
                    }
                )
                invitation._workflow_write(
                    {
                        'state': 'voted',
                        'voted_at': fields.Datetime.now(),
                        'token_hash': False,
                    }
                )
        except (IntegrityError, UserError, ValidationError):
            return self._generic_error()
        return request.render('afa_voting.voting_confirmation')

    @staticmethod
    def _find_invitation(token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        invitation = (
            request.env['afa.voting.invitation']
            .sudo()
            .search([('token_hash', '=', digest)], limit=1)
        )
        if invitation and not hmac.compare_digest(invitation.token_hash or '', digest):
            return request.env['afa.voting.invitation']
        return invitation

    @staticmethod
    def _is_usable(invitation):
        now = fields.Datetime.now()
        voting = invitation.voting_id
        return bool(
            invitation.state == 'pending'
            and invitation.token_hash
            and voting.state == 'open'
            and voting.date_start <= now <= voting.date_end
        )

    @staticmethod
    def _generic_error():
        response = request.render('afa_voting.voting_unavailable', {})
        response.status_code = 400
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response
