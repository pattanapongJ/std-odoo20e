def migrate(cr, version):
    # inline editing went from top/bottom/none to on/off
    cr.execute("""
        UPDATE bs_view_layout
           SET editable = CASE WHEN editable = 'none' THEN 'off' ELSE 'on' END
         WHERE editable IN ('top', 'bottom', 'none')
    """)
