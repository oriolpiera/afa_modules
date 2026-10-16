{
    'name': 'AFA Acollida Fixed Fees',
    'version': '19.0.1.0.0',
    'summary': 'Import and invoice fixed Acollida fees from a monthly spreadsheet',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': ['afa_service_subscription', 'afa_school_course'],
    'data': [
        'security/ir.model.access.csv',
        'views/acollida_views.xml',
        'wizard/import_views.xml',
        'wizard/billing_views.xml',
    ],
    'installable': True,
    'application': False,
}
