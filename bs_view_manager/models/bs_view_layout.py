from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

# Field types a user may add as a new column. Relational lists (x2many) and
# heavy types (binary, html, properties) are left out on purpose.
ADDABLE_FIELD_TYPES = {
    'boolean', 'char', 'date', 'datetime', 'float', 'integer',
    'many2one', 'monetary', 'selection', 'text',
}
AGGREGATABLE_FIELD_TYPES = {'integer', 'float', 'monetary'}
# A properties field unfolds into one column per property on the client. The
# layout cannot hold those, and hiding the field would hide them all, so it is
# left out of layouts; the panel switches its properties natively instead.
UNMANAGED_FIELD_TYPES = {'properties'}
AGGREGATES = ('sum', 'avg', 'min', 'max')
MAX_COLUMNS = 200
MAX_LABEL_LENGTH = 100
MIN_WIDTH, MAX_WIDTH = 30, 2000
TRUE_VALUES = {'1', 'True', 'true'}
FILTER_ROW_ATTR = 'bs_filter_row'
ROW_NUMBERS_ATTR = 'bs_row_numbers'
# marks a list whose arch this module changed; the client aligns grouped totals on it
LAYOUT_ATTR = 'bs_layout'
EDITABLE_MODES = ('on', 'off')
# set when this module turned inline editing on: New keeps opening the form
INLINE_EDIT_ATTR = 'bs_inline_edit'
# what only administrators may change: who a layout belongs to, whom it is
# shared with, and the list-wide inline editing policy
PROTECTED_FIELDS = {'user_id', 'group_ids', 'editable', 'action_id', 'res_model'}


