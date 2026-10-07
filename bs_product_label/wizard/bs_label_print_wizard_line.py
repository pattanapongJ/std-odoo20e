# -*- coding: utf-8 -*-

from odoo import fields, models


class BsLabelPrintWizardLine(models.TransientModel):
    _name = "bs.label.print.wizard.line"
    _description = "Print Labels Line"
    _order = "sequence, id"

    wizard_id = fields.Many2one("bs.label.print.wizard", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one("product.product", string="Product", required=True)
    quantity = fields.Integer(default=1, required=True)
    extra_text = fields.Char(help="Printed on this line's labels only.")
    source = fields.Char(readonly=True, help="Where the line came from, e.g. a transfer.")

    def _label_line(self):
        """This line as the dict a label is printed from. Extend it to carry
        more (a lot, a package) to _prepare_label_values."""
        self.ensure_one()
        return {
            "product_id": self.product_id.id,
            "quantity": self.quantity,
            "extra_text": self.extra_text or "",
            "source": self.source or "",
        }
