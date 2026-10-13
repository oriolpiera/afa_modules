from odoo import http
from odoo.http import request

from .. import file_format


class FamilyImportController(http.Controller):
    @http.route('/afa_family_import/template', type='http', auth='user', methods=['GET'])
    def template(self, **kwargs):
        if not request.env.su and not request.env.user.has_group('afa_family.group_family_manager'):
            raise request.not_found()
        return request.make_response(
            file_format.TEMPLATE_CSV,
            headers=[
                ('Content-Type', 'text/csv; charset=utf-8'),
                ('Content-Disposition', 'attachment; filename="afa_families.csv"'),
            ],
        )
