# -*- coding: utf-8 -*-
{
    "name": "Product Labels",
    "version": "20.0.1.0.0",
    "summary": "Print product labels of any size on roll or sheet printers, as PDF, HTML or ZPL",
    "description": """
Label profiles say what paper a label goes on - a thermal roll with one or more
labels across, or a sticker sheet - and what the label shows: reference, name,
variant, price from a pricelist, a QR code or barcode, and free text.

Print from products and variants (Actions > Print Labels), with a quantity and
extra text per line and a live preview. Output is a PDF through whichever PDF
engine the database uses, an HTML page for the browser's print dialog, or ZPL
for Zebra printers.

Built to be extended: projects add fields to the label, new places to print
from, or a design of their own without touching this module.
    """,
    "author": "Basic Solution Co., Ltd.",
    "website": "https://www.basic-solution.com",
    "category": "Sales/Sales",
    "depends": [
        "product",
    ],
    "data": [
        "security/ir.access.csv",
        "report/bs_label_reports.xml",
        "report/bs_label_templates.xml",
        "views/bs_label_profile_views.xml",
        "wizard/bs_label_print_wizard_views.xml",
        "data/bs_label_actions.xml",
        "data/bs_label_profile_data.xml",
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
