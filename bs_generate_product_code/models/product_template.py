# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    has_duplicate_code = fields.Boolean(
        string="Duplicate Reference",
        compute="_compute_has_duplicate_code",
        search="_search_has_duplicate_code",
        help="One of this product's variants shares its internal reference "
        "with another product.",
    )

    def _compute_has_duplicate_code(self):
        variants = self.with_context(active_test=False).product_variant_ids
        duplicates = set(
            self.env["product.product"]._duplicate_codes(variants.mapped("default_code"))
        )
        for template in self:
            template.has_duplicate_code = any(
                code in duplicates
                for code in template.with_context(
                    active_test=False
                ).product_variant_ids.mapped("default_code")
            )

    def _search_has_duplicate_code(self, operator, value):
        if operator != "in":
            return NotImplemented
        return [
            (
                "product_variant_ids.default_code",
                "in",
                self.env["product.product"]._duplicate_codes(),
            )
        ]

    def write(self, vals):
        """Rebuild the variants' references when the template changes.

        The product form edits the template, and a field the variants inherit
        from it - the category, say - is written there without ever passing
        through the variants' own write.
        """
        variants = self._code_variants()
        if not variants._code_follows(vals):
            return super().write(vals)
        generated = variants._rendered_codes()
        result = super().write(vals)
        variants.exists()._follow_rules(generated)
        return result

    def _code_variants(self):
        # Archived variants keep a reference too, and it should not go stale.
        return self.env["product.product"].browse(
            self.with_context(active_test=False).product_variant_ids.ids
        )

    def action_preview_default_code(self):
        """Preview Generate Internal Reference for every variant at once.

        Odoo has no list of variants across products, so selecting products
        here is how references are rebuilt in bulk.
        """
        return self.product_variant_ids.action_preview_default_code()
