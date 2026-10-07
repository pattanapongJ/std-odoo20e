# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ProductCodeHistory(models.Model):
    """A reference this module wrote, and the one it replaced.

    It is what tells a reference the rules built from one typed or imported:
    only the first appears here.
    """

    _name = "product.code.history"
    _description = "Product Reference History"
    _order = "create_date desc, id desc"

    product_id = fields.Many2one(
        "product.product", required=True, ondelete="cascade", index=True
    )
    old_code = fields.Char(string="Previous Reference")
    new_code = fields.Char(string="New Reference", required=True)
    rule_id = fields.Many2one("product.code.rule", string="Rule", ondelete="set null")

    @api.model
    def _record(self, rows):
        if rows:
            self.sudo().create(rows)

    @api.model
    def _generated_pairs(self, products):
        """``(product id, reference)`` for every reference built for ``products``."""
        if not products:
            return set()
        history = self.sudo().search_fetch(
            [("product_id", "in", products.ids)], ["product_id", "new_code"]
        )
        return {(row.product_id.id, row.new_code) for row in history}
