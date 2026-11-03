# AFA Website

This addon provides the public AFA Escola La Bòbila website in Catalan, including
the homepage, commission pages, contact form, and responsive navigation.

## Editing website content

The XML pages, menus, branding, and contact-page customization are initial data
only. After installation, use Odoo's Website editor to update the copy, images,
and menu. The records are marked `noupdate` so upgrading the addon does not
overwrite those database edits. Existing installations are protected by the
`19.0.1.1.0` pre-migration. Future code changes to these records must be applied
manually or through a deliberate migration.

## Production deployment

1. Add `afa_website` to the production Odoo addons path and deploy its files,
   including `static/src/img/`.
2. Confirm that the Odoo Website app is installed and restart Odoo so it can
   discover the addon.
3. Install `afa_website` from **Apps**, or update the database during a
   maintenance window with `odoo-bin -d <database> -u afa_website
   --stop-after-init`.
4. Verify the homepage, commission pages, mobile navigation, and contact form.
   The form sends to `hola@afabobila.cat`; confirm the production mail server can
   deliver to that address before announcing the site.
5. The **Inicia sessió** link opens `/web/login`. Family accounts and their
   access rights must be provisioned separately; this addon does not create
   users.

The pages are assigned to `website.default_website`. For multi-website databases,
review the page and menu assignments before installing.
