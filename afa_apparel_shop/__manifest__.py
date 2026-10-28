{
    'name': 'AFA Apparel Shop',
    'version': '19.0.1.0.0',
    'summary': 'Reserve website stock for AFA bank-transfer orders',
    'category': 'Sales',
    'license': 'LGPL-3',
    'depends': ['afa_member_pricing', 'payment_custom', 'website_sale_stock'],
    'data': [
        'data/ir_cron.xml',
        'views/sale_order_views.xml',
    ],
    'demo': ['demo/apparel_stock_demo.xml'],
    'installable': True,
    'application': False,
}
