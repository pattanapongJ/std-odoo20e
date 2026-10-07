# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductCodePreviewLine(models.TransientModel):
    _name = "product.code.preview.line"
    _description = "Product Code Preview Line"

    wizard_id = fields.Many2one("product.code.preview", required=True, ondelete="cascade")
    selected = fields.Boolean(string="Apply")
    product_id = fields.Many2one("product.product", required=True, ondelete="cascade")
    rule_id = fields.Many2one("product.code.rule", string="Rule")
    current_code = fields.Char(string="Current Reference")
    new_code = fields.Char(string="New Reference")
    state = fields.Selection(
        [
            ("change", "Will change"),
            ("same", "Already up to date"),
            ("broken", "Rule cannot be read"),
            ("skip", "No rule applies"),
        ],
        required=True,
    )
    is_duplicate = fields.Boolean(
        string="Duplicate",
        help="Another product already holds this reference, or another line "
        "would build it too.",
    )
    is_typed = fields.Boolean(
        string="Typed",
        help="The current reference was not built by a code rule: it was typed "
        "or imported, so replacing it may lose information.",
    )
    is_used = fields.Boolean(
        string="Used",
        help="A stock move, order, invoice, POS or BoM line already refers to "
        "this product, so its current reference may be printed or sent.",
    )
