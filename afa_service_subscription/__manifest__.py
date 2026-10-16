{
    'name': 'AFA Monthly Service Subscriptions',
    'version': '19.0.2.0.0',
    'summary': 'Staff-managed student subscriptions and monthly family invoices',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': ['afa_membership', 'account_payment_mode'],
    'data': [
        'security/ir.model.access.csv',
        'views/service_views.xml',
        'wizard/billing_views.xml',
    ],
    'installable': True,
    'application': False,
}
