# -*- coding: utf-8 -*-
{
    "name": "Product Attribute Report",
    "version": "20.0.1.0.0",
    "summary": "Stock on hand and sales quantity by attribute value",
    "description": """
A pivot and graph of product variants by attribute value - Colour, Size,
Thickness - measuring stock on hand and quantity sold.

Pick one attribute in the side panel and its values become the rows. The
report holds one row per variant and attribute, so a variant counts once under
each of its attributes: the totals are only meaningful within one attribute,
which is why the panel selects exactly one.
    """,
    "author": "Basic Solution Co., Ltd.",
    "website": "https://www.basic-solution.com",
    "category": "Inventory/Inventory",
    "depends": [
        "bs_product_attribute_ui",
        "sale_stock",
    ],
    "data": [
        "security/ir.access.csv",
        "report/product_attribute_report_views.xml",
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
