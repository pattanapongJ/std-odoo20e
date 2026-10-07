from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        info = super().session_info()
        if self.env.user._is_internal():
            info['bs_chatter_position'] = self.env.user.bs_chatter_position
        return info
