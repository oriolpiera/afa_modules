{
    'name': 'AFA SEPA Collections',
    'version': '19.0.1.0.0',
    'summary': 'Family-linked SEPA Core direct debit orders',
    'category': 'Accounting',
    'license': 'AGPL-3',
    'depends': ['afa_membership', 'account_banking_sepa_direct_debit'],
    'data': [
        'security/ir.model.access.csv',
        'views/collection_views.xml',
        'wizard/collection_wizard_views.xml',
    ],
    'installable': True,
}
