# -*- coding: utf-8 -*-

from odoo import api, models


class ProductAttributeValue(models.Model):
    _inherit = "product.attribute.value"

    def _column_option(self):
        return f"value_{self.id}"

    # The values are the options of their attribute's column.

    @api.model_create_multi
    def create(self, vals_list):
        values = super().create(vals_list)
        if any(values.attribute_id.mapped("variant_column")):
            self.env["product.attribute"]._sync_column_definition()
        return values

    def write(self, vals):
        result = super().write(vals)
        if {"name", "sequence", "attribute_id"} & set(vals) and any(
            self.attribute_id.mapped("variant_column")
        ):
            self.env["product.attribute"]._sync_column_definition()
        return result

    def unlink(self):
        had_column = any(self.attribute_id.mapped("variant_column"))
        result = super().unlink()
        if had_column:
            self.env["product.attribute"]._sync_column_definition()
        return result
