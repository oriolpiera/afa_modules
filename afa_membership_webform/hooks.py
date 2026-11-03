_GOOGLE_FORM_URL = (
    'https://docs.google.com/forms/d/e/'
    '1FAIpQLSeZgDKoprOUT2a007GsZJEpcfo_XtMCHfU0uhp86EvVCfhLvA/viewform'
)


def post_init_hook(env):
    """Point the existing website's membership links to the Odoo form."""
    home = env['website.page'].search([('url', '=', '/')], limit=1)
    if home and _GOOGLE_FORM_URL in home.arch:
        home.write({'arch': home.arch.replace(_GOOGLE_FORM_URL, '/alta-socia')})
