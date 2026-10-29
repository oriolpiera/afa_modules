import json

from odoo import http
from odoo.http import request


class AttendanceKioskPwaController(http.Controller):
    @http.route(
        '/hr_attendance/pwa_manifest/<token>',
        type='http',
        auth='public',
        methods=['GET'],
        website=True,
        sitemap=False,
    )
    def kiosk_manifest(self, token):
        company = (
            request.env['res.company']
            .sudo()
            .search(
                [('attendance_kiosk_key', '=', token)],
                limit=1,
            )
        )
        if not company:
            return request.not_found()

        manifest_path = request.httprequest.path
        kiosk_path = manifest_path.rsplit('/pwa_manifest/', 1)[0] + '/' + token
        manifest = {
            'id': kiosk_path,
            'name': 'Attendance Kiosk',
            'short_name': 'Attendance',
            'description': 'Employee attendance kiosk',
            'start_url': kiosk_path,
            'scope': kiosk_path,
            'display': 'standalone',
            'background_color': '#ffffff',
            'theme_color': '#16864d',
            'icons': [
                {
                    'src': '/afa_attendance_kiosk_pwa/static/src/img/kiosk-192.png',
                    'sizes': '192x192',
                    'type': 'image/png',
                    'purpose': 'any maskable',
                },
                {
                    'src': '/afa_attendance_kiosk_pwa/static/src/img/kiosk-512.png',
                    'sizes': '512x512',
                    'type': 'image/png',
                    'purpose': 'any maskable',
                },
            ],
        }
        return request.make_response(
            json.dumps(manifest),
            headers=[
                ('Content-Type', 'application/manifest+json; charset=utf-8'),
                ('Cache-Control', 'no-store'),
                ('X-Content-Type-Options', 'nosniff'),
            ],
        )
