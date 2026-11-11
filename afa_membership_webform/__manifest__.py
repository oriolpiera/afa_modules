{
    'name': 'AFA Membership Web Form',
    'author': 'Oriol Piera',
    'version': '19.0.1.0.0',
    'summary': 'Public member registration requests with manager review',
    'category': 'Website',
    'license': 'AGPL-3',
    'depends': [
        'afa_website',
        'afa_family',
        'afa_membership',
        'afa_school_course',
        'afa_sepa',
        'website',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/membership_application_views.xml',
        'views/membership_application_templates.xml',
        'views/res_partner_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'afa_membership_webform/static/src/js/membership_form.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
