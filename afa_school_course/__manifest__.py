{
    'name': 'AFA School Courses',
    'version': '19.0.1.0.0',
    'summary': 'School course ladder and annual student promotion',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': ['afa_service_subscription'],
    'data': [
        'security/ir.model.access.csv',
        'views/course_views.xml',
        'wizard/promotion_views.xml',
    ],
    'installable': True,
    'application': False,
}
