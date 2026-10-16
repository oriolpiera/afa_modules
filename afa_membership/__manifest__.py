{
    'name': 'AFA Membership',
    'version': '19.0.2.0.0',
    'summary': 'Family membership intention and school-year dues',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': ['afa_family', 'account', 'product'],
    'data': [
        'security/ir.model.access.csv',
        'views/membership_views.xml',
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'application': False,
}
