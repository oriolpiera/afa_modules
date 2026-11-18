from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAfaSepaTemplateData(TransactionCase):
    def test_return_notification_template_is_noupdate(self):
        template_data = self.env['ir.model.data'].search(
            [
                ('module', '=', 'afa_sepa'),
                ('name', '=', 'mail_template_return_notification'),
            ],
            limit=1,
        )

        self.assertTrue(template_data)
        self.assertTrue(template_data.noupdate)
