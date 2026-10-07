# -*- coding: utf-8 -*-

from odoo import fields, models

PARAM_AUTOGENERATE = "bs_generate_product_code.autogenerate"
PARAM_FREEZE_USED = "bs_generate_product_code.freeze_used"


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    product_code_autogenerate = fields.Boolean(
        string="Generate Internal References",
        config_parameter=PARAM_AUTOGENERATE,
        help="Build a product's internal reference from its code rules when "
        "it is created. Products no rule matches are never touched.",
    )
    product_code_freeze_used = fields.Boolean(
        string="Freeze References Once Used",
        config_parameter=PARAM_FREEZE_USED,
        help="Stop rebuilding a product's reference once a stock move, order "
        "or invoice line uses it. A rule can override this.",
    )
