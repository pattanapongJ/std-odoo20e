# -*- coding: utf-8 -*-

from odoo import fields, models


class BsLabelProfile(models.Model):
    _inherit = "bs.label.profile"

    show_lot = fields.Boolean("Lot/Serial Number", default=True)
    barcode_source = fields.Selection(
        selection_add=[("lot", "Lot/Serial, else Product Barcode")],
        ondelete={"lot": "set default"},
    )

    def _prepare_label_values(self, line, pricelist=None):
        values = super()._prepare_label_values(line, pricelist)
        lot = self.env["stock.lot"].browse(line.get("lot_id") or [])
        values["lot"] = lot.name or "" if self.show_lot else ""
        return values

    def _barcode_value(self, product, line):
        if self.barcode_source == "lot":
            lot = self.env["stock.lot"].browse(line.get("lot_id") or [])
            return lot.name or product.barcode or ""
        return super()._barcode_value(product, line)

    def _text_lines(self, values):
        # The lot goes right after the variant: it matters more than notes.
        lines = super()._text_lines(values)
        lines.insert(2, (values.get("lot") or "", "small_pt"))
        return lines
