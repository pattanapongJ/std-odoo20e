# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """The attribute columns moved from the module's own container to core's
    properties.base.definition. The variants' values keep their keys, so only
    the definition needs writing again; the old container goes with its model.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["product.attribute"]._sync_column_definition()
    # Odoo forgets a removed model but leaves its table behind.
    cr.execute("DROP TABLE IF EXISTS bs_product_attribute_column_set CASCADE")
