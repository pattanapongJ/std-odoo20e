# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval
from odoo.tools.sql import SQL

from .product_code_rule_line import UnreadablePath
from .res_config_settings import PARAM_FREEZE_USED

_logger = logging.getLogger(__name__)


class ProductCodeRule(models.Model):
    """A named recipe for building a product's internal reference.

    A rule owns an ordered list of lines, each contributing one piece of the
    reference. The first rule whose domain matches a product wins, so more
    specific rules are given a lower sequence than the catch-all.
    """

    _name = "product.code.rule"
    _description = "Product Code Rule"
    _order = "sequence, id"
    # _watched_fields is cached per registry and follows the rules.
    _clear_cache_name = "default"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    product_domain = fields.Char(
        string="Apply To",
        default="[]",
        help="Products this rule builds a reference for. Leave empty to match "
        "every product, and give the rule a high sequence so it acts as the "
        "fallback.",
    )
    line_ids = fields.One2many(
        "product.code.rule.line", "rule_id", string="Parts", copy=True
    )
    freeze_policy = fields.Selection(
        [
            ("setting", "As in Settings"),
            ("used", "Freeze once used"),
            ("never", "Keep following the rule"),
        ],
        string="Once Used",
        default="setting",
        required=True,
        help="Whether a product's reference keeps being rebuilt when its "
        "fields change after a stock move, order or invoice line has used it. "
        "The Generate Internal Reference action applies either way.",
    )
    example = fields.Char(
        string="Example", compute="_compute_example", store=False,
        help="What this rule produces for the first product it matches.",
    )

    @api.depends(
        "product_domain",
        "line_ids",
        "line_ids.sequence",
        "line_ids.value_type",
        "line_ids.field_path",
        "line_ids.text",
        "line_ids.prefix",
        "line_ids.suffix",
        "line_ids.separate_with",
        "line_ids.transform",
        "line_ids.length",
        "line_ids.start_number",
    )
    def _compute_example(self):
        for rule in self:
            product = rule._matching_products(
                self.env["product.product"].search(rule._domain(), limit=1)
            )
            if not product:
                rule.example = self.env._("No product matches yet")
                continue
            try:
                rule.example = rule._render(product)
            except UnreadablePath as error:
                rule.example = self.env._("Cannot read %s", error.args[0])

    @api.constrains("line_ids")
    def _check_number_boundaries(self):
        self.line_ids._check_number_boundary()

    def _freezes_once_used(self):
        self.ensure_one()
        if self.freeze_policy == "setting":
            return self.env["ir.config_parameter"].sudo().get_bool(PARAM_FREEZE_USED)
        return self.freeze_policy == "used"

    def _domain(self):
        self.ensure_one()
        try:
            return safe_eval(self.product_domain or "[]")
        except Exception:
            _logger.warning("Rule %s has an unreadable domain", self.name)
            return [("id", "=", 0)]

    def _matching_products(self, products):
        self.ensure_one()
        return products.filtered_domain(self._domain())

    @api.model
    def _rules_for(self, products):
        """Map each product to the first rule that matches it.

        One pass over the rules rather than one query per product: each rule
        filters the products still unclaimed, in memory.
        """
        assigned, remaining = {}, products
        for rule in self.search([]):
            if not remaining:
                break
            matched = rule._matching_products(remaining)
            for product in matched:
                assigned[product.id] = rule
            remaining -= matched
        return assigned

    def _render(self, product, counters=None):
        """Build the reference for one product.

        ``counters`` carries the running numbers already handed out in the
        current batch, so products generated together do not take the same one.
        """
        self.ensure_one()
        product.ensure_one()
        before, after, number_line = [], [], None
        for line in self.line_ids:
            if line.value_type == "number":
                number_line = line
                continue
            (after if number_line else before).append(line._render(product))
        before, after = "".join(before), "".join(after)
        if not number_line:
            return before
        return number_line._render_number(product, before, after, counters)

    def _lock_numbering(self):
        """Serialize generation for rules that hand out running numbers.

        Two transactions reading the same highest number would build the same
        reference. Touching the rule row makes the second one wait for the
        first, then fail with a serialization error that Odoo retries - by
        which time it sees the number the first one took.
        """
        numbered = self.filtered(
            lambda rule: "number" in rule.line_ids.mapped("value_type")
        )
        if numbered:
            self.env.cr.execute(SQL(
                "UPDATE product_code_rule SET sequence = sequence WHERE id IN %s",
                tuple(numbered.ids),
            ))

    # ------------------------------------------------------------------
    # Which product fields the rules read
    # ------------------------------------------------------------------

    @api.model
    @api.ormcache()
    def _watched_fields(self):
        """The ``product.product`` fields the rules actually look at.

        Generation has to run again when one of these changes, and no module
        may be named here: the rules themselves say what they depend on, so a
        site that builds references out of its own fields is covered without
        this module ever hearing about it.

        Only the first step of each path is kept. A change further down the
        path - the name of a category, say - reaches the product through that
        step, and watching it would mean watching every model in the database.
        """
        names = set()
        for rule in self.sudo().search([]):
            names |= rule._domain_fields()
            for line in rule.line_ids:
                if line.value_type == "field" and line.field_path:
                    names.add(line.field_path.strip().split(".")[0])
        names.discard("")
        return frozenset(names)

    def _domain_fields(self):
        """The first step of every path this rule's domain looks at."""
        self.ensure_one()
        found = set()
        for leaf in self._domain():
            # Domains also carry the operators '&', '|' and '!', which name
            # no field at all.
            if isinstance(leaf, (list, tuple)) and len(leaf) == 3:
                found.add(str(leaf[0]).split(".")[0])
        return found
