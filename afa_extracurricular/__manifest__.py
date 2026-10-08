{
    'name': 'AFA Extracurriculars',
    'version': '19.0.1.0.0',
    'summary': 'Extracurricular groups, schedules and student enrollments',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': ['afa_service_subscription'],
    'data': [
        'security/ir.model.access.csv',
        'views/extracurricular_views.xml',
        'views/subscription_views.xml',
        'views/partner_views.xml',
    ],
    'installable': True,
    'application': False,
}
