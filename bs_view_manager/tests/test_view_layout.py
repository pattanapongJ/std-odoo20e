from lxml import etree

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user


class TestViewLayout(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'bs_vm_user', groups='base.group_user')
        cls.other = new_test_user(cls.env, 'bs_vm_other', groups='base.group_user')
        cls.action = cls.env.ref('base.action_partner_form')
        cls.Layout = cls.env['bs.view.layout'].with_user(cls.user)
        cls.fields_info = cls.env['res.partner'].fields_get(
            attributes=cls.env['res.partner']._get_view_field_attributes(),
        )

    def _layout(self, columns):
        return self.env['bs.view.layout'].new({'columns': columns})

    def _fields(self, arch):
        return [(node.get('name'), dict(node.attrib)) for node in etree.fromstring(arch).iterchildren('field')]

    def test_apply_reorders_hides_renames_and_sizes(self):
        arch = """<list><field name="name"/><button name="action_x" type="object"/>
                  <field name="email" optional="show"/><field name="phone" optional="hide"/></list>"""
        layout = self._layout([
            {'name': 'phone', 'visible': True, 'label': 'Mobile', 'width': 120},
            {'name': 'name', 'visible': True, 'label': '', 'width': False},
            {'name': 'email', 'visible': False, 'label': '', 'width': False},
        ])
        new_arch, added = layout._bs_apply(arch, self.fields_info)
        root = etree.fromstring(new_arch)

        self.assertFalse(added)
        self.assertEqual([child.tag for child in root], ['field', 'button', 'field', 'field'],
                         "the button keeps its slot")
        fields = self._fields(new_arch)
        self.assertEqual([name for name, _attrs in fields], ['phone', 'name', 'email'])
        self.assertEqual(fields[0][1], {'name': 'phone', 'string': 'Mobile', 'width': '120px'})
        self.assertEqual(fields[2][1].get('column_invisible'), 'True')
        self.assertNotIn('optional', fields[2][1], "the layout replaces the native optional toggle")

    def test_apply_adds_fields_and_keeps_unknown_arch_fields(self):
        arch = '<list><field name="name"/><field name="email"/><field name="city"/></list>'
        layout = self._layout([
            {'name': 'email', 'visible': True},
            {'name': 'ref', 'visible': True},
            {'name': 'comment', 'visible': True},  # html: not addable
            {'name': 'website', 'visible': False},  # hidden and not in arch: skipped
        ])
        new_arch, added = layout._bs_apply(arch, self.fields_info)
        self.assertEqual(added, {'ref'})
        self.assertEqual([name for name, _attrs in self._fields(new_arch)], ['email', 'ref', 'name', 'city'],
                         "fields missing from the layout keep their arch order after the layout ones")

    def test_apply_never_reveals_always_invisible_columns(self):
        arch = '<list><field name="name"/><field name="company_id" column_invisible="True"/></list>'
        layout = self._layout([{'name': 'company_id', 'visible': True}, {'name': 'name', 'visible': True}])
        new_arch, _added = layout._bs_apply(arch, self.fields_info)
        attrs = dict(self._fields(new_arch))
        self.assertEqual(attrs['company_id'].get('column_invisible'), 'True')

    def test_apply_leaves_properties_fields_alone(self):
        """A properties field is many columns on the client; a layout that
        hid it - saved before this was handled - must not hide them all."""
        arch = '<list><field name="name"/><field name="properties"/></list>'
        layout = self._layout([
            {'name': 'properties', 'visible': False},
            {'name': 'name', 'visible': True},
        ])
        new_arch, _added = layout._bs_apply(arch, self.fields_info)
        attrs = dict(self._fields(new_arch))
        self.assertNotIn('column_invisible', attrs['properties'])

    def test_save_validates_columns(self):
        columns = self.Layout.bs_get_panel_data('res.partner', self.action.id)['columns']
        self.assertTrue(columns)
        payload = [
            {'name': 'not_a_field', 'visible': True},
            {'name': 'ref', 'visible': True, 'label': '  ' + 'x' * 300, 'width': 99999},
            {'name': 'ref', 'visible': False},  # duplicate, ignored
            {'name': columns[0]['name'], 'visible': False, 'width': 150},
        ]
        self.Layout.bs_save_layout('res.partner', self.action.id, False, payload)
        layout = self.Layout._bs_find('res.partner', self.action.id)
        self.assertEqual(layout.user_id, self.user)
        self.assertEqual(layout.columns, [
            {'name': 'ref', 'visible': True, 'label': 'x' * 100, 'width': False, 'aggregate': ''},
            {'name': columns[0]['name'], 'visible': False, 'label': '', 'width': 150, 'aggregate': ''},
        ])

        # saving again updates the same record
        self.Layout.bs_save_layout('res.partner', self.action.id, False, payload[:2])
        self.assertEqual(self.env['bs.view.layout'].search_count([('user_id', '=', self.user.id)]), 1)

    def test_save_rejects_foreign_action_and_unknown_model(self):
        with self.assertRaises(UserError):
            self.Layout.bs_save_layout('res.users', self.action.id, False, [])
        with self.assertRaises(UserError):
            self.Layout.bs_save_layout('no.such.model', self.action.id, False, [])

    def test_layouts_are_private(self):
        self.Layout.bs_save_layout('res.partner', self.action.id, False, [{'name': 'ref', 'visible': True}])
        layout = self.Layout._bs_find('res.partner', self.action.id)
        Other = self.env['bs.view.layout'].with_user(self.other)
        self.assertFalse(Other._bs_find('res.partner', self.action.id))
        self.assertFalse(Other.search([('id', '=', layout.id)]))
        with self.assertRaises(AccessError):
            layout.with_user(self.other).columns = []
        with self.assertRaises(AccessError):
            layout.with_user(self.other).unlink()

    def test_users_cannot_share_through_write(self):
        self.Layout.bs_save_layout('res.partner', self.action.id, False, [{'name': 'ref', 'visible': True}])
        layout = self.Layout._bs_find('res.partner', self.action.id)
        for vals in ({'user_id': False}, {'group_ids': [(6, 0, [])]}, {'editable': 'on'}):
            with self.assertRaises(AccessError):
                layout.write(vals)
        # saving again still works: the lookup keys are not rewritten
        self.Layout.bs_save_layout('res.partner', self.action.id, False, [{'name': 'email', 'visible': True}])
        self.assertEqual(layout.columns[0]['name'], 'email')

    def test_columns_are_sanitized_on_write(self):
        self.Layout.bs_save_layout('res.partner', self.action.id, False, [])
        layout = self.Layout._bs_find('res.partner', self.action.id)
        layout.write({'columns': ['x', {'name': 3}, {'name': 'ref', 'width': True, 'aggregate': 'median'}, None]})
        self.assertEqual(layout.columns, [{'name': 'ref', 'visible': False, 'label': '', 'width': False, 'aggregate': ''}])
        layout.write({'columns': 'not a list'})
        self.assertFalse(layout.columns, "an empty Json list reads back as False")

    def test_get_views_applies_the_layout(self):
        Partner = self.env['res.partner'].with_user(self.user)
        views = [[False, 'list'], [False, 'search']]
        options = {'action_id': self.action.id}
        before = Partner.get_views(views, options)
        in_list = {name for name, _attrs in self._fields(before['views']['list']['arch'])}
        extra = next(name for name, info in self.fields_info.items()
                     if info['type'] == 'char' and name not in in_list)

        self.Layout.bs_save_layout('res.partner', self.action.id, False, [{'name': extra, 'visible': True, 'label': 'Code'}])
        after = Partner.get_views(views, options)
        self.assertIn(extra, after['models']['res.partner']['fields'])
        self.assertEqual(dict(self._fields(after['views']['list']['arch']))[extra].get('string'), 'Code')

        # other users and calls without an action are untouched
        other = self.env['res.partner'].with_user(self.other).get_views(views, options)
        self.assertEqual(other['views']['list']['arch'], before['views']['list']['arch'])
        self.assertEqual(Partner.get_views(views, {})['views']['list']['arch'], before['views']['list']['arch'])

        self.Layout.bs_reset_layout('res.partner', self.action.id)
        self.assertEqual(Partner.get_views(views, options)['views']['list']['arch'], before['views']['list']['arch'])


