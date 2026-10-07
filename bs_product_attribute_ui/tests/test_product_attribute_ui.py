# -*- coding: utf-8 -*-

from lxml import etree

from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon


@tagged("post_install", "-at_install")
class TestProductAttributeUi(BaseCommon):
    _test_user_groups = (
        "base.group_user",
        "product.group_product_manager",
        "product.group_product_variant",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Attribute = cls.env["product.attribute"]
        Value = cls.env["product.attribute.value"]
        cls.thickness = Attribute.create({"name": "UI Thickness"})
        cls.thick_18, cls.thick_25 = Value.create([
            {"name": "18 mm", "attribute_id": cls.thickness.id},
            {"name": "25 mm", "attribute_id": cls.thickness.id},
        ])
        cls.finish = Attribute.create({"name": "UI Finish"})
        cls.matt = Value.create({"name": "Matt", "attribute_id": cls.finish.id})
        cls.hidden = Attribute.create(
            {"name": "UI Batch", "show_in_search_panel": False}
        )
        cls.batch = Value.create({"name": "B1", "attribute_id": cls.hidden.id})

    @classmethod
    def make_template(cls, name, thicknesses, with_finish=True):
        lines = [(0, 0, {"attribute_id": cls.thickness.id,
                         "value_ids": [(6, 0, thicknesses.ids)]})]
        if with_finish:
            lines.append((0, 0, {"attribute_id": cls.finish.id,
                                 "value_ids": [(6, 0, cls.matt.ids)]}))
        return cls.env["product.template"].create(
            {"name": name, "attribute_line_ids": lines}
        )

    def test_variants_point_at_the_shared_values(self):
        template = self.make_template("UI Panel", self.thick_18 | self.thick_25)

        variant_18 = template.product_variant_ids.filtered(
            lambda variant: self.thick_18 in variant.product_attribute_value_ids
        )

        self.assertEqual(len(template.product_variant_ids), 2)
        self.assertEqual(variant_18.product_attribute_value_ids, self.thick_18 | self.matt)

    def test_a_single_value_line_is_kept(self):
        """Core's variant tags drop it; the stored values must not."""
        template = self.make_template("UI Single", self.thick_18)

        self.assertIn(self.matt, template.product_variant_ids.product_attribute_value_ids)

    def test_the_summary_lists_every_attribute(self):
        template = self.make_template("UI Summary", self.thick_18)

        self.assertEqual(
            template.product_variant_ids.attribute_summary,
            "UI Thickness: 18 mm, UI Finish: Matt",
        )

    def test_one_value_finds_variants_of_every_template(self):
        first = self.make_template("UI First", self.thick_18)
        second = self.make_template("UI Second", self.thick_18 | self.thick_25)

        found = self.env["product.product"].search(
            [("product_attribute_value_ids", "in", self.thick_18.ids)]
        )

        self.assertEqual(
            found.product_tmpl_id & (first | second), first | second
        )
        self.assertNotIn(self.thick_25, found.product_attribute_value_ids - self.thick_18
                         - self.matt)

    def test_the_values_follow_a_changed_combination(self):
        template = self.make_template("UI Change", self.thick_18, with_finish=False)
        variant = template.product_variant_ids
        line = template.attribute_line_ids

        line.value_ids = self.thick_25
        variant = template.product_variant_ids

        self.assertEqual(variant.product_attribute_value_ids, self.thick_25)

    def test_grouping_by_value_merges_templates(self):
        self.make_template("UI Group A", self.thick_18)
        self.make_template("UI Group B", self.thick_18)

        groups = self.env["product.product"].formatted_read_group(
            [("product_tmpl_id.name", "like", "UI Group")],
            ["product_attribute_value_ids"],
            ["__count"],
        )

        counts = {
            group["product_attribute_value_ids"][0]: group["__count"]
            for group in groups
            if group["product_attribute_value_ids"]
        }
        self.assertEqual(counts[self.thick_18.id], 2)

    def panel(self, **kwargs):
        return self.env["product.product"].search_panel_select_multi_range(
            "product_attribute_value_ids",
            group_by="attribute_id",
            enable_counters=True,
            comodel_domain=[("attribute_id.show_in_search_panel", "=", True)],
            **kwargs,
        )

    def test_the_panel_groups_values_under_their_attribute(self):
        self.make_template("UI Panel", self.thick_18 | self.thick_25)

        values = {value["id"]: value for value in self.panel()["values"]}

        self.assertEqual(values[self.thick_18.id]["display_name"], "18 mm")
        self.assertEqual(values[self.thick_18.id]["group_name"], "UI Thickness")
        self.assertEqual(values[self.thick_18.id]["__count"], 1)

    def test_the_panel_leaves_out_attributes_switched_off(self):
        self.env["product.template"].create({
            "name": "UI Batched",
            "attribute_line_ids": [
                (0, 0, {"attribute_id": self.thickness.id,
                        "value_ids": [(6, 0, self.thick_18.ids)]}),
                (0, 0, {"attribute_id": self.hidden.id,
                        "value_ids": [(6, 0, self.batch.ids)]}),
            ],
        })

        values = {value["id"] for value in self.panel()["values"]}

        self.assertIn(self.thick_18.id, values)
        self.assertNotIn(self.batch.id, values)

    def search_arch(self, view_ref):
        view = self.env.ref(view_ref)
        arch = self.env["product.product"].get_view(view.id, "search")["arch"]
        return etree.fromstring(arch)

    def test_the_variant_search_view_gets_a_panel(self):
        arch = self.search_arch("product.product_search_form_view")

        fields = arch.xpath("//searchpanel/field[@name='product_attribute_value_ids']")
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0].get("groupby"), "attribute_id")
        self.assertTrue(arch.xpath("//filter[@name='group_by_attribute_value']"))

    def test_an_existing_panel_is_extended_not_replaced(self):
        arch = self.search_arch("product.product_view_search_catalog")

        self.assertEqual(len(arch.xpath("//searchpanel")), 1)
        panel_fields = [field.get("name") for field in arch.xpath("//searchpanel/field")]
        self.assertIn("categ_id", panel_fields)
        self.assertIn("product_attribute_value_ids", panel_fields)

    def test_the_variant_list_offers_the_summary(self):
        view = self.env.ref("product.product_product_tree_view")
        arch = etree.fromstring(
            self.env["product.product"].get_view(view.id, "list")["arch"]
        )

        self.assertTrue(arch.xpath("//field[@name='attribute_summary'][@optional='hide']"))

    def test_the_form_shows_the_rows_widget(self):
        view = self.env.ref("product.product_normal_form_view")
        arch = etree.fromstring(
            self.env["product.product"].get_view(view.id, "form")["arch"]
        )

        self.assertTrue(arch.xpath(
            "//field[@name='product_template_attribute_value_ids']"
            "[@widget='product_attribute_rows']"
        ))

    # -- attribute columns -----------------------------------------------

    def definition(self):
        record = self.env["product.product"]._attribute_properties_definition()
        return {prop["name"]: prop for prop in record.properties_definition or []}

    def test_a_column_is_defined_with_the_attribute_values(self):
        self.thickness.variant_column = True

        column = self.definition()[f"attribute_{self.thickness.id}"]
        self.assertEqual(column["string"], "UI Thickness")
        self.assertEqual(column["type"], "selection")
        self.assertEqual(
            [label for _key, label in column["selection"]], ["18 mm", "25 mm"]
        )
        self.assertNotIn(f"attribute_{self.finish.id}", self.definition())

    def test_switching_a_column_on_fills_existing_variants(self):
        template = self.make_template("UI Col", self.thick_18 | self.thick_25)

        self.thickness.variant_column = True

        values = {
            variant.id: variant.with_context(property_selection_get_label=True)
            .attribute_properties[f"attribute_{self.thickness.id}"]
            for variant in template.product_variant_ids
        }
        self.assertEqual(sorted(values.values()), ["18 mm", "25 mm"])

    def test_a_new_variant_gets_its_columns(self):
        self.thickness.variant_column = True

        variant = self.make_template("UI New", self.thick_25).product_variant_ids

        self.assertEqual(
            variant.attribute_properties,
            {f"attribute_{self.thickness.id}": f"value_{self.thick_25.id}"},
        )

    def test_switching_a_column_off_clears_it(self):
        self.thickness.variant_column = True
        variant = self.make_template("UI Off", self.thick_18).product_variant_ids

        self.thickness.variant_column = False

        self.assertEqual(variant.attribute_properties, {})
        self.assertNotIn(f"attribute_{self.thickness.id}", self.definition())

    def test_renames_reach_the_column_without_touching_variants(self):
        self.thickness.variant_column = True
        variant = self.make_template("UI Rename", self.thick_18).product_variant_ids
        stored = dict(variant.attribute_properties._values)

        self.thickness.name = "UI Board Thickness"
        self.thick_18.name = "18.0 mm"

        column = self.definition()[f"attribute_{self.thickness.id}"]
        self.assertEqual(column["string"], "UI Board Thickness")
        self.assertIn([f"value_{self.thick_18.id}", "18.0 mm"], column["selection"])
        self.assertEqual(variant.attribute_properties, stored)

    def test_a_new_value_becomes_an_option(self):
        self.thickness.variant_column = True

        value = self.env["product.attribute.value"].create(
            {"name": "30 mm", "attribute_id": self.thickness.id}
        )

        options = [key for key, _label in self.definition()[f"attribute_{self.thickness.id}"]["selection"]]
        self.assertIn(f"value_{value.id}", options)

    def test_the_list_can_be_grouped_by_a_column(self):
        self.thickness.variant_column = True
        self.make_template("UI GroupCol A", self.thick_18)
        self.make_template("UI GroupCol B", self.thick_18 | self.thick_25)
        column = f"attribute_properties.attribute_{self.thickness.id}"

        groups = self.env["product.product"].formatted_read_group(
            [("product_tmpl_id.name", "like", "UI GroupCol")], [column], ["__count"]
        )

        counts = {group[column]: group["__count"] for group in groups}
        self.assertEqual(counts[f"value_{self.thick_18.id}"], 2)
        self.assertEqual(counts[f"value_{self.thick_25.id}"], 1)

    def test_the_views_carry_the_columns(self):
        list_arch = etree.fromstring(self.env["product.product"].get_view(
            self.env.ref("product.product_product_tree_view").id, "list")["arch"])
        search_arch = self.search_arch("product.product_search_form_view")

        self.assertTrue(list_arch.xpath("//field[@name='attribute_properties'][@readonly='1']"))
        self.assertTrue(search_arch.xpath(
            "//filter[@name='group_by_attribute_columns']"
            "[@context=\"{'group_by': 'attribute_properties'}\"]"
        ))

    def test_the_web_client_finds_the_columns_from_any_action(self):
        """The Variants button opens with active_id set to the template. The
        web client filters ordinary definition records by that id, which found
        nothing; the base definition is looked up by model and field instead."""
        self.thickness.variant_column = True

        result = self.env["properties.base.definition"].get_properties_base_definition(
            "product.product", "attribute_properties"
        )

        names = [prop["name"] for prop in result["records"][0]["properties_definition"]]
        self.assertIn(f"attribute_{self.thickness.id}", names)

    def test_a_variant_reads_its_column_labels(self):
        self.thickness.variant_column = True
        variant = self.make_template("UI Label", self.thick_18).product_variant_ids

        label = variant.with_context(property_selection_get_label=True).attribute_properties[
            f"attribute_{self.thickness.id}"
        ]

        self.assertEqual(label, "18 mm")
