{
    'name': 'AFA Accounting Reconciliation',
    'version': '19.0.1.0.0',
    'summary': 'Use family billing guardians in accounting and bank reconciliation',
    'category': 'Accounting',
    'license': 'LGPL-3',
    'depends': ['afa_family', 'account_statement_base', 'account_reconcile_oca'],
    'data': [
        'views/account_bank_statement_line_views.xml',
    ],
    'installable': True,
    'application': False,
}
