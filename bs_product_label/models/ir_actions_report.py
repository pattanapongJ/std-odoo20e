# -*- coding: utf-8 -*-

from odoo import models

LABEL_REPORTS = {
    "bs_product_label.label_document",
    "bs_product_label.label_document_zpl",
}


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def get_paperformat(self):
        """A label report takes its page size from the profile it prints.

        The profile owns its paperformat; the print action passes the profile
        in the context. Every PDF engine asks for the page size here, so this
        serves wkhtmltopdf and Paper Muncher alike.
        """
        profile_id = self.env.context.get("bs_label_profile_id")
        if profile_id and self.report_name in LABEL_REPORTS:
            profile = self.env["bs.label.profile"].sudo().browse(profile_id).exists()
            paperformat = profile.paperformat_id
            if paperformat:
                # The engines read dpi in opposite ways - wkhtmltopdf zooms by
                # 96/dpi, Paper Muncher scales by 76/dpi - and only the right
                # one prints millimetres at size. An unsaved copy carries it,
                # so printing still writes nothing.
                dpi = 76 if self._get_pdf_engine(self) == "paper-muncher" else 96
                if paperformat.dpi != dpi:
                    values = paperformat.copy_data({"dpi": dpi})[0]
                    paperformat = paperformat.new(values)
                return paperformat
        return super().get_paperformat()
