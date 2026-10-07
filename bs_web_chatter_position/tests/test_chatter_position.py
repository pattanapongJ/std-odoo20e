from odoo.tests import HttpCase, tagged
from odoo.addons.mail.tests.common import mail_new_test_user


@tagged('post_install', '-at_install')
class TestChatterPosition(HttpCase):
    def test_user_sets_own_position(self):
        user = mail_new_test_user(self.env, login='chatter_pos', groups='base.group_user')
        self.assertEqual(user.bs_chatter_position, 'auto')
        user.with_user(user).write({'bs_chatter_position': 'bottom'})
        self.assertEqual(user.bs_chatter_position, 'bottom')

    def test_session_info(self):
        mail_new_test_user(self.env, login='chatter_pos2', password='chatter_pos2',
                           groups='base.group_user').bs_chatter_position = 'side'
        self.authenticate('chatter_pos2', 'chatter_pos2')
        info = self.make_jsonrpc_request('/web/session/get_session_info')
        self.assertEqual(info['bs_chatter_position'], 'side')

    def test_preferences_view(self):
        view = self.env.ref('base.view_users_form_simple_modif')
        arch = self.env['res.users'].get_views([(view.id, 'form')])['views']['form']['arch']
        self.assertIn('bs_chatter_position', arch)

    def test_side_on_large_screen(self):
        # 1366px is below Odoo's XXL breakpoint: standard puts the chatter below.
        self.env.ref('base.user_admin').bs_chatter_position = 'side'
        partner = self.env['res.partner'].create({'name': 'Chatter side'})
        self.start_tour(f'/odoo/action-base.action_partner_form/{partner.id}',
                        'bs_chatter_position_side', login='admin')


@tagged('post_install', '-at_install')
class TestChatterPositionWide(HttpCase):
    browser_size = '1920x1080'

    def test_bottom_on_wide_screen(self):
        # 1920px is XXL: standard puts the chatter beside.
        self.env.ref('base.user_admin').bs_chatter_position = 'bottom'
        partner = self.env['res.partner'].create({'name': 'Chatter bottom'})
        self.start_tour(f'/odoo/action-base.action_partner_form/{partner.id}',
                        'bs_chatter_position_bottom', login='admin')
