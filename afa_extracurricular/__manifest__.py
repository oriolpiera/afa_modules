{
    'name': 'AFA Extracurriculars',
    'version': '19.0.3.0.0',
    'summary': 'Extracurricular groups, schedules and student enrollments',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': ['afa_service_subscription', 'afa_school_course'],
    'data': [
        'security/ir.model.access.csv',
        'views/extracurricular_views.xml',
        'views/subscription_views.xml',
        'views/partner_views.xml',
        'wizard/extracurricular_import_views.xml',
    ],
    'demo': ['demo/extracurricular_demo.xml'],
    'installable': True,
    'application': False,
}