class BsViewLayout(models.Model):
    _name = 'bs.view.layout'
    _description = 'List View Layout'

    # set: personal layout; empty: team layout shared with group_ids (all internal users if none)
    user_id = fields.Many2one(
        'res.users', default=lambda self: self.env.user, ondelete='cascade', index=True,
    )
    group_ids = fields.Many2many('res.groups', string="Shared With")
    action_id = fields.Many2one('ir.actions.act_window', required=True, ondelete='cascade')
    res_model = fields.Char(required=True)
    # [{'name', 'visible', 'label', 'width', 'aggregate'}], in display order
    columns = fields.Json(default=list)
    show_filter_row = fields.Boolean()
    show_row_numbers = fields.Boolean()
    # inline editing policy of the whole list, for every user whatever the groups;
    # kept on the team layout record, set by administrators
    editable = fields.Selection([('on', "On"), ('off', "Off")], string="Inline Editing")

    _personal_uniq = models.UniqueIndex('(user_id, action_id, res_model) WHERE user_id IS NOT NULL')
    _team_uniq = models.UniqueIndex('(action_id, res_model) WHERE user_id IS NULL')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'columns' in vals:
                vals['columns'] = self._bs_sanitize_columns(vals['columns'])
        return super().create(vals_list)

    def write(self, vals):
        # access rows check the records before the write only: without this, a user
        # could empty user_id and turn their own layout into everyone's team layout
        if PROTECTED_FIELDS & vals.keys() and not self.env.is_superuser() and not self._bs_can_share():
            raise AccessError(self.env._("Only administrators can share layouts or change their owner."))
        if 'columns' in vals:
            vals = {**vals, 'columns': self._bs_sanitize_columns(vals['columns'])}
        return super().write(vals)

    # ------------------------------------------------------------
    # RPC entry points
    # ------------------------------------------------------------

    @api.model
    def bs_get_panel_data(self, res_model, action_id, view_id=False):
        """Return the columns panel content for the current user."""
        Model = self._bs_get_model(res_model)
        fields_info = Model.fields_get(attributes=['string', 'type'])
        arch_columns = self._bs_arch_columns(Model, view_id, fields_info)
        layout = self._bs_resolve(res_model, action_id)

        by_name = {col['name']: col for col in arch_columns}
        columns = []
        for saved in layout.columns or []:
            base = by_name.pop(saved['name'], None)
            info = fields_info.get(saved['name'])
            if info and info['type'] in UNMANAGED_FIELD_TYPES:
                continue
            if base is None and not self._bs_is_addable(info):
                continue
            columns.append({
                'name': saved['name'],
                'type': info['type'],
                'default_label': (base or {}).get('default_label') or info['string'],
                'label': saved.get('label') or '',
                'visible': saved.get('visible', True),
                'width': saved.get('width') or False,
                'aggregate': saved.get('aggregate', (base or {}).get('aggregate', '')),
                'in_arch': base is not None,
            })
        # arch columns the layout does not know yet keep their arch order
        columns += list(by_name.values())

        shown = {col['name'] for col in columns}
        addable = sorted(
            (
                {'name': name, 'label': info['string'], 'type': info['type']}
                for name, info in fields_info.items()
                if name not in shown and self._bs_is_addable(info)
            ),
            key=lambda field: field['label'].lower(),
        )
        can_share = self._bs_can_share()
        team = self._bs_find_team(res_model, action_id)
        return {
            'columns': columns,
            'addable': addable,
            'source': 'personal' if layout.user_id else 'team' if layout.columns else 'default',
            'show_filter_row': layout.show_filter_row,
            'show_row_numbers': layout.show_row_numbers,
            'team_applies': bool(team.columns),
            'can_share': can_share,
            'team_group_ids': team.group_ids.ids if can_share else [],
            'inline_edit': self._bs_get_inline_edit(Model, view_id, res_model, action_id) if can_share else False,
        }

    @api.model
    def bs_save_layout(self, res_model, action_id, view_id, columns, options=None):
        """Store the current user's own layout.

        :param dict options: ``show_filter_row`` and ``show_row_numbers`` flags
        """
        vals = self._bs_prepare_vals(res_model, action_id, view_id, columns, options)
        layout = self._bs_find(res_model, action_id)
        # two saves racing on a first layout hit the unique index and the second
        # one fails; the panel disables Save while saving, so this is left as is
        if layout:
            # the layout was found by action and model: do not rewrite them
            layout.write({key: value for key, value in vals.items() if key not in PROTECTED_FIELDS})
        else:
            self.create(vals)
        return True

    @api.model
    def bs_share_layout(self, res_model, action_id, view_id, columns, options=None):
        """Store the team layout of this list; administrators only.

        :param dict options: the ``bs_save_layout`` flags, plus ``group_ids``
        """
        self._bs_check_can_share()
        options = options if isinstance(options, dict) else {}
        vals = self._bs_prepare_vals(res_model, action_id, view_id, columns, options)
        group_ids = options.get('group_ids')
        group_ids = [gid for gid in group_ids if isinstance(gid, int)] if isinstance(group_ids, list) else []
        groups = self.env['res.groups'].browse(group_ids).exists()
        vals.update(user_id=False, group_ids=[(6, 0, groups.ids)])
        team = self._bs_find_team(res_model, action_id)
        if team:
            team.write(vals)
        else:
            self.create(vals)
        return True

    @api.model
    def bs_unshare_layout(self, res_model, action_id):
        """Drop the team columns; the inline editing policy, if any, stays."""
        self._bs_check_can_share()
        team = self._bs_find_team(res_model, action_id)
        if team.editable:
            team.write({'columns': [], 'group_ids': [(5, 0, 0)], 'show_filter_row': False, 'show_row_numbers': False})
        else:
            team.unlink()
        return True

    @api.model
    def bs_set_editable(self, res_model, action_id, editable):
        """Turn inline editing of the existing rows ``on`` or ``off`` for every
        user of this list; empty goes back to the view's own behavior."""
        self._bs_check_can_share()
        self._bs_prepare_vals(res_model, action_id, False, [], {})  # validates model and action
        editable = editable if editable in EDITABLE_MODES else False
        team = self._bs_find_team(res_model, action_id)
        if team and not editable and not team.columns:
            # the record only held the policy
            team.unlink()
        elif team:
            team.editable = editable
        elif editable:
            self.create({
                'user_id': False, 'action_id': action_id, 'res_model': res_model,
                'columns': [], 'editable': editable,
            })
        return True

    @api.model
    def bs_reset_layout(self, res_model, action_id):
        """Drop the user's own layout: the team layout, if any, applies again."""
        self._bs_find(res_model, action_id).unlink()
        return True

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    @api.model
    def _bs_find(self, res_model, action_id):
        return self.search([
            ('user_id', '=', self.env.uid),
            ('action_id', '=', action_id),
            ('res_model', '=', res_model),
        ], limit=1)

    @api.model
    def _bs_find_team(self, res_model, action_id):
        # access rows limit team layouts to the ones shared with the user's groups
        return self.search([
            ('user_id', '=', False),
            ('action_id', '=', action_id),
            ('res_model', '=', res_model),
        ], limit=1)

    @api.model
    def _bs_resolve(self, res_model, action_id):
        """The layout applied for the current user: their own, else the team one."""
        return self._bs_find(res_model, action_id) or self._bs_find_team(res_model, action_id)

    @api.model
    def _bs_lookup(self, res_model, action_id):
        """Everything get_views needs, in one query: the layout applied for the
        current user and the list's inline editing policy.

        Read as superuser, so the team layout's visibility is checked here: it
        mirrors the access rows (shared with one of the user's groups, or with
        everyone; administrators see them all).

        :return: (layout or empty recordset, editable policy or '')
        """
        layouts = self.sudo().search([
            ('action_id', '=', action_id),
            ('res_model', '=', res_model),
            '|', ('user_id', '=', self.env.uid), ('user_id', '=', False),
        ])
        personal = layouts.filtered('user_id')[:1]
        team = (layouts - personal)[:1]
        editable = team.editable or ''
        if personal:
            return personal, editable
        if team and (
            not team.group_ids
            or team.group_ids & self.env.user.all_group_ids
            or self._bs_can_share()
        ):
            return team, editable
        return self.browse(), editable

    @api.model
    def _bs_get_editable(self, res_model, action_id):
        # a list-wide policy: read it whatever the groups the team layout is shared with
        return self.sudo()._bs_find_team(res_model, action_id).editable or ''

    @api.model
    def _bs_get_inline_edit(self, Model, view_id, res_model, action_id):
        """Whether the list is edited inline: the policy, else the view itself."""
        editable = self._bs_get_editable(res_model, action_id)
        if editable:
            return editable == 'on'
        return bool(etree.fromstring(Model.get_view(view_id or None, 'list')['arch']).get('editable'))

    @api.model
    def _bs_can_share(self):
        return self.env.user.has_group('base.group_system')

    @api.model
    def _bs_check_can_share(self):
        if not self._bs_can_share():
            raise AccessError(self.env._("Only administrators can manage team layouts."))

    @api.model
    def _bs_get_model(self, res_model):
        if not isinstance(res_model, str) or res_model not in self.env:
            raise UserError(self.env._("Unknown model."))
        Model = self.env[res_model]
        Model.check_access('read')
        return Model

    @api.model
    def _bs_is_addable(self, field_info):
        return bool(field_info) and field_info['type'] in ADDABLE_FIELD_TYPES

    @api.model
    def _bs_prepare_vals(self, res_model, action_id, view_id, columns, options):
        """Validate a layout sent by the client and return the record values."""
        options = options if isinstance(options, dict) else {}
        Model = self._bs_get_model(res_model)
        # users load actions through /web/action/load (sudo) and cannot read them
        # directly; only the action's model is compared here
        action = self.env['ir.actions.act_window'].sudo().browse(action_id).exists()
        if not action or action.res_model != res_model:
            raise UserError(self.env._("This list does not belong to the given action."))
        if not isinstance(columns, list):
            raise UserError(self.env._("Invalid column layout."))

        fields_info = Model.fields_get(attributes=['string', 'type'])
        allowed = {col['name'] for col in self._bs_arch_columns(Model, view_id, fields_info)}
        allowed |= {name for name, info in fields_info.items() if self._bs_is_addable(info)}

        clean = [
            column for column in self._bs_sanitize_columns(columns)
            if column['name'] in allowed
        ]
        for column in clean:
            if fields_info[column['name']]['type'] not in AGGREGATABLE_FIELD_TYPES:
                column['aggregate'] = ''
        return {
            'action_id': action.id,
            'res_model': res_model,
            'columns': clean,
            'show_filter_row': bool(options.get('show_filter_row')),
            'show_row_numbers': bool(options.get('show_row_numbers')),
        }

    @api.model
    def _bs_sanitize_columns(self, columns):
        """Keep only well-formed column entries, whatever wrote them."""
        if not isinstance(columns, list):
            return []
        clean, seen = [], set()
        for column in columns[:MAX_COLUMNS]:
            name = column.get('name') if isinstance(column, dict) else None
            if not isinstance(name, str) or name in seen:
                continue
            seen.add(name)
            width = column.get('width')
            aggregate = column.get('aggregate')
            clean.append({
                'name': name,
                'visible': bool(column.get('visible')),
                'label': str(column.get('label') or '').strip()[:MAX_LABEL_LENGTH],
                'width': (
                    int(width)
                    if isinstance(width, (int, float)) and not isinstance(width, bool) and MIN_WIDTH <= width <= MAX_WIDTH
                    else False
                ),
                'aggregate': aggregate if aggregate in AGGREGATES else '',
            })
        return clean

    @api.model
    def _bs_arch_columns(self, Model, view_id, fields_info):
        """Columns of the original list arch that a user may move or hide."""
        arch = etree.fromstring(Model.get_view(view_id or None, 'list')['arch'])
        columns = []
        for node in arch.iterchildren('field'):
            name = node.get('name')
            if (
                name not in fields_info
                or fields_info[name]['type'] in UNMANAGED_FIELD_TYPES
                or node.get('column_invisible') in TRUE_VALUES
                or node.get('widget') == 'handle'
            ):
                continue
            columns.append({
                'name': name,
                'type': fields_info[name]['type'],
                'default_label': node.get('string') or fields_info[name]['string'],
                'label': '',
                'visible': node.get('optional') != 'hide',
                'width': False,
                'aggregate': next((agg for agg in AGGREGATES if node.get(agg)), ''),
                'in_arch': True,
            })
        return columns

    def _bs_apply(self, arch, fields_info, editable=False):
        """Apply this layout to a list arch.

        Field nodes follow the layout order, then the arch fields the layout does not
        mention. They fill the slots field nodes already occupy, so buttons and other
        nodes keep their place; extra (added) fields go after the last slot.

        :param editable: inline editing mode of the team layout, applied whatever
            layout provides the columns
        :return: (new arch, names of the fields added to the arch)
        """
        self.ensure_one()
        root = etree.fromstring(arch)
        if root.tag != 'list':
            return arch, set()

        field_nodes = list(root.iterchildren('field'))
        arch_names = {node.get('name') for node in field_nodes}
        by_name = {node.get('name'): node for node in field_nodes}
        ordered, added = [], set()
        for column in self.columns or []:
            name = column.get('name')
            if (fields_info.get(name) or {}).get('type') in UNMANAGED_FIELD_TYPES:
                # saved before properties were left out: keep the arch node as is
                continue
            node = by_name.pop(name, None)
            if node is None:
                if not column.get('visible') or not self._bs_is_addable(fields_info.get(name)):
                    continue
                node = etree.Element('field', name=name)
                added.add(name)
            if node.get('column_invisible') in TRUE_VALUES:
                ordered.append(node)
                continue
            node.attrib.pop('optional', None)
            if not column.get('visible'):
                node.set('column_invisible', 'True')
            if column.get('label'):
                node.set('string', column['label'])
            if column.get('width'):
                node.set('width', f"{column['width']}px")
            if 'aggregate' in column:
                self._bs_set_aggregate(node, column['aggregate'], fields_info.get(name))
            ordered.append(node)
        ordered += list(by_name.values())

        # monetary columns need their currency field loaded
        for name in list(added):
            currency = fields_info[name].get('currency_field')
            if currency and currency in fields_info and currency not in arch_names and currency not in added:
                ordered.append(etree.Element('field', name=currency, column_invisible='True'))
                added.add(currency)

        slots = [root.index(node) for node in field_nodes]
        for node in field_nodes:
            root.remove(node)
        # re-inserting in ascending slot order puts every slot back at its index
        for position, node in zip(slots, ordered):
            root.insert(position, node)
        after = slots[-1] + 1 if slots else len(root)
        for offset, node in enumerate(ordered[len(slots):]):
            root.insert(after + offset, node)

        root.set(LAYOUT_ATTR, '1')
        if self.show_filter_row:
            root.set(FILTER_ROW_ATTR, '1')
        if self.show_row_numbers:
            root.set(ROW_NUMBERS_ATTR, '1')
        if editable == 'off':
            root.attrib.pop('editable', None)
        elif editable == 'on' and not root.get('editable'):
            root.set('editable', 'bottom')
            root.set(INLINE_EDIT_ATTR, '1')
        return etree.tostring(root, encoding='unicode'), added

    @api.model
    def _bs_set_aggregate(self, node, aggregate, field_info):
        if not field_info or field_info['type'] not in AGGREGATABLE_FIELD_TYPES:
            return
        for agg in AGGREGATES:
            node.attrib.pop(agg, None)
        if aggregate in AGGREGATES:
            node.set(aggregate, field_info.get('string') or '')
