{
    'name': 'AFA Membership',
    'version': '19.0.1.0.0',
    'summary': 'School-year periods and family membership links',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': ['afa_family', 'account', 'product'],
    'data': [
        'security/ir.model.access.csv',
        'views/membership_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}
