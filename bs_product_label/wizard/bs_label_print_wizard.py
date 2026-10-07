# -*- coding: utf-8 -*-

import math

from odoo import api, fields, models
from odoo.exceptions import UserError


class BsLabelPrintWizard(models.TransientModel):
    """Choose a profile, adjust quantities, preview, print."""

    _name = "bs.label.print.wizard"
    _description = "Print Labels"

    profile_id = fields.Many2one(
        "bs.label.profile",
        string="Label",
        required=True,
        default=lambda self: self._default_profile(),
        domain="['|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]",
    )
    output = fields.Selection(related="profile_id.output")
    show_price = fields.Boolean(related="profile_id.show_price")
    pricelist_id = fields.Many2one("product.pricelist")
    line_ids = fields.One2many("bs.label.print.wizard.line", "wizard_id", string="Products")
    label_count = fields.Integer(compute="_compute_counts")
    page_count = fields.Integer(compute="_compute_counts")
    preview_html = fields.Html(compute="_compute_preview_html", sanitize=False)

    @api.model
    def _default_profile(self):
        # ir.default brings the user's last profile first; this is the fallback.
        return self.env["bs.label.profile"].search([], limit=1)

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if "profile_id" in fields_list:
            # User defaults can outlive a company switch or profile archival.
            profile = self.env["bs.label.profile"].search([
                ("id", "=", defaults.get("profile_id") or 0),
                "|", ("company_id", "=", False),
                ("company_id", "in", self.env.companies.ids),
            ], limit=1)
            defaults["profile_id"] = (profile or self._default_profile()).id
        return defaults

    @api.onchange("profile_id")
    def _onchange_profile_id(self):
        self.pricelist_id = self.profile_id.pricelist_id

    @api.depends("line_ids.quantity", "profile_id")
    def _compute_counts(self):
        for wizard in self:
            count = sum(max(line.quantity, 0) for line in wizard.line_ids)
            per_page = wizard.profile_id.labels_per_page or 1
            wizard.label_count = count
            wizard.page_count = math.ceil(count / per_page) if count else 0

    @api.depends(
        "profile_id", "pricelist_id", "line_ids.product_id", "line_ids.quantity",
        "line_ids.extra_text",
    )
    def _compute_preview_html(self):
        for wizard in self:
            lines = wizard._label_lines()
            wizard.preview_html = (
                wizard.profile_id._render_preview(lines, wizard.pricelist_id)
                if wizard.profile_id and lines else False
            )

    # ------------------------------------------------------------------
    # Opening
    # ------------------------------------------------------------------

    @api.model
    def _action_open(self, records):
        """Open the dialog with a line per thing to label in ``records``."""
        lines = self._lines_from_records(records)
        if not lines:
            raise UserError(self.env._("There is nothing to print a label for in the selection."))
        wizard = self.create({"line_ids": [fields.Command.create(line) for line in lines]})
        wizard._onchange_profile_id()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Print Labels"),
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    @api.model
    def action_open_blank(self):
        """The dialog with no products yet, for a menu: shelf labels or a
        price change, printed without first finding the products."""
        wizard = self.create({})
        wizard._onchange_profile_id()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Print Labels"),
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    @api.model
    def _lines_from_records(self, records):
        """Dispatch to ``_lines_from_<model>``: a module adds a place to print
        from by adding that method and binding the server action."""
        method = getattr(self, "_lines_from_%s" % records._name.replace(".", "_"), None)
        if not method:
            raise UserError(self.env._("Labels cannot be printed from %s.", records._description))
        return method(records)

    @api.model
    def _lines_from_product_template(self, templates):
        return self._lines_from_product_product(templates.product_variant_ids)

    @api.model
    def _lines_from_product_product(self, products):
        return [{"product_id": product.id, "quantity": 1} for product in products]

    # ------------------------------------------------------------------
    # Printing
    # ------------------------------------------------------------------

    def _label_lines(self):
        """The lines as plain dicts, what the report receives."""
        self.ensure_one()
        return [
            line._label_line() for line in self.line_ids
            if line.product_id and line.quantity > 0
        ]

    def action_print(self):
        self.ensure_one()
        lines = self._label_lines()
        if not lines:
            raise UserError(self.env._("Set a quantity on at least one product."))
        self.profile_id._expand_lines(lines)  # the label limit, before the report runs
        self.env["ir.default"].set(
            self._name, "profile_id", self.profile_id.id, user_id=self.env.uid,
            company_id=self.env.company.id
        )
        action = self.profile_id._print(lines, self.pricelist_id)
        action["close_on_report_download"] = True
        return action
