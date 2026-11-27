{
    'name': 'AFA SEPA Collections',
    'author': 'Oriol Piera',
    'version': '19.0.1.1.0',
    'summary': 'Family-linked SEPA Core direct debit orders',
    'category': 'Accounting',
    'license': 'AGPL-3',
    'depends': [
        'afa_service_subscription',
        'account_banking_sepa_direct_debit',
        'account_payment_return_import_iso20022',
        'mail',
    ],
    'data': [
        'data/return_fee_product.xml',
        'data/return_notification_template.xml',
        'security/ir.model.access.csv',
        'views/collection_views.xml',
        'views/return_fee_views.xml',
        'wizard/collection_wizard_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
}
