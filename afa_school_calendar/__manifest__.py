{
    'name': 'AFA School Calendar',
    'author': 'Oriol Piera',
    'version': '19.0.1.2.0',
    'summary': 'School year terms and automatic non-teaching days',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': ['afa_membership', 'resource', 'hr_holidays'],
    'data': [
        'security/ir.model.access.csv',
        'security/school_calendar_rules.xml',
        'views/membership_period_views.xml',
        'views/school_calendar_leaves_views.xml',
    ],
    'installable': True,
    'application': False,
}
