# -*- coding: utf-8 -*-

from odoo import api, fields, models


class BsLabelPrintWizardLine(models.TransientModel):
    _inherit = "bs.label.print.wizard.line"

    tracking = fields.Selection(related="product_id.tracking")
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot/Serial",
        domain="[('product_id', '=', product_id)]",
    )

    @api.onchange("product_id")
    def _onchange_product_id_lot(self):
        # tracking is False for an untracked product ("none" is gone in 20).
        if self.lot_id and (not self.product_id.tracking or self.lot_id.product_id != self.product_id):
            self.lot_id = False

    def _label_line(self):
        values = super()._label_line()
        # A lot only means something for a product tracked by lot or serial.
        values["lot_id"] = self.lot_id.id if self.product_id.tracking and self.lot_id else False
        return values
