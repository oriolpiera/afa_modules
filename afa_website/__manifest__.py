{
    'name': 'AFA Website',
    'author': 'Oriol Piera',
    'version': '19.0.1.1.0',
    'summary': 'A welcoming public website for AFA Escola La Bòbila',
    'category': 'Website',
    'license': 'LGPL-3',
    'depends': ['website'],
    'data': [
        'views/homepage.xml',
        'views/commission_pages.xml',
        'views/branding.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'afa_website/static/src/scss/afa_website.scss',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
