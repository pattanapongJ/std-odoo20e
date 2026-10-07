# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Record the references earlier versions built, so they are not mistaken
    for typed ones. A reference counts when it is still what its rule builds;
    one that has gone stale since cannot be told from a typed one."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Archived products too, but not archived rules: browse them back.
    products = env["product.product"].browse(
        env["product.product"].with_context(active_test=False).search(
            [("default_code", "!=", False)]
        ).ids
    )
    rules = env["product.code.rule"]._rules_for(products)
    rendered = products._rendered_codes()
    env["product.code.history"]._record([
        {
            "product_id": product.id,
            "new_code": product.default_code,
            "rule_id": rules[product.id].id,
        }
        for product in products
        if rendered.get(product.id) == product.default_code
    ])
