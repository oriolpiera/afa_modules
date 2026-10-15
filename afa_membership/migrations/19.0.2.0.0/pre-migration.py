def migrate(cr, version):
    cr.execute("SELECT value FROM ir_config_parameter WHERE key = 'afa_membership.mode' LIMIT 1")
    mode = cr.fetchone()
    mode = mode[0] if mode else 'invoice'

    if mode != 'manual':
        cr.execute('UPDATE afa_family SET manual_member = FALSE WHERE manual_member')
        cr.execute(
            """
            UPDATE afa_family AS family
               SET manual_member = TRUE
             WHERE EXISTS (
                 SELECT 1
                   FROM afa_membership AS membership
                   JOIN afa_membership_period AS period
                     ON period.id = membership.period_id
                   JOIN account_move AS invoice
                     ON invoice.id = membership.invoice_id
                    AND invoice.afa_membership_id = membership.id
                  WHERE membership.family_id = family.id
                    AND membership.active
                    AND period.date_start <= CURRENT_DATE
                    AND period.date_end >= CURRENT_DATE
                    AND invoice.move_type = 'out_invoice'
                    AND invoice.state = 'posted'
                    AND invoice.payment_state = 'paid'
                    AND invoice.amount_total > 0
                    AND NOT EXISTS (
                        SELECT 1
                          FROM account_move AS refund
                         WHERE refund.reversed_entry_id = invoice.id
                           AND refund.move_type = 'out_refund'
                           AND refund.state = 'posted'
                    )
             )
            """
        )

    cr.execute("DELETE FROM ir_config_parameter WHERE key = 'afa_membership.mode'")
    cr.execute(
        """
        DELETE FROM ir_ui_view
         WHERE id IN (
             SELECT res_id
               FROM ir_model_data
              WHERE module = 'afa_membership'
                AND name = 'view_res_config_settings_afa_membership'
                AND model = 'ir.ui.view'
         )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = 'afa_membership'
           AND name = 'view_res_config_settings_afa_membership'
           AND model = 'ir.ui.view'
        """
    )
