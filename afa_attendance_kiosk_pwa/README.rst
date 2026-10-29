Attendance Kiosk PWA
====================

Adds a web app manifest to the Odoo 19 Attendance kiosk route. The manifest is
scoped to the current company's kiosk token, starts directly in that kiosk, and
uses standalone display mode to hide Chrome's address and navigation bars.
The app requires a network connection; it does not cache attendance actions.

Install
-------

Install the ``afa_attendance_kiosk_pwa`` addon in the Odoo database. It depends
on Odoo's ``hr_attendance`` addon. In this repository's test stack, install and
test it with::

   docker compose -f compose.test.yaml run --rm odoo -d afa_kiosk_pwa_test \
     -i hr_attendance,afa_attendance_kiosk_pwa --test-enable \
     --test-tags /afa_attendance_kiosk_pwa --stop-after-init --log-level=test \
     --db_host=db --db_user=odoo --db_password=odoo

Install on Android
------------------

#. Open the company's Attendance Kiosk URL in Chrome.
#. In Chrome's menu, choose **Install app** or **Add to Home screen**.
#. Launch the new Attendance icon from the home screen. It opens in a standalone
   window without the browser address bar or navigation controls.

For an existing Odoo database, deploy the addon code to its configured addons
path, restart Odoo, update the Apps list, and install ``afa_attendance_kiosk_pwa``.

If Chrome previously created a regular shortcut, remove it and add the app again
after installing or upgrading this addon. The kiosk URL contains the access
token; keep it private and regenerate it in Attendance settings if it is exposed.

This does not lock the whole tablet: users can leave the PWA and use other apps.
