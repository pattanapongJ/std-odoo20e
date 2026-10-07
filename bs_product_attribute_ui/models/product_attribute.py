# -*- coding: utf-8 -*-

from odoo import api, fields, models

class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    show_in_search_panel = fields.Boolean(
        string="In Filter Panel",
        default=True,
        help="Offer this attribute's values in the filter panel beside the "
        "product list.\n\n"
        "Turn it off for attributes with many values. The panel lists every "
        "value at once - it cannot be folded away - and it stops showing a "
        "section altogether once 200 values are reached. Values left out of "
        "the panel are still found by typing them in the search bar.",
    )
    variant_column = fields.Boolean(
        string="Column on Variants",
        help="Show this attribute as a column of its own in the product "
        "variant list, and offer it under Group By > Properties.\n\n"
        "Stored as a property of the variant, so switching it on or off "
        "changes no table: it rewrites the variants that carry the attribute.",
    )

    def _column_name(self):
        return f"attribute_{self.id}"

    @api.model_create_multi
    def create(self, vals_list):
        attributes = super().create(vals_list)
        if any(attributes.mapped("variant_column")):
            self._sync_column_definition()
        return attributes

    def write(self, vals):
        toggled = self.filtered(
            lambda attribute: "variant_column" in vals
            and attribute.variant_column != bool(vals["variant_column"])
        )
        result = super().write(vals)
        if toggled or ({"name", "sequence"} & set(vals) and any(self.mapped("variant_column"))):
            self._sync_column_definition()
        if toggled:
            self.env["product.product"]._variants_with_attributes(toggled)._sync_attribute_columns()
        return result

    def unlink(self):
        had_column = any(self.mapped("variant_column"))
        result = super().unlink()
        if had_column:
            self._sync_column_definition()
        return result

    @api.model
    def _sync_column_definition(self):
        """Rebuild the column definition from the attributes marked for it.

        One selection property per attribute, its options the attribute's
        values. Keys are built from ids so a rename relabels a column and an
        option without touching a single variant.
        """
        definition = self.env["product.product"]._attribute_properties_definition()
        attributes = self.sudo().search([("variant_column", "=", True)])
        definition.properties_definition = [
            {
                "name": attribute._column_name(),
                "string": attribute.name,
                "type": "selection",
                "selection": [
                    [value._column_option(), value.name] for value in attribute.value_ids
                ],
            }
            for attribute in attributes
        ]
