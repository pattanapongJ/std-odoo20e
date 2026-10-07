# Product Labels (`bs_product_label`) - Odoo 20

Generic label printing: any label size on roll or sheet printers, output as
PDF, HTML or ZPL, with a live preview. It is the company standard; projects
extend it rather than copy it. It replaces the DK-only `bs_product_label_dk` and
`bs_lot_label_dk` of 17.0.

Depends on `product` only. `bs_product_label_stock` (auto-installed with
Inventory) adds lots, transfers and the Label Profiles menu.

## Use

1. **Inventory > Configuration > Products > Label Profiles.** Pick a preset
   (roll 50 x 30, roll 2-up 101.6 mm, A4 3 x 8) or copy one. Set the label size,
   columns, gaps and margins, then what the label shows. Only product and stock
   managers can edit profiles.
2. **Print Test Page** prints outlined sample labels. Set the printer driver's
   paper to **Printer Paper Size** and print at actual size. Use **Shift Right /
   Shift Down** if the printer prints off target.
3. **Inventory > Products > Print Labels** opens the dialog empty, to add
   products by hand (shelf labels, a price change). **Actions > Custom Labels**
   on products, variants, lots or transfers opens it with the selection. Pick the profile and pricelist, adjust quantities and extra text per
   line, check the preview, and print. The last profile used is remembered per
   user.

## Label layout

The name comes first and heaviest (one or two lines by its length). Then come the
code, variant, lot, extra text and custom text, and finally the price, large at
the bottom left. A QR code sits on the right, as tall as the label. A linear
barcode spans the bottom, with its digits under it for when a scanner fails.
Every box is positioned in mm. `_fit_label` decides per label which small lines
fit: a line prints whole or not at all, so a small label drops notes rather than
printing one cut in half. Sizes scale with the label height (`_content_layout`).

## Design

- **One model, `bs.label.profile`.** It holds the paper (roll/sheet, size,
  columns/rows, gaps, margins, shift), the content (reference, name, variant,
  price + pricelist, custom text, barcode source and type) and the output
  (PDF / HTML / ZPL, ZPL dpi).
- **Output.** There are three `ir.actions.report` records on the same values:
  `qweb-pdf` and `qweb-html` render `bs_product_label.label_document`, and
  `qweb-text` renders ZPL, built in Python (`_render_zpl`). The PDF goes through
  whichever engine the database uses (wkhtmltopdf or Paper Muncher). The
  templates use tables and mm/pt only, and both engines were checked to place
  labels at size.
- **Page size without writes.** Each profile owns a `report.paperformat`, written
  only when the profile changes. `ir.actions.report.get_paperformat` returns it
  when the print context carries `bs_label_profile_id`. The engines read dpi in
  opposite ways (wkhtmltopdf zooms by 96/dpi, Paper Muncher scales by 76/dpi), so
  an unsaved copy with the engine's dpi is returned. Printing writes nothing,
  which also fixes the 17.0 race where two users printing different sizes
  rewrote one shared paperformat.
- **Whole millimetres.** `report.paperformat.page_width/height` are integers, so
  the page is rounded up (101.6 becomes 102 mm). Labels are placed exactly, with
  under 1 mm spare at the right or bottom edge.
- **Data, not records.** The print sends plain line dicts in `data`, as core's
  label wizard does. A download still works after the dialog is gone.
- **Barcodes are data URIs**, made with `ir.actions.report.barcode()`. No engine
  fetches `/report/barcode` over HTTP, and the preview shows them as they are. An
  invalid EAN-13 is turned into Code 128 by Odoo.
- **Preview.** A computed, non-stored `Html` renders the first page with the same
  template, drawn by the browser. Fonts can differ slightly from the PDF engine's,
  so the test page is the check on paper.
- **Fonts.** None are shipped. Labels use the report's default font; add a font in
  a project module when a client needs one.

## Extending (per project, in a module of its own)

| Need | Where |
|---|---|
| A line on the label | `bs.label.profile._prepare_label_values` (super + key) and `_text_lines` (insert `(text, size)` where it belongs in the give-way order), plus a `show_x` boolean on the profile if it is optional. `bs_product_label_stock` does this for the lot. Fitting, PDF and ZPL follow. |
| A block of its own | An xpath into `bs_product_label.label_body` at `div[@name='header'|'main'|'extra'|'price'|'barcode']`. |
| A new place to print from | `bs.label.print.wizard._lines_from_<model_with_underscores>(records)` returning line dicts, plus an `ir.actions.server` bound to the model (`group_ids` = `base.group_user`). |
| Extra data per line | `bs.label.print.wizard.line._label_line` (super + key). |
| A different design | A new QWeb template for `label_body`. Keep the generic one. |
| ZPL content | `bs.label.profile._zpl_label`. |

## Environment notes

- Barcodes need reportlab's PNG backend. Ubuntu's `python3-reportlab` has it; a
  pip/uv venv needs `rl-renderPM`.
- ZPL uses the printer's built-in font, so it prints Latin text only. Use PDF for
  Myanmar or Thai names.

## Verification - 2026-09-29

Scratch DB `odoo20_pcode` (Odoo 20.0+e, demo data):

- Install: passed (`bs_product_label_stock` auto-installs).
- Tests: 30 in `bs_product_label` and 9 in `bs_product_label_stock`, 0
  failures. They cover layout, paperformat ownership, no writes on print, the
  Paper Muncher dpi swap, price by pricelist, EAN fallback, the label limit,
  HTML/ZPL/PDF output and PDF page size, the dialog, the remembered profile,
  ACLs, transfer quantities (units, kg, lots) and the lot on the label.
- PDF with wkhtmltopdf: roll 2-up gives 3 pages of 102 x 30 mm for 6 labels, and
  the A4 sheet places 3 across. With Paper Muncher the same layout came out at
  101.9 x 29.9 mm.
- Browser: in the profile form, the preview and test page (`Labels.pdf`) work.
  Products > Actions > Custom Labels opens the dialog with 2 lines; the counts
  follow the quantity, Print downloads `Labels.pdf` and closes the dialog. Transfer
  > Custom Labels works too. No console errors.
