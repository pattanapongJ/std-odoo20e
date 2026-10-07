# -*- coding: utf-8 -*-

import base64
import math
import re
from functools import lru_cache

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import file_open
from odoo.tools.barcode import check_barcode_encoding

# Sheet sizes in mm, width x height, portrait.
SHEET_SIZES = {
    "A4": (210.0, 297.0),
    "Letter": (215.9, 279.4),
}
# Beyond this a print is almost always a mistyped quantity.
MAX_LABELS = 5000
# Fields that change the page, so the paperformat follows them.
LAYOUT_FIELDS = {
    "media", "sheet_size", "label_width_mm", "label_height_mm", "columns", "rows",
    "gap_x_mm", "gap_y_mm", "margin_top_mm", "margin_bottom_mm", "margin_left_mm",
    "margin_right_mm",
}


def _complex_script(text):
    return any(
        "\u0e00" <= char <= "\u0e7f" or "\u1000" <= char <= "\u109f"
        or "\ua9e0" <= char <= "\ua9ff" or "\uaa60" <= char <= "\uaa7f"
        for char in text
    )


@lru_cache(maxsize=1)
def _label_font_css():
    """Inline bundled fonts so report workers need no font HTTP requests."""
    rules = []
    for script in ("Myanmar", "Thai"):
        for weight, number in (("Regular", 400), ("Bold", 700)):
            path = f"bs_product_label/static/fonts/NotoSans{script}-{weight}.ttf"
            with file_open(path, "rb") as font:
                data = base64.b64encode(font.read()).decode("ascii")
            rules.append(
                f"@font-face {{font-family: 'BS Label {script}'; font-weight: {number};"
                f"src: url(data:font/ttf;base64,{data}) format('truetype');}}"
            )
    return Markup("\n".join(rules))


