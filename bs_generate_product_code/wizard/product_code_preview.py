# -*- coding: utf-8 -*-

from odoo import api, fields, models

from ..models.product_code_rule_line import UnreadablePath


class ProductCodePreview(models.TransientModel):
    """What Generate Internal Reference would do, shown before it does it.

    Rewriting references in bulk cannot be undone from the interface, and a
    running number, once taken, is not given back. So the action lists every
    change first and applies only the ones left ticked.
    """

    _name = "product.code.preview"
    _description = "Product Code Preview"

    line_ids = fields.One2many("product.code.preview.line", "wizard_id", string="Products")
    change_count = fields.Integer(compute="_compute_counts")
    same_count = fields.Integer(compute="_compute_counts")
    skip_count = fields.Integer(compute="_compute_counts")
    broken_count = fields.Integer(compute="_compute_counts")
    duplicate_count = fields.Integer(compute="_compute_counts")
    used_count = fields.Integer(compute="_compute_counts")
    typed_count = fields.Integer(compute="_compute_counts")

    @api.depends(
        "line_ids.state", "line_ids.is_duplicate", "line_ids.is_used", "line_ids.is_typed"
    )
    def _compute_counts(self):
        for wizard in self:
            states = wizard.line_ids.mapped("state")
            wizard.change_count = states.count("change")
            wizard.same_count = states.count("same")
            wizard.skip_count = states.count("skip")
            wizard.broken_count = states.count("broken")
            wizard.duplicate_count = len(wizard.line_ids.filtered("is_duplicate"))
            wizard.used_count = len(wizard.line_ids.filtered("is_used"))
            wizard.typed_count = len(wizard.line_ids.filtered("is_typed"))

    @api.model
    def _open_for(self, products):
        """Build the preview for ``products`` and return the action showing it."""
        rules = self.env["product.code.rule"]._rules_for(products)
        counters = {}
        rows = []
        for product in products:
            rule = rules.get(product.id)
            current = product.default_code or ""
            try:
                code = rule._render(product, counters) if rule else ""
            except UnreadablePath:
                code, state = "", "broken"
            else:
                state = "skip" if not code else "same" if code == current else "change"
            rows.append({
                "product_id": product.id,
                "rule_id": rule.id if rule else False,
                "current_code": current,
                "new_code": code,
                "state": state,
                "selected": state == "change",
            })
        changing = products.browse(
            [row["product_id"] for row in rows if row["state"] == "change"]
        )
        used = set(changing._used_products().ids) if changing else set()
        for row in rows:
            if row["product_id"] in used:
                row["is_used"] = True
                # Manual generation overrides freezing, but on purpose only.
                row["selected"] = not rules[row["product_id"]]._freezes_once_used()
        generated = self.env["product.code.history"]._generated_pairs(changing)
        for row in rows:
            if (
                row["state"] == "change"
                and row["current_code"]
                and (row["product_id"], row["current_code"]) not in generated
            ):
                # Typed or imported: replacing it is a decision to take per line.
                row["is_typed"] = True
                row["selected"] = False
        new_codes = {row["new_code"] for row in rows if row["state"] == "change"}
        taken = self._codes_held_elsewhere(new_codes, products)
        seen = set()
        for row in rows:
            if row["state"] != "change":
                continue
            code = row["new_code"]
            # Held by a product outside the selection, or built twice within it.
            row["is_duplicate"] = code in taken or code in seen
            seen.add(code)
        order = {"change": 0, "broken": 1, "same": 2, "skip": 3}
        rows.sort(key=lambda row: order[row["state"]])
        wizard = self.create({"line_ids": [fields.Command.create(row) for row in rows]})
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Generate Internal Reference"),
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def _codes_held_elsewhere(self, codes, products):
        if not codes:
            return set()
        held = self.env["product.product"].sudo().with_context(active_test=False).search_fetch(
            [("default_code", "in", list(codes)), ("id", "not in", products.ids)],
            ["default_code"],
        )
        return set(held.mapped("default_code"))

    def action_apply(self):
        """Generate the ticked products' references.

        Generation runs again rather than copying the preview: it takes the
        rule lock, and a running number reflects what exists when applied.
        """
        self.ensure_one()
        products = self.line_ids.filtered(
            lambda line: line.selected and line.state == "change"
        ).product_id
        return products.action_generate_default_code()
