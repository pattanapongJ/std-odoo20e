# -*- coding: utf-8 -*-

from lxml import etree

from collections import defaultdict
from collections.abc import Iterable

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import SQL

# The field the search panel offers, and the group that may see it.
PANEL_FIELD = "product_attribute_value_ids"
VARIANT_GROUP = "product.group_product_variant"


class ProductProduct(models.Model):
    _inherit = "product.product"

    product_attribute_value_ids = fields.Many2many(
        "product.attribute.value",
        relation="product_variant_attribute_value_rel",
        column1="product_id",
        column2="value_id",
        # Core's product_template_attribute_value_ids is "Attribute Values".
        string="Shared Attribute Values",
        compute="_compute_product_attribute_value_ids",
        store=True,
        help="The values behind this variant's attributes, as the catalogue "
        "knows them rather than as each product's template copies them.",
    )

    # The columns are defined once for all variants, on core's definition for
    # properties without a parent - as properties.base.definition.mixin does
    # for res.partner. The mixin fixes the field name to "properties", hence
    # the same three members spelt out here for this field.
    attribute_properties_definition_id = fields.Many2one(
        "properties.base.definition",
        string="Attribute Columns Definition",
        compute="_compute_attribute_properties_definition_id",
        compute_sql="_compute_sql_attribute_properties_definition_id",
        search="_search_attribute_properties_definition_id",
        compute_sudo=True,
    )
    attribute_properties = fields.Properties(
        string="Attribute Columns",
        definition="attribute_properties_definition_id.properties_definition",
        readonly=True,
    )

    attribute_summary = fields.Char(
        # Core's product_template_variant_value_ids is "Attributes".
        string="Attribute Summary",
        compute="_compute_attribute_summary",
        help="Every attribute of the variant with its value, single-value "
        "lines included. For reading only: it is not stored, so it cannot be "
        "grouped or sorted by.",
    )

    @api.depends(
        "product_template_attribute_value_ids.attribute_id",
        "product_template_attribute_value_ids.name",
    )
    def _compute_attribute_summary(self):
        for product in self:
            values = product.product_template_attribute_value_ids.sorted(
                lambda value: (value.attribute_line_id.sequence, value.attribute_id.sequence,
                               value.attribute_id.id)
            )
            product.attribute_summary = ", ".join(
                f"{value.attribute_id.name}: {value.name}" for value in values
            )

    @api.model
    def _attribute_properties_definition(self):
        return self.env["properties.base.definition"].sudo()._get_definition_for_property_field(
            "product.product", "attribute_properties"
        )

    def _compute_attribute_properties_definition_id(self):
        self.attribute_properties_definition_id = self._attribute_properties_definition()

    def _compute_sql_attribute_properties_definition_id(self, table):
        return SQL("%s", self._attribute_properties_definition().id)

    def _search_attribute_properties_definition_id(self, operator, value):
        if operator != "in":
            return NotImplemented
        if not isinstance(value, Iterable):
            value = (value,)
        return Domain.TRUE if self._attribute_properties_definition().id in value else Domain.FALSE

    @api.model_create_multi
    def create(self, vals_list):
        definition = self._attribute_properties_definition()
        for vals in vals_list:
            vals["attribute_properties_definition_id"] = definition.id
        products = super().create(vals_list)
        products._sync_attribute_columns()
        return products

    def write(self, vals):
        result = super().write(vals)
        if "product_template_attribute_value_ids" in vals:
            self._sync_attribute_columns()
        return result

    @api.model
    def _variants_with_attributes(self, attributes):
        return self.with_context(active_test=False).search(
            [("product_template_attribute_value_ids.attribute_id", "in", attributes.ids)]
        )

    def _sync_attribute_columns(self):
        """Write each variant's value for every attribute shown as a column.

        The whole property dict is written, not merged: this module owns every
        property of the field, so a column switched off drops out here too.
        Variants that end up with the same values are written together.
        """
        attributes = self.env["product.attribute"].sudo().search(
            [("variant_column", "=", True)]
        )
        names = {attribute.id: attribute._column_name() for attribute in attributes}
        batches = defaultdict(lambda: self.browse())
        for product in self.sudo().with_context(active_test=False):
            values = {
                names[ptav.attribute_id.id]: ptav.product_attribute_value_id._column_option()
                for ptav in product.product_template_attribute_value_ids
                if ptav.attribute_id.id in names
            }
            if product.attribute_properties != values:
                batches[tuple(sorted(values.items()))] |= product
        for values, products in batches.items():
            products.with_context(tracking_disable=True).write(
                {"attribute_properties": dict(values)}
            )

    @api.depends("product_template_attribute_value_ids.product_attribute_value_id")
    def _compute_product_attribute_value_ids(self):
        """The catalogue values behind the variant's combination.

        product.template.attribute.value holds one record per template, so the
        same "18 mm" is a different record on every product that offers it.
        Searching or grouping on those lists "18 mm" once per template, which
        is not what a person asking for the 18 mm ones means. The value behind
        them is shared, and is what this field points at.

        Stored because the search panel groups on it, and grouping is done in
        SQL.
        """
        for product in self:
            product.product_attribute_value_ids = (
                product.product_template_attribute_value_ids.product_attribute_value_id
            )

    @api.model
    def search_panel_select_multi_range(self, field_name, **kwargs):
        """Leave the attribute's name out of its own values.

        product.attribute.value renders as "Paint Color: Red" so that a value
        means something on its own. Under a section already headed Paint Color
        it says it twice. The headers are read off product.attribute and keep
        their full name.
        """
        if field_name == PANEL_FIELD:
            self = self.with_context(show_attribute=False)
        return super().search_panel_select_multi_range(field_name, **kwargs)

    def _get_view(self, view_id=None, view_type="form", **options):
        """Offer the attributes in every variant list and search view.

        Done here rather than in get_view so the injected node still goes
        through postprocessing: that is what reads the groups attribute and
        what tells the web client the field exists.
        """
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == "search":
            self._add_attribute_search_panel(arch)
            self._add_attribute_columns_search(arch)
        elif view_type == "list":
            self._add_attribute_columns_list(arch)
        return arch, view

    def _add_attribute_columns_list(self, arch):
        """One optional column per attribute marked Column on Variants.

        The web client expands a Properties field into a hidden-by-default
        column per property, so the field is all a list needs - in the stock
        report as much as in the variant list.
        """
        if arch.tag != "list" or arch.xpath("//field[@name='attribute_properties']"):
            return
        etree.SubElement(arch, "field", {
            "name": "attribute_properties_definition_id", "column_invisible": "1",
        })
        etree.SubElement(arch, "field", {
            "name": "attribute_properties",
            "readonly": "1",
            "groups": VARIANT_GROUP,
        })

    def _add_attribute_columns_search(self, arch):
        """A Group By entry that unfolds into one item per attribute column.

        A group_by filter on a Properties field is what the web client
        expands into its properties, the way core offers Product Properties.
        """
        if arch.xpath("//filter[@name='group_by_attribute_columns']"):
            return
        group = next(
            iter(arch.xpath("//group[filter[contains(@context, 'group_by')]]")), None
        )
        if group is None:
            group = etree.SubElement(arch, "group")
        etree.SubElement(group, "filter", {
            "name": "group_by_attribute_columns",
            "string": self.env._("Attribute Columns"),
            "context": "{'group_by': 'attribute_properties'}",
            "groups": VARIANT_GROUP,
        })

    def _add_attribute_search_panel(self, arch):
        """Extend the view's search panel, or give it one.

        Declaring a <searchpanel> in the arch would be simpler, but a search
        view may already carry one - stock adds a Category panel to its
        product report, product one to the catalogue - and a second panel
        takes the place of the first rather than adding to it.
        """
        if arch.xpath("//searchpanel/field[@name='%s']" % PANEL_FIELD):
            return
        panel = next(iter(arch.xpath("//searchpanel")), None)
        if panel is None:
            panel = etree.SubElement(arch, "searchpanel")
        etree.SubElement(
            panel,
            "field",
            {
                "name": PANEL_FIELD,
                "string": self.env._("Attributes"),
                "icon": "sell",
                # One section per attribute rather than one long list.
                "groupby": "attribute_id",
                # The panel cannot be folded and gives up entirely past 200
                # values, so which attributes belong in it is a decision the
                # catalogue makes rather than one taken here.
                "domain": "[('attribute_id.show_in_search_panel', '=', True)]",
                "select": "multi",
                "enable_counters": "1",
                # Applied per user at postprocessing, after the arch is cached.
                "groups": VARIANT_GROUP,
            },
        )