class TestTeamLayout(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(cls.env, 'bs_vm_admin', groups='base.group_user,base.group_system')
        cls.user = new_test_user(cls.env, 'bs_vm_member', groups='base.group_user')
        cls.action = cls.env.ref('base.action_partner_form')
        cls.fields_info = cls.env['res.partner'].fields_get(
            attributes=cls.env['res.partner']._get_view_field_attributes(),
        )

    def _share(self, columns, groups, **options):
        self.env['bs.view.layout'].with_user(self.admin).bs_share_layout(
            'res.partner', self.action.id, False, columns, {'group_ids': groups.ids, **options},
        )

    def _source(self, user):
        return self.env['bs.view.layout'].with_user(user).bs_get_panel_data('res.partner', self.action.id)['source']

    def test_team_layout_applies_until_the_user_saves_their_own(self):
        self._share([{'name': 'ref', 'visible': True, 'label': 'Team code'}], self.env.ref('base.group_user'))
        Layout = self.env['bs.view.layout'].with_user(self.user)
        self.assertEqual(self._source(self.user), 'team')
        self.assertEqual(Layout._bs_resolve('res.partner', self.action.id).columns[0]['label'], 'Team code')

        Layout.bs_save_layout('res.partner', self.action.id, False, [{'name': 'ref', 'visible': True, 'label': 'Mine'}])
        self.assertEqual(self._source(self.user), 'personal')
        self.assertEqual(Layout._bs_resolve('res.partner', self.action.id).columns[0]['label'], 'Mine')

        Layout.bs_reset_layout('res.partner', self.action.id)
        self.assertEqual(self._source(self.user), 'team', "resetting falls back to the team layout")

    def test_team_layout_is_limited_to_its_groups(self):
        self._share([{'name': 'ref', 'visible': True}], self.env.ref('base.group_system'))
        self.assertEqual(self._source(self.user), 'default')
        self.assertEqual(self._source(self.admin), 'team')

    def test_share_ignores_malformed_group_ids(self):
        self._share([{'name': 'ref', 'visible': True}], self.env['res.groups'], group_ids=['x', None])
        self.assertEqual(self._source(self.user), 'team')

    def test_team_layout_without_groups_is_for_everyone(self):
        self._share([{'name': 'ref', 'visible': True}], self.env['res.groups'])
        self.assertEqual(self._source(self.user), 'team')

    def test_only_administrators_manage_team_layouts(self):
        Layout = self.env['bs.view.layout'].with_user(self.user)
        with self.assertRaises(AccessError):
            Layout.bs_share_layout('res.partner', self.action.id, False, [], {})
        with self.assertRaises(AccessError):
            Layout.bs_unshare_layout('res.partner', self.action.id)

        self._share([{'name': 'ref', 'visible': True}], self.env['res.groups'])
        team = Layout._bs_find_team('res.partner', self.action.id)
        with self.assertRaises(AccessError):
            team.columns = []
        with self.assertRaises(AccessError):
            team.unlink()

        self.env['bs.view.layout'].with_user(self.admin).bs_unshare_layout('res.partner', self.action.id)
        self.assertEqual(self._source(self.user), 'default')

    def test_aggregates_and_filter_row(self):
        arch = '<list><field name="name"/><field name="color" sum="Total"/><field name="email"/></list>'
        layout = self.env['bs.view.layout'].new({
            'show_filter_row': True,
            'columns': [
                {'name': 'color', 'visible': True, 'aggregate': 'avg'},
                {'name': 'email', 'visible': True, 'aggregate': 'sum'},  # not numeric: ignored
            ],
        })
        new_arch, _added = layout._bs_apply(arch, self.fields_info)
        root = etree.fromstring(new_arch)
        color = root.find("field[@name='color']")
        self.assertEqual(root.get('bs_filter_row'), '1')
        self.assertEqual(root.get('bs_layout'), '1')
        self.assertIsNone(color.get('sum'))
        self.assertTrue(color.get('avg'))
        self.assertIsNone(root.find("field[@name='email']").get('sum'))

        layout.columns = [{'name': 'color', 'visible': True, 'aggregate': ''}]
        layout.show_filter_row = False
        new_arch, _added = layout._bs_apply(arch, self.fields_info)
        root = etree.fromstring(new_arch)
        self.assertFalse({'sum', 'avg', 'min', 'max'} & set(root.find("field[@name='color']").attrib))
        self.assertIsNone(root.get('bs_filter_row'))

    def test_save_drops_invalid_aggregates(self):
        Layout = self.env['bs.view.layout'].with_user(self.user)
        Layout.bs_save_layout('res.partner', self.action.id, False, [
            {'name': 'color', 'visible': True, 'aggregate': 'sum'},
            {'name': 'email', 'visible': True, 'aggregate': 'sum'},
            {'name': 'ref', 'visible': True, 'aggregate': 'median'},
        ], {'show_filter_row': True})
        layout = Layout._bs_find('res.partner', self.action.id)
        self.assertEqual([col['aggregate'] for col in layout.columns], ['sum', '', ''])
        self.assertTrue(layout.show_filter_row)

    def test_row_numbers_flag(self):
        Layout = self.env['bs.view.layout'].with_user(self.user)
        Layout.bs_save_layout('res.partner', self.action.id, False, [], {'show_row_numbers': True})
        layout = Layout._bs_find('res.partner', self.action.id)
        new_arch, _added = layout._bs_apply('<list><field name="name"/></list>', self.fields_info)
        self.assertEqual(etree.fromstring(new_arch).get('bs_row_numbers'), '1')

    def _list_arch(self, user):
        views = self.env['res.partner'].with_user(user).get_views([[False, 'list']], {'action_id': self.action.id})
        return etree.fromstring(views['views']['list']['arch'])

    def test_inline_edit_is_a_list_wide_policy(self):
        Admin = self.env['bs.view.layout'].with_user(self.admin)
        with self.assertRaises(AccessError):
            self.env['bs.view.layout'].with_user(self.user).bs_set_editable('res.partner', self.action.id, 'on')
        self.assertFalse(Admin.bs_get_panel_data('res.partner', self.action.id)['inline_edit'])

        Admin.bs_set_editable('res.partner', self.action.id, 'on')
        root = self._list_arch(self.user)
        self.assertEqual(root.get('editable'), 'bottom')
        self.assertEqual(root.get('bs_inline_edit'), '1', "New keeps opening the form")
        self.assertTrue(Admin.bs_get_panel_data('res.partner', self.action.id)['inline_edit'])
        self.assertEqual(self._source(self.user), 'default', "a policy alone is not a team layout")

        # it applies over personal layouts, and over team layouts shared with other groups
        self.env['bs.view.layout'].with_user(self.user).bs_save_layout(
            'res.partner', self.action.id, False, [{'name': 'email', 'visible': True}], {'editable': 'off'},
        )
        self._share([{'name': 'ref', 'visible': True}], self.env.ref('base.group_system'))
        self.assertEqual(self._list_arch(self.user).get('editable'), 'bottom')

        # removing the team columns keeps the policy
        Admin.bs_unshare_layout('res.partner', self.action.id)
        self.assertEqual(self._list_arch(self.user).get('editable'), 'bottom')

        Admin.bs_set_editable('res.partner', self.action.id, 'off')
        self.assertIsNone(self._list_arch(self.user).get('editable'))
        self.assertFalse(Admin.bs_get_panel_data('res.partner', self.action.id)['inline_edit'])

    def test_inline_edit_keeps_a_natively_editable_list(self):
        layout = self.env['bs.view.layout'].new({})
        new_arch, _added = layout._bs_apply('<list editable="top"><field name="name"/></list>', self.fields_info, 'on')
        root = etree.fromstring(new_arch)
        self.assertEqual(root.get('editable'), 'top')
        self.assertIsNone(root.get('bs_inline_edit'), "the view's own New behavior is kept")
