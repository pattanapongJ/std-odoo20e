# -*- coding: utf-8 -*-
{
    "name": "Product Labels - Inventory",
    "version": "20.0.1.0.0",
    "summary": "Print product labels from lots and transfers, with the lot on the label",
    "description": """
Adds lots/serial numbers and transfers as places to print labels from, the lot
as label content and barcode, and the Label Profiles menu under Inventory.
    """,
    "author": "Basic Solution Co., Ltd.",
    "website": "https://www.basic-solution.com",
    "category": "Inventory/Inventory",
    "depends": [
        "bs_product_label",
        "stock",
    ],
    "data": [
        "security/ir.access.csv",
        "views/bs_label_profile_views.xml",
        "wizard/bs_label_print_wizard_views.xml",
        "data/bs_label_actions.xml",
    ],
    "application": False,
    "installable": True,
    "auto_install": True,
    "license": "LGPL-3",
}
