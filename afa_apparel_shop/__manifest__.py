{
    'name': 'AFA Apparel Shop',
    'author': 'Oriol Piera',
    'version': '19.0.1.2.0',
    'summary': 'Reserve website stock for AFA bank-transfer orders',
    'category': 'Sales',
    'license': 'LGPL-3',
    'depends': ['afa_member_pricing', 'payment_custom', 'website_sale_stock'],
    'data': [
        'data/ir_cron.xml',
        'views/delivery_carrier_views.xml',
        'views/sale_order_views.xml',
        'views/templates.xml',
    ],
    'demo': ['demo/apparel_stock_demo.xml'],
    'assets': {
        'web.assets_frontend': [
            'afa_apparel_shop/static/src/interactions/checkout.js',
        ],
    },
    'installable': True,
    'application': False,
}
