{
    'name': 'AFA Invoice Receipts',
    'version': '19.0.1.0.0',
    'summary': 'Receipt-style customer invoice reports and emails',
    'category': 'Accounting',
    'license': 'AGPL-3',
    'depends': ['afa_sepa'],
    'data': [
        'data/mail_template.xml',
        'report/invoice_report.xml',
    ],
    'installable': True,
}
