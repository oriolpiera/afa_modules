{
    'name': 'AFA Families',
    'version': '19.0.1.0.0',
    'summary': 'Family membership and designated guardian for billing',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': ['base', 'contacts'],
    'data': [
        'security/family_groups.xml',
        'security/ir.model.access.csv',
        'security/family_rules.xml',
        'views/afa_family_views.xml',
        'views/res_partner_views.xml',
    ],
    'demo': ['demo/family_demo.xml'],
    'installable': True,
    'application': False,
}
