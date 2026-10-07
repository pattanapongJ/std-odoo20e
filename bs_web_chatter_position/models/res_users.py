from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    bs_chatter_position = fields.Selection([
        ('auto', 'Automatic'),
        ('bottom', 'Below the form'),
        ('side', 'Beside the form'),
    ], string='Chatter Position', default='auto', required=True, user_writeable=True)
