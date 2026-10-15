{
    'name': 'AFA Family Import',
    'version': '19.0.2.0.0',
    'summary': 'Initial CSV/Excel load of families, membership intent, people and IBANs',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': ['afa_family', 'afa_school_course', 'afa_sepa'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/family_import_views.xml',
    ],
    'installable': True,
    'application': False,
}
