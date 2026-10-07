from odoo import api, models


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def get_views(self, views, options=None):
        result = super().get_views(views, options)
        action_id = (options or {}).get('action_id')
        list_view = result['views'].get('list')
        if not action_id or not list_view:
            return result
        Layout = self.env['bs.view.layout']
        # inline editing is a list-wide policy: it applies whatever layout the user gets
        layout, editable = Layout._bs_lookup(self._name, action_id)
        if not layout and not editable:
            return result
        model_fields = result['models'][self._name]['fields']
        fields_info = self._bs_fields_info(model_fields, layout)
        list_view['arch'], added = (layout or Layout.new({}))._bs_apply(list_view['arch'], fields_info, editable)
        for name in added:
            model_fields[name] = fields_info[name]
        return result

    @api.model
    def _bs_fields_info(self, model_fields, layout):
        """Descriptions of the fields the layout may use. With a search view,
        get_views already describes every field; only fetch the missing ones."""
        attributes = self._get_view_field_attributes()
        names = {column['name'] for column in layout.columns or []}
        missing = [name for name in names - model_fields.keys() if name in self._fields]
        fields_info = {**model_fields, **(self.fields_get(missing, attributes) if missing else {})}
        # an added monetary column also needs its currency field
        currencies = {
            fields_info[name].get('currency_field') for name in names if name in fields_info
        } - fields_info.keys() - {None}
        currencies = [name for name in currencies if name in self._fields]
        if currencies:
            fields_info.update(self.fields_get(currencies, attributes))
        return fields_info
