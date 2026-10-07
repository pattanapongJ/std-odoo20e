# -*- coding: utf-8 -*-
{
    "name": "Product Attribute UI",
    "version": "20.0.1.0.2",
    "summary": "Read, filter, show and group product variants by their attributes",
    "description": """
Two additions to the product variant screens, both display-only.

On the form, the attribute tags are replaced by one row per attribute: the
attribute's own name on the left, its value on the right. Nothing is
configured - the rows follow whatever attributes a variant carries, including
the ones core hides because their line offers a single value.

In the list, a search panel offers every attribute value, grouped under the
attribute it belongs to, so variants can be narrowed down by Colour and Size
the way a catalogue is browsed. A Group By on Attribute Value groups the list
by value across templates.

An attribute marked Column on Variants becomes a column of its own in the
variant list and a Group By under Properties. It is kept as a property of the
variant, so adding one changes no table.
    """,
    "author": "Basic Solution Co., Ltd.",
    "website": "https://www.basic-solution.com",
    "category": "Sales/Sales",
    "depends": [
        "product",
    ],
    "data": [
        "views/product_attribute_views.xml",
        "views/product_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "bs_product_attribute_ui/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "bs_product_attribute_ui/static/tests/**/*",
        ],
    },
    "application": False,
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