class BsLabelProfile(models.Model):
    """What a label is printed on, what it shows, and in which format.

    One record holds the paper and the content together: a client has a
    printer or two and a few designs, and a profile per combination reads
    better in a dropdown than two lists to match up.
    """

    _name = "bs.label.profile"
    _description = "Label Profile"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", help="Leave empty to share the profile.")

    output = fields.Selection(
        [("pdf", "PDF"), ("html", "HTML (print from the browser)"), ("zpl", "ZPL (Zebra)")],
        default="pdf",
        required=True,
    )
    media = fields.Selection(
        [("roll", "Roll"), ("sheet", "Sheet")],
        default="roll",
        required=True,
        help="Roll: a thermal roll, one row of labels per page.\n"
        "Sheet: a sticker sheet with rows and columns of labels.",
    )
    sheet_size = fields.Selection(
        [(key, key) for key in SHEET_SIZES], default="A4", required=True
    )
    label_width_mm = fields.Float("Label Width (mm)", default=50.0, required=True, digits=(16, 2))
    label_height_mm = fields.Float("Label Height (mm)", default=30.0, required=True, digits=(16, 2))
    columns = fields.Integer(default=1, required=True, help="Labels across.")
    rows = fields.Integer(default=1, required=True, help="Rows of labels on a sheet.")
    gap_x_mm = fields.Float("Gap Across (mm)", digits=(16, 2))
    gap_y_mm = fields.Float("Gap Down (mm)", digits=(16, 2))
    margin_top_mm = fields.Float("Top (mm)", digits=(16, 2))
    margin_bottom_mm = fields.Float("Bottom (mm)", digits=(16, 2))
    margin_left_mm = fields.Float("Left (mm)", digits=(16, 2))
    margin_right_mm = fields.Float("Right (mm)", digits=(16, 2))
    offset_x_mm = fields.Float(
        "Shift Right (mm)",
        digits=(16, 2),
        help="Moves every label to fix a printer that prints off target. "
        "Negative moves left.",
    )
    offset_y_mm = fields.Float(
        "Shift Down (mm)",
        digits=(16, 2),
        help="Moves every label down. Negative moves up.",
    )
    zpl_dpi = fields.Selection(
        [("203", "203 dpi (8 dots/mm)"), ("300", "300 dpi (12 dots/mm)")],
        string="Printer Resolution",
        default="203",
        required=True,
    )

    show_code = fields.Boolean("Internal Reference", default=True)
    show_name = fields.Boolean("Product Name", default=True)
    show_variant = fields.Boolean("Variant Values", default=True)
    show_price = fields.Boolean("Price")
    pricelist_id = fields.Many2one(
        "product.pricelist",
        help="Default pricelist for the price; the print dialog can change it. "
        "Without one the sales price is printed.",
    )
    custom_text = fields.Char(help="Printed on every label, e.g. the shop name.")
    barcode_source = fields.Selection(
        [
            ("barcode", "Product Barcode"),
            ("default_code", "Internal Reference"),
            ("none", "No Barcode"),
        ],
        default="barcode",
        required=True,
    )
    barcode_type = fields.Selection(
        [("QR", "QR Code"), ("Code128", "Code 128"), ("EAN13", "EAN-13")],
        default="QR",
        required=True,
        help="EAN-13 falls back to Code 128 for values that are not valid EAN-13.",
    )

    paperformat_id = fields.Many2one(
        "report.paperformat", readonly=True, copy=False, ondelete="set null"
    )
    page_width_mm = fields.Float("Page Width (mm)", compute="_compute_page", digits=(16, 2))
    page_height_mm = fields.Float("Page Height (mm)", compute="_compute_page", digits=(16, 2))
    driver_page_size = fields.Char(
        "Printer Paper Size",
        compute="_compute_page",
        help="Set the printer driver's paper to this size and print at actual size.",
    )
    labels_per_page = fields.Integer(compute="_compute_page")
    preview_html = fields.Html(compute="_compute_preview_html", sanitize=False)

    _check_positive_size = models.Constraint(
        "CHECK(label_width_mm > 0 AND label_height_mm > 0 AND columns > 0 AND rows > 0)",
        "Label size, columns and rows must be greater than zero.",
    )

    # ------------------------------------------------------------------
    # Page layout
    # ------------------------------------------------------------------

    @api.depends(*LAYOUT_FIELDS)
    def _compute_page(self):
        for profile in self:
            layout = profile._layout()
            profile.page_width_mm = layout["page_width"]
            profile.page_height_mm = layout["page_height"]
            profile.labels_per_page = layout["per_page"]
            profile.driver_page_size = "%s x %s mm" % (
                layout["paper_width"], layout["paper_height"]
            )

    def _layout(self):
        """Every measurement the templates and the paperformat need, in mm."""
        self.ensure_one()
        columns = max(self.columns, 1)
        rows = max(self.rows, 1) if self.media == "sheet" else 1
        grid_width = columns * self.label_width_mm + (columns - 1) * self.gap_x_mm
        grid_height = rows * self.label_height_mm + (rows - 1) * self.gap_y_mm
        if self.media == "sheet":
            page_width, page_height = SHEET_SIZES[self.sheet_size]
        else:
            page_width = self.margin_left_mm + grid_width + self.margin_right_mm
            page_height = self.margin_top_mm + grid_height + self.margin_bottom_mm
        height = self.label_height_mm
        return {
            "columns": columns,
            "rows": rows,
            "per_page": columns * rows,
            "label_width": self.label_width_mm,
            "label_height": height,
            "gap_x": self.gap_x_mm,
            "gap_y": self.gap_y_mm,
            "grid_width": grid_width,
            "grid_height": grid_height,
            "page_width": page_width,
            "page_height": page_height,
            # report.paperformat stores whole millimetres; rounding up keeps
            # the labels on the page, leaving under a millimetre spare.
            "paper_width": math.ceil(round(page_width, 2)),
            "paper_height": math.ceil(round(page_height, 2)),
            "margin_top": self.margin_top_mm,
            "margin_left": self.margin_left_mm,
            "offset_x": self.offset_x_mm,
            "offset_y": self.offset_y_mm,
            **self._content_layout(self.label_width_mm, height),
        }

    @api.model
    def _content_layout(self, width, height):
        """Sizes inside one label, in mm and pt, scaled to its height.

        Reading order on a shelf or a bin is name, then price, then the
        code: the name gets the weight, the price the size, the rest stays
        small but no smaller than a 203 dpi thermal head prints cleanly.
        """
        padding = min(max(round(min(width, height) * 0.05, 2), 1.0), 2.0)
        inner_width = width - 2 * padding
        inner_height = height - 2 * padding
        pt = 0.3528  # mm per point
        human_pt = min(max(round(height * 0.18, 1), 5.0), 7.5)
        linear_height = min(max(round(inner_height * 0.26, 2), 4.0), 14.0)
        qr_mm = max(round(min(inner_height, inner_width * 0.42), 2), 6.0)
        return {
            "padding": padding,
            "inner_width": inner_width,
            "inner_height": inner_height,
            "name_pt": min(max(round(height * 0.30, 1), 6.5), 13.0),
            "code_pt": min(max(round(height * 0.24, 1), 6.0), 10.0),
            "small_pt": min(max(round(height * 0.21, 1), 5.5), 8.5),
            "price_pt": min(max(round(height * 0.38, 1), 7.5), 16.0),
            "human_pt": human_pt,
            "qr_mm": qr_mm,
            # A little air between the QR code and the text beside it.
            "qr_column": round(qr_mm + 1.2, 2),
            "linear_height": linear_height,
            # Bars, then the digits under them, then a little air.
            "linear_block": round(linear_height + human_pt * pt * 1.3 + 0.6, 2),
        }

    @api.constrains(*LAYOUT_FIELDS)
    def _check_sheet_fits(self):
        for profile in self.filtered(lambda p: p.media == "sheet"):
            layout = profile._layout()
            width = profile.margin_left_mm + layout["grid_width"] + profile.margin_right_mm
            height = profile.margin_top_mm + layout["grid_height"] + profile.margin_bottom_mm
            if width > layout["page_width"] + 0.01 or height > layout["page_height"] + 0.01:
                raise ValidationError(self.env._(
                    "The labels of %(profile)s need %(width).1f x %(height).1f mm, "
                    "more than a %(sheet)s sheet.",
                    profile=profile.name, width=width, height=height, sheet=profile.sheet_size,
                ))

    # ------------------------------------------------------------------
    # Paperformat
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        profiles = super().create(vals_list)
        profiles._sync_paperformat()
        return profiles

    def write(self, vals):
        result = super().write(vals)
        if LAYOUT_FIELDS & set(vals) or "name" in vals:
            self._sync_paperformat()
        return result

    def unlink(self):
        paperformats = self.paperformat_id
        result = super().unlink()
        paperformats.sudo().unlink()
        return result

    def _sync_paperformat(self):
        """Keep one paperformat per profile, written when the profile changes.

        Printing never writes it: two people printing on different profiles
        each read their own page size.
        """
        Paperformat = self.env["report.paperformat"].sudo()
        for profile in self:
            layout = profile._layout()
            values = {
                "name": self.env._("Labels: %s", profile.name),
                "format": "custom",
                "page_width": layout["paper_width"],
                "page_height": layout["paper_height"],
                "orientation": "Portrait",
                "margin_top": 0,
                "margin_bottom": 0,
                "margin_left": 0,
                "margin_right": 0,
                "header_line": False,
                "header_spacing": 0,
                "disable_shrinking": True,
                # 96 prints mm at size in wkhtmltopdf; get_paperformat swaps
                # in 76 for Paper Muncher.
                "dpi": 96,
            }
            if profile.paperformat_id:
                profile.paperformat_id.sudo().write(values)
            else:
                profile.paperformat_id = Paperformat.create(values)

    # ------------------------------------------------------------------
    # Printing
    # ------------------------------------------------------------------

    def _get_report(self):
        self.ensure_one()
        xmlid = {
            "pdf": "bs_product_label.action_report_label_pdf",
            "html": "bs_product_label.action_report_label_html",
            "zpl": "bs_product_label.action_report_label_zpl",
        }[self.output]
        return self.env.ref(xmlid)

    def _print(self, lines, pricelist=None, test=False):
        """Return the report action printing ``lines`` on this profile.

        ``lines`` are plain dicts (see the print wizard's ``_label_line``), so
        the report can be downloaded again after the wizard is gone.
        """
        self.ensure_one()
        selected_pricelist = self.pricelist_id if pricelist is None else pricelist
        data = {
            "profile_id": self.id,
            "pricelist_id": selected_pricelist.id if selected_pricelist else False,
            "lines": lines,
            "test": test,
        }
        # config=False: labels carry no company header, so the document
        # layout setup that report_action would open first is irrelevant.
        return self._get_report().with_context(bs_label_profile_id=self.id).report_action(
            None, data=data, config=False
        )

    def action_print_test_page(self):
        """A page of outlined sample labels, to line the printer up."""
        self.ensure_one()
        return self._print([], test=True)

    def _expand_lines(self, lines):
        """One entry per label to print, in order."""
        total = sum(max(int(line.get("quantity") or 0), 0) for line in lines)
        if total > MAX_LABELS:
            raise UserError(self.env._(
                "%(count)s labels is more than %(max)s at once. Check the quantities, "
                "or print in several runs.",
                count=total, max=MAX_LABELS,
            ))
        labels = []
        for line in lines:
            labels.extend([line] * max(int(line.get("quantity") or 0), 0))
        return labels

    def _paginate(self, labels):
        """Pages of rows of cells; a cell is a label's values or None."""
        self.ensure_one()
        layout = self._layout()
        per_page, columns = layout["per_page"], layout["columns"]
        pages = []
        for start in range(0, len(labels), per_page):
            chunk = labels[start:start + per_page]
            chunk += [None] * (per_page - len(chunk))
            pages.append([chunk[row:row + columns] for row in range(0, per_page, columns)])
        return pages

    def _prepare_label_values(self, line, pricelist=None):
        """What one label shows, from a label line dict.

        The single place the label's content is decided: the PDF, HTML and
        ZPL outputs and the preview all read these values, so a project adds
        a field to every output by extending this method.
        """
        self.ensure_one()
        product = self.env["product.product"].browse(line["product_id"])
        barcode_value = self._barcode_value(product, line)
        return {
            "code": product.default_code or "" if self.show_code else "",
            "name": product.name or "" if self.show_name else "",
            "variant": (
                product.product_template_attribute_value_ids._get_combination_name()
                if self.show_variant else ""
            ),
            "price": self._format_price(product, pricelist) if self.show_price else "",
            "barcode_value": barcode_value,
            "barcode_type": self._effective_barcode_type(barcode_value),
            "barcode_src": self._barcode_src(barcode_value),
            "extra_text": line.get("extra_text") or "",
            "custom_text": self.custom_text or "",
            "source": line.get("source") or "",
        }

    def _text_lines(self, values):
        """The small lines under the name, in the order they give way when a
        label runs out of room: (text, size key in the layout). A project
        adds a line by extending this list."""
        return [
            (values["code"], "code_pt"),
            (values["variant"], "small_pt"),
            (values["extra_text"], "small_pt"),
            (values["custom_text"], "small_pt"),
        ]

    def _fit_label(self, values):
        """Decide which lines one label has room for.

        A line either prints whole or not at all: a line cut through the
        middle by the barcode looks broken on the shelf. The name takes one
        or two lines by its length; the lines under it follow in order
        until the space is used.
        """
        layout = self._layout()
        mm_per_pt = 0.3528
        is_qr = values["barcode_src"] and values["barcode_type"] == "QR"
        is_linear = values["barcode_src"] and not is_qr
        width = layout["inner_width"] - (layout["qr_column"] if is_qr else 0)
        space = layout["inner_height"]
        space -= layout["price_pt"] * mm_per_pt * 1.25 if values["price"] else 0
        space -= layout["linear_block"] if is_linear else 0
        # Myanmar/Thai combining marks need more vertical room than Latin.
        texts = [values["name"], values["price"]]
        texts += [text for text, _size in self._text_lines(values)]
        line_height = 1.5 if any(_complex_script(text or "") for text in texts) else 1.15
        name_line = layout["name_pt"] * mm_per_pt * line_height
        name_lines = 0
        if values["name"]:
            # A bold character averages about 0.58 of the font size across.
            needed = len(values["name"]) * layout["name_pt"] * mm_per_pt * 0.58
            name_lines = 1 if needed <= width or space < 2 * name_line else 2
        space -= name_lines * name_line
        lines = []
        for text, size in self._text_lines(values):
            if not text:
                continue
            height = layout[size] * mm_per_pt * line_height
            if height > space + 0.05:
                break
            lines.append({"text": text, "size": size})
            space -= height
        values.update(name_lines=name_lines, lines=lines, text_width=round(width, 2), line_height=line_height)
        return values

    def _barcode_value(self, product, line):
        if self.barcode_source == "barcode":
            return product.barcode or ""
        if self.barcode_source == "default_code":
            return product.default_code or ""
        return ""

    def _format_price(self, product, pricelist=None):
        pricelist = self.pricelist_id if pricelist is None else pricelist
        if pricelist:
            currency = pricelist.currency_id
            price = pricelist._get_product_price(product, 1, currency=currency)
        else:
            currency = product.currency_id
            price = product.lst_price
        return currency.format(price)

    def _effective_barcode_type(self, value):
        """Use the same validated symbology in every output."""
        if self.barcode_type == "EAN13" and value and not check_barcode_encoding(value, "EAN13"):
            return "Code128"
        return self.barcode_type

    def _barcode_src(self, value):
        """The barcode as a data URI.

        Embedded rather than linked to /report/barcode: no PDF engine has to
        fetch it back over HTTP, and the preview shows it as is.
        """
        if not value:
            return ""
        layout = self._layout()
        if self.barcode_type == "QR":
            width = height = 300
        else:
            width, height = 600, max(int(600 * layout["linear_height"] / layout["inner_width"]), 60)
        try:
            png = self.env["ir.actions.report"].barcode(
                self._effective_barcode_type(value), value, width=width, height=height, humanreadable=0, quiet=0
            )
        except (ValueError, AttributeError):
            return ""
        return "data:image/png;base64," + base64.b64encode(png).decode()

    @api.model
    def _format_label_text(self, text):
        """Select script fonts explicitly: old WebKit skips webfont fallbacks."""
        pattern = r"[\u1000-\u109f\ua9e0-\ua9ff\uaa60-\uaa7f][\u1000-\u109f\ua9e0-\ua9ff\uaa60-\uaa7f\s]*|[\u0e00-\u0e7f][\u0e00-\u0e7f\s]*"
        parts, start = [], 0
        for match in re.finditer(pattern, text or ""):
            parts.append(escape(text[start:match.start()]))
            script = "Thai" if "\u0e00" <= match[0][0] <= "\u0e7f" else "Myanmar"
            parts.append(Markup('<span style="font-family: %s;">%s</span>') % (
                "BS Label " + script, match[0],
            ))
            start = match.end()
        parts.append(escape((text or "")[start:]))
        return Markup("").join(parts)

    def _sample_line(self):
        """A product to show in previews and test pages."""
        product = self.env["product.product"].search(
            [("barcode", "!=", False), ("default_code", "!=", False)], limit=1
        ) or self.env["product.product"].search([], limit=1)
        return {
            "product_id": product.id,
            "quantity": 1,
            "extra_text": "",
            "source": "",
        }

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_values(self, lines, pricelist=None, test=False, limit=None):
        """Values for the label templates, shared by every output.

        ``limit`` caps the labels expanded, for a preview of the first page.
        """
        self.ensure_one()
        per_page = self._layout()["per_page"]
        if test:
            sample = self._sample_line()
            labels = [sample] * per_page if sample["product_id"] else []
        elif limit is not None:
            labels = []
            for line in lines:
                remaining = max(limit - len(labels), 0)
                quantity = min(max(int(line.get("quantity") or 0), 0), remaining)
                labels.extend([line] * quantity)
                if len(labels) >= limit:
                    break
            labels = labels[:limit]
        else:
            labels = self._expand_lines(lines)
        values = [self._fit_label(self._prepare_label_values(line, pricelist)) for line in labels]
        return {
            "profile": self,
            "font_css": _label_font_css() if any(value["line_height"] > 1.15 for value in values) else "",
            "layout": self._layout(),
            "pages": self._paginate(values),
            "outline": test,
        }

    def _render_preview(self, lines, pricelist=None):
        """The first page, in HTML at real size, for the print dialog."""
        self.ensure_one()
        values = self._render_values(lines, pricelist, limit=self._layout()["per_page"])
        values["outline"] = True
        return self.env["ir.qweb"]._render("bs_product_label.label_pages", values)

    @api.depends(
        *LAYOUT_FIELDS, "show_code", "show_name", "show_variant", "show_price",
        "pricelist_id", "custom_text", "barcode_source", "barcode_type", "offset_x_mm",
        "offset_y_mm",
    )
    def _compute_preview_html(self):
        for profile in self:
            sample = profile._sample_line()
            if not sample["product_id"]:
                profile.preview_html = False
                continue
            sample["quantity"] = profile._layout()["per_page"]
            profile.preview_html = profile._render_preview([sample])

    # ------------------------------------------------------------------
    # ZPL
    # ------------------------------------------------------------------

    def _render_zpl(self, pages):
        """ZPL for the pages: one printer label per row of labels.

        Printers use their built-in font, which covers Latin text only.
        """
        self.ensure_one()
        layout = self._layout()
        dots = int(self.zpl_dpi) / 25.4

        def d(mm):
            return max(int(round(mm * dots)), 0)

        out = []
        for page in pages:
            for row in page:
                out.append("^XA^CI28")
                out.append("^PW%d^LL%d" % (d(layout["page_width"]), d(layout["label_height"] + self.margin_top_mm + self.margin_bottom_mm)))
                for index, label in enumerate(row):
                    if not label:
                        continue
                    visible_text = [label["name"], label.get("price") or ""]
                    visible_text += [line["text"] for line in label.get("lines", [])]
                    if any(_complex_script(text) for text in visible_text):
                        raise UserError(self.env._(
                            "ZPL's built-in font cannot print Myanmar or Thai text. "
                            "Choose a PDF or HTML label profile for these products."
                        ))
                    left = (layout["margin_left"] + layout["offset_x"] + layout["padding"]
                            + index * (layout["label_width"] + layout["gap_x"]))
                    top = layout["margin_top"] + layout["offset_y"] + layout["padding"]
                    out.extend(self._zpl_label(label, layout, left, top, d))
                out.append("^XZ")
        return "\n".join(out) + "\n"

    def _zpl_label(self, label, layout, left, top, d):
        """ZPL commands drawing one label with its top-left corner at (left, top)
        mm, in the same arrangement as the PDF: name, code, variant, extra lines,
        price at the bottom, QR on the right or barcode across the bottom."""
        mm_per_pt = 0.3528
        is_qr = label["barcode_value"] and label["barcode_type"] == "QR"
        is_linear = label["barcode_value"] and not is_qr
        text_width = layout["inner_width"] - (layout["qr_column"] if is_qr else 0)
        bottom = top + layout["inner_height"]

        def encode(text):
            # ^FH decodes UTF-8 bytes inside ^FD without interpreting them as
            # ZPL commands. Encode XML-sensitive bytes too: QWeb's normal
            # escaping then leaves the generated text stream unchanged.
            return "".join(
                chr(byte) if 32 <= byte < 127 and chr(byte) not in "^~_<>&\"'"
                else "_%02X" % byte
                for byte in (text or "").encode("utf-8")
            )

        commands = []
        y = top
        rows = [(label["name"], "name_pt", label.get("name_lines", 1))]
        rows += [(line["text"], line["size"], 1) for line in label.get("lines", [])]
        for text, size, count in rows:
            text = encode(text)
            if not text or not count:
                continue
            height_mm = layout[size] * mm_per_pt
            commands.append("^FO%d,%d^A0N,%d,%d^FB%d,%d,0,L^FH^FD%s^FS" % (
                d(left), d(y), d(height_mm), d(height_mm), d(text_width), count, text,
            ))
            y += height_mm * 1.15 * count
        if is_linear:
            bottom -= layout["linear_block"]
            barcode_value = label["barcode_value"]
            if label["barcode_type"] == "Code128":
                # Zebra uses > for subset/FNC invocation; >0 prints a literal >.
                barcode_value = barcode_value.replace(">", ">0")
            value = encode(barcode_value)
            symbol = "^BEN" if label["barcode_type"] == "EAN13" else "^BCN"
            commands.append("^FO%d,%d^BY2%s,%d,Y,N^FH^FD%s^FS" % (
                d(left), d(bottom + 0.6), symbol, d(layout["linear_height"]), value,
            ))
        price = encode(label.get("price"))
        if price:
            height_mm = layout["price_pt"] * mm_per_pt
            commands.append("^FO%d,%d^A0N,%d,%d^FB%d,1,0,L^FH^FD%s^FS" % (
                d(left), d(bottom - height_mm * 1.1), d(height_mm), d(height_mm), d(text_width), price,
            ))
        if is_qr:
            magnification = max(min(int(d(layout["qr_mm"]) / 30), 10), 1)
            commands.append("^FO%d,%d^BQN,2,%d^FH^FDLA,%s^FS" % (
                d(left + layout["inner_width"] - layout["qr_mm"]), d(top), magnification,
                encode(label["barcode_value"]),
            ))
        return commands
