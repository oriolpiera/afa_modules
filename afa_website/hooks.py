def post_init_hook(env):
    website = env.ref('website.default_website', raise_if_not_found=False)
    if website and website.name == 'My Website':
        website.write({'name': 'AFA Escola La Bòbila'})
