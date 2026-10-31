from odoo import fields


def prepare_preview(env):
    env['account.chart.template'].try_loading('generic_coa', env.company)
    sales_journal = env['account.journal'].search(
        [('company_id', '=', env.company.id), ('type', '=', 'sale')], limit=1
    )
    inbound_method = env['account.payment.method'].search(
        [('payment_type', '=', 'inbound')], limit=1
    )
    payment_mode = env['account.payment.mode'].create(
        {
            'name': 'Preview Direct Debit',
            'company_id': env.company.id,
            'payment_method_id': inbound_method.id,
            'bank_account_link': 'variable',
        }
    )

    service = env.ref('afa_extracurricular.demo_chess_club')
    subscription = env.ref('afa_extracurricular.demo_chess_enrollment')
    service.write(
        {
            'invoice_journal_id': sales_journal.id,
            'payment_mode_id': payment_mode.id,
        }
    )
    assert subscription.service_id == service

    month_start = fields.Date.context_today(env.user).replace(day=1)
    billing_preview = env['afa.service.billing'].create({'month': month_start})
    billing_preview.action_preview()
    preview_line = billing_preview.line_ids.filtered(
        lambda line: line.subscription_id.service_id == service
    )
    assert len(preview_line) == 1 and preview_line.discount_amount == 5.0
    assert preview_line.include and not preview_line.reason

    env.cr.commit()
    print(f'Prepared a current-month billing preview for {service.display_name}.')
