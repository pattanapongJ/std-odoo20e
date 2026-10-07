# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.exceptions import UserError


class ReportBsLabelDocument(models.AbstractModel):
    _name = "report.bs_product_label.label_document"
    _description = "Label Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        profile = self.env["bs.label.profile"].browse(data.get("profile_id")).exists()
        if not profile:
            raise UserError(self.env._("The label profile of this print no longer exists."))
        pricelist = self.env["product.pricelist"].browse(data.get("pricelist_id") or []).exists()
        return profile._render_values(
            data.get("lines") or [], pricelist, test=bool(data.get("test"))
        )


class ReportBsLabelDocumentZpl(models.AbstractModel):
    _name = "report.bs_product_label.label_document_zpl"
    _inherit = "report.bs_product_label.label_document"
    _description = "Label Report (ZPL)"

    @api.model
    def _get_report_values(self, docids, data=None):
        values = super()._get_report_values(docids, data)
        values["zpl"] = values["profile"]._render_zpl(values["pages"])
        return values
