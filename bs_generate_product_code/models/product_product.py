# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models

from .product_code_rule_line import UnreadablePath
from .res_config_settings import PARAM_AUTOGENERATE

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = "product.product"

    has_duplicate_code = fields.Boolean(
        string="Duplicate Reference",
        compute="_compute_has_duplicate_code",
        search="_search_has_duplicate_code",
        help="Another product, archived ones included, has the same internal "
        "reference.",
    )

    def _compute_has_duplicate_code(self):
        duplicates = set(self._duplicate_codes(self.mapped("default_code")))
        for product in self:
            product.has_duplicate_code = product.default_code in duplicates

    def _search_has_duplicate_code(self, operator, value):
        if operator != "in":
            return NotImplemented
        return [("default_code", "in", self._duplicate_codes())]

    @api.model
    def _duplicate_codes(self, codes=None):
        """References held by more than one product, in any company.

        ``codes`` narrows the check to those references, so a list of products
        does not group the whole table.
        """
        domain = [("default_code", "!=", False)]
        if codes is not None:
            domain.append(("default_code", "in", [code for code in codes if code]))
        groups = self.sudo().with_context(active_test=False)._read_group(
            domain, ["default_code"], having=[("__count", ">", 1)]
        )
        return [code for (code,) in groups]

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        if not products._code_generation_enabled():
            return products
        # A reference given explicitly is a decision, and generation must not
        # undo it. Without this a catch-all rule - which the Apply To help text
        # suggests creating - would overwrite the reference of every product
        # imported or typed in with one, which is the 14.0 behaviour this
        # module exists to replace. The manual action still regenerates, since
        # asking for it is itself a decision.
        supplied = {
            product.id
            for product, vals in zip(products, vals_list)
            if vals.get("default_code")
        }
        products.filtered(
            lambda product: product.id not in supplied
        )._generate_default_code()
        return products

    def write(self, vals):
        """Rebuild the reference when what a rule reads changes.

        Generating on create alone is not enough. Odoo routinely finishes a
        record after creating it: core writes a single-value attribute onto
        variants that already exist, and a configurator hands a variant its
        combination in one step and its document line in the next. A reference
        built before those values arrived is simply wrong, and nothing ever
        went back to correct it.

        Which fields matter is asked of the rules themselves, so no module is
        named here and a site that builds references out of its own fields is
        served the same as the ones this module shipped with.
        """
        if not self._code_follows(vals):
            return super().write(vals)
        # Read before the write: a product whose reference is still what its
        # rule produced is one this module wrote, and may be rewritten. One a
        # user typed differs, and is left alone.
        generated = self._rendered_codes()
        result = super().write(vals)
        self._follow_rules(generated)
        return result

    def _code_follows(self, vals):
        """Whether writing ``vals`` may change what the rules build."""
        # A reference written explicitly is a decision, exactly as on create.
        # This also keeps generation from calling itself, since writing the
        # reference is all generation ever does.
        if not self or "default_code" in vals or not self._code_generation_enabled():
            return False
        # Asked after the switch, not before: products are written to on paths
        # that have nothing to do with references, and those must not pay for
        # reading the rules.
        return bool(
            self.env["product.code.rule"]._watched_fields().intersection(vals)
        )

    def _follow_rules(self, generated):
        """Rebuild the references that still read what ``generated`` holds.

        A blank reference is filled too: nobody relies on it yet, so neither a
        typed value nor freezing has anything to protect.
        """
        blank = self.filtered(lambda product: not product.default_code)
        followed = self.filtered(
            lambda product: product.default_code
            and product.default_code == generated.get(product.id)
        )
        (blank | (followed - followed._frozen_references()))._generate_default_code()

    def _frozen_references(self):
        """The products whose reference must no longer follow their fields.

        A reference already printed on a label or sent on an order is one
        other people rely on, so once a document uses the product its rule
        decides - or leaves to Settings - whether it may still change. Only
        automatic rebuilding stops; the manual action still applies.
        """
        rules = self.env["product.code.rule"]._rules_for(self)
        freezing = self.filtered(
            lambda product: product.id in rules
            and rules[product.id]._freezes_once_used()
        )
        return freezing._used_products() if freezing else freezing

    def _used_products(self):
        used = self.browse()
        for model, field in self._code_usage_fields():
            if model not in self.env:
                continue
            groups = self.env[model].sudo().with_context(active_test=False)._read_group(
                [(field, "in", self.ids)], [field]
            )
            used |= self.browse([product.id for (product,) in groups])
        return used

    @api.model
    def _code_usage_fields(self):
        """Documents that carry a product's reference to someone else.

        Models of modules that are not installed are skipped, so this module
        need not depend on them. Override to add a site's own documents.
        """
        return [
            ("stock.move", "product_id"),
            ("sale.order.line", "product_id"),
            ("purchase.order.line", "product_id"),
            ("account.move.line", "product_id"),
            ("pos.order.line", "product_id"),
            ("mrp.bom.line", "product_id"),
        ]

    def _rendered_codes(self):
        """What the rules produce for each of these products right now.

        Rendered in one pass, so deciding whether a reference was generated
        costs the same one search as generating it.
        """
        rules = self.env["product.code.rule"]._rules_for(self)
        counters, codes = {}, {}
        for product in self.filtered(lambda product: product.id in rules):
            try:
                codes[product.id] = rules[product.id]._render(product, counters)
            except UnreadablePath:
                continue
        return codes

    def action_preview_default_code(self):
        """Show what Generate Internal Reference would change, to confirm."""
        return self.env["product.code.preview"]._open_for(self)

    def action_generate_default_code(self):
        """Rebuild the internal reference of the selected products.

        Run by hand, so it does not consult the Settings switch - asking for it
        is the decision. Products no rule matches are left alone rather than
        blanked.
        """
        changed = self._generate_default_code()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success" if changed else "warning",
                "message": self.env._(
                    "%(changed)s reference(s) updated, %(untouched)s left as "
                    "they were.",
                    changed=len(changed),
                    untouched=len(self) - len(changed),
                ),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _generate_default_code(self):
        """Apply the first matching rule to each product.

        Returns the products it changed. A product no rule matches, or whose
        rule renders to nothing, keeps whatever reference it already had - the
        14.0 module blanked those instead.
        """
        rules = self.env["product.code.rule"]._rules_for(self)
        self.env["product.code.rule"].union(rules.values())._lock_numbering()
        counters = {}
        changed = self.browse()
        history = []
        for product in self:
            rule = rules.get(product.id)
            if not rule:
                continue
            try:
                code = rule._render(product, counters)
            except UnreadablePath:
                continue
            if not code:
                continue
            if product.default_code == code:
                # Already correct: counting it as generated would make a no-op
                # run indistinguishable from one that rewrote every reference.
                continue
            history.append({
                "product_id": product.id,
                "old_code": product.default_code,
                "new_code": code,
                "rule_id": rule.id,
            })
            product.default_code = code
            changed |= product
        self.env["product.code.history"]._record(history)
        return changed

    def _code_generation_enabled(self):
        return self.env["ir.config_parameter"].sudo().get_bool(PARAM_AUTOGENERATE)
