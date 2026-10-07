# -*- coding: utf-8 -*-
{
    "name": "Product Code Generator",
    "version": "20.0.1.1.0",
    "summary": "Build a product's internal reference from its fields",
    "description": """
Builds a product's internal reference from the fields it already has.

A code rule says which products it covers, with a domain, then lists the parts
that make up their reference in order. Each part reads a product field along a
path that may follow relations, contributes fixed text, or hands out a running
number, and carries its own prefix, suffix and formatting.

This module stores no fields of its own on products or attributes: it works
with whatever a database already has. Site-specific fields belong in a module of
their own.
    """,
    "author": "Basic Solution Co., Ltd.",
    "website": "https://www.basic-solution.com",
    "category": "Product",
    "depends": [
        "product",
        # For the Products section of the Inventory settings page.
        "stock",
    ],
    "demo": [
        "demo/product_code_demo.xml",
    ],
    "data": [
        "security/ir.access.csv",
        "views/product_code_rule_views.xml",
        "views/res_config_settings_views.xml",
        "views/product_product_views.xml",
        "views/product_code_history_views.xml",
        "wizard/product_code_preview_views.xml",
    ],
    "assets": {
        "web.assets_unit_tests": [
            "bs_generate_product_code/static/tests/product_code_field_selector.test.js",
        ],
        "web.assets_backend": [
            "bs_generate_product_code/static/src/fields/product_code_field_selector.js",
        ],
    },
    "application": False,
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
