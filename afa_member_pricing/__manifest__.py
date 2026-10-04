{
    'name': 'AFA Member Pricing',
    'version': '19.0.1.0.0',
    'summary': 'Family-based member and non-member prices in sales and eCommerce',
    'category': 'Sales',
    'license': 'LGPL-3',
    'depends': ['afa_membership', 'sale', 'website_sale'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
    ],
    'demo': ['demo/apparel_demo.xml'],
    'installable': True,
    'application': False,
}
