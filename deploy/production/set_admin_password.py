import os

env.ref('base.user_admin').write({'password': os.environ['ODOO_LOGIN_PASSWORD']})  # noqa: F821
env.cr.commit()  # noqa: F821
