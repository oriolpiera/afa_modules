def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_model_data
           SET noupdate = TRUE
         WHERE module = 'afa_website'
           AND noupdate IS DISTINCT FROM TRUE
        """
    )
