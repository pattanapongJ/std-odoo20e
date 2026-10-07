# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import api, fields, models


class BsLabelPrintWizard(models.TransientModel):
    _inherit = "bs.label.print.wizard"

    @api.model
    def _lines_from_stock_lot(self, lots):
        return [
            {"product_id": lot.product_id.id, "lot_id": lot.id, "quantity": 1, "source": lot.name}
            for lot in lots.filtered("product_id")
        ]

    @api.model
    def _lines_from_stock_picking(self, pickings):
        """A line per product and lot of the transfers, counted as core does.

        Done or reserved quantities when there are any, else the demand. A
        product counted in units gets one label per unit; one in another
        unit (kg, m) gets a single label.
        """
        unit = self.env.ref("uom.product_uom_unit", raise_if_not_found=False)
        quantities = defaultdict(float)
        order = []

        def add(picking, product, lot, quantity, uom):
            key = (picking.name, product.id, lot.id if lot else False)
            if key not in quantities:
                order.append(key)
            if unit and uom._has_common_reference(unit):
                quantities[key] += quantity
            else:
                quantities[key] = 1

        for picking in pickings:
            move_lines = picking.move_line_ids.filtered(lambda ml: ml.product_id and ml.quantity)
            if move_lines:
                for move_line in move_lines:
                    add(picking, move_line.product_id, move_line.lot_id, move_line.quantity, move_line.uom_id)
            else:
                for move in picking.move_ids.filtered("product_id"):
                    add(picking, move.product_id, False, move.product_uom_qty, move.uom_id)

        return [
            {
                "product_id": product_id,
                "lot_id": lot_id,
                "quantity": max(int(round(quantities[(source, product_id, lot_id)])), 1),
                "source": source,
            }
            for source, product_id, lot_id in order
        ]

    has_tracked_line = fields.Boolean(compute="_compute_has_tracked_line")

    @api.depends("line_ids.product_id")
    def _compute_has_tracked_line(self):
        for wizard in self:
            wizard.has_tracked_line = any(wizard.line_ids.product_id.mapped("tracking"))
