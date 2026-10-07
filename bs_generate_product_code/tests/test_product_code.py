# -*- coding: utf-8 -*-

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import BinaryBytes

from odoo.addons.base.tests.common import BaseCommon

LOGGER = "odoo.addons.bs_generate_product_code.models.product_code_rule_line"

@tagged("post_install", "-at_install")
class TestProductCode(BaseCommon):
    # Rules are kept by inventory administrators, who also manage products.
    _test_user_groups = (
        "base.group_user",
        "stock.group_stock_manager",
        "product.group_product_manager",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_bool(
            "bs_generate_product_code.autogenerate", True
        )

        Attribute = cls.env["product.attribute"]
        Value = cls.env["product.attribute.value"]
        cls.thickness = Attribute.create({"name": "Code Thickness"})
        cls.thick_18, cls.thick_25 = Value.create(
            [
                {"name": "18 mm", "attribute_id": cls.thickness.id},
                {"name": "25 mm", "attribute_id": cls.thickness.id},
            ]
        )
        cls.width = Attribute.create({"name": "Code Width"})
        cls.width_1220 = Value.create(
            {"name": "1220 mm", "attribute_id": cls.width.id}
        )
        cls.category = cls.env["product.category"].create({"name": "Code Panels"})
        cls.ATTRIBUTE_NAMES = (
            "product_template_attribute_value_ids.product_attribute_value_id.name"
        )

    # -- helpers ---------------------------------------------------------

    def make_rule(self, lines, domain="[]", sequence=10, name="Test Rule"):
        rule = self.env["product.code.rule"].create(
            {"name": name, "sequence": sequence, "product_domain": domain}
        )
        for index, line in enumerate(lines, start=1):
            self.env["product.code.rule.line"].create(
                dict({"rule_id": rule.id, "sequence": index * 10}, **line)
            )
        return rule

    def make_product(self, name="Code Panel", with_attributes=True):
        vals = {"name": name, "type": "consu", "categ_id": self.category.id}
        if with_attributes:
            vals["attribute_line_ids"] = [
                (0, 0, {"attribute_id": self.thickness.id, "sequence": 10,
                        "value_ids": [(6, 0, self.thick_18.ids)]}),
                (0, 0, {"attribute_id": self.width.id, "sequence": 20,
                        "value_ids": [(6, 0, self.width_1220.ids)]}),
            ]
        return self.env["product.template"].create(vals)

    # -- parts -----------------------------------------------------------

    def test_a_field_part_reads_a_product_field(self):
        self.make_rule([{"value_type": "field",
                         "field_path": "product_tmpl_id.name"}])

        self.assertEqual(
            self.make_product().product_variant_ids.default_code, "Code Panel"
        )

    def test_a_field_part_walks_a_nested_path(self):
        """The path is stored exactly as the export dialog writes it."""
        self.make_rule([{"value_type": "field", "field_path": "categ_id.name"}])

        self.assertEqual(
            self.make_product().product_variant_ids.default_code, "Code Panels"
        )

    def test_a_text_part_is_used_verbatim(self):
        self.make_rule([{"value_type": "text", "text": "ACME"}])

        self.assertEqual(self.make_product().product_variant_ids.default_code, "ACME")

    def test_parts_are_joined_in_sequence_order(self):
        self.make_rule([
            {"value_type": "text", "text": "A"},
            {"value_type": "field", "field_path": "product_tmpl_id.name"},
            {"value_type": "field", "field_path": self.ATTRIBUTE_NAMES},
        ])

        self.assertEqual(
            self.make_product().product_variant_ids.default_code,
            "ACode Panel18 mm1220 mm",
        )

    def test_prefix_and_suffix_wrap_the_part(self):
        self.make_rule([{"value_type": "field",
                         "field_path": "product_tmpl_id.name",
                         "prefix": "-", "suffix": "T"}])

        self.assertEqual(
            self.make_product().product_variant_ids.default_code, "-Code PanelT"
        )

    def test_a_part_that_resolves_to_nothing_takes_its_prefix_with_it(self):
        self.make_rule([
            {"value_type": "field", "field_path": "product_tmpl_id.name"},
            {"value_type": "field", "field_path": "barcode",
             "prefix": "/", "suffix": "!"},
        ])

        self.assertEqual(
            self.make_product().product_variant_ids.default_code, "Code Panel"
        )

    def test_a_path_through_a_list_contributes_every_value(self):
        """Reading a field off several records at once raises Expected
        singleton, so the path has to be resolved with mapped()."""
        self.make_rule([{
            "value_type": "field",
            "field_path": self.ATTRIBUTE_NAMES,
        }])

        self.assertEqual(
            self.make_product().product_variant_ids.default_code, "18 mm1220 mm"
        )

    def test_the_separator_goes_between_the_values_of_a_list(self):
        self.make_rule([{"value_type": "field",
                         "field_path": self.ATTRIBUTE_NAMES,
                         "separate_with": "/"}])

        self.assertEqual(
            self.make_product().product_variant_ids.default_code, "18 mm/1220 mm"
        )

    def test_the_transform_runs_on_each_value_not_on_the_joined_string(self):
        """Digits only would otherwise eat the separator, and Pad would pad the
        whole run instead of each value."""
        self.make_rule([{"value_type": "field",
                         "field_path": self.ATTRIBUTE_NAMES,
                         "separate_with": "-", "transform": "digits"}])

        self.assertEqual(
            self.make_product().product_variant_ids.default_code, "18-1220"
        )

    def test_padding_applies_to_each_value_of_a_list(self):
        """Each value is padded on its own: padding the joined run would pad
        once, at the front, and leave the later values short."""
        self.make_rule([{"value_type": "field",
                         "field_path": self.ATTRIBUTE_NAMES,
                         "separate_with": "-", "transform": "pad", "length": 6}])

        self.assertEqual(
            self.make_product().product_variant_ids.default_code,
            "018 mm-1220 mm",
        )

    def test_a_separator_is_only_offered_for_multi_value_fields(self):
        """The column is there for lists; a scalar path has nothing to
        separate, so the cell stays empty."""
        Line = self.env["product.code.rule.line"]
        listy = Line.new({"value_type": "field", "field_path": self.ATTRIBUTE_NAMES})
        scalar = Line.new({"value_type": "field", "field_path": "categ_id.name"})
        text = Line.new({"value_type": "text", "text": "ACME"})

        self.assertTrue(listy.is_multi_value)
        self.assertFalse(scalar.is_multi_value)
        self.assertFalse(text.is_multi_value)

    # -- other field types -------------------------------------------------

    def test_a_boolean_contributes_nothing(self):
        """"True" has no place in an internal reference."""
        self.make_rule([
            {"value_type": "text", "text": "A"},
            {"value_type": "field", "field_path": "active"},
        ])

        self.assertEqual(self.make_product().product_variant_ids.default_code, "A")

    def test_a_datetime_becomes_compact_digits(self):
        self.make_rule([{"value_type": "field", "field_path": "create_date"}])
        product = self.make_product()

        self.assertEqual(
            product.product_variant_ids.default_code,
            product.create_date.strftime("%Y%m%d"),
        )

    def test_markup_and_newlines_never_reach_the_reference(self):
        """A newline in an internal reference breaks reports and exports."""
        self.make_rule([{"value_type": "field",
                         "field_path": "description_sale"}])
        template = self.make_product()
        template.description_sale = "Nice <b>chair</b>\nwith  gaps &amp; markup"
        template.product_variant_ids.action_generate_default_code()

        self.assertEqual(
            template.product_variant_ids.default_code,
            "Nice chair with gaps & markup",
        )

    def test_a_selection_keeps_its_technical_key(self):
        self.make_rule([{"value_type": "field", "field_path": "type"}])

        self.assertEqual(self.make_product().product_variant_ids.default_code, "consu")

    def test_a_float_keeps_its_decimals(self):
        self.make_rule([{"value_type": "field", "field_path": "weight"}])
        template = self.make_product()
        template.weight = 12.5
        template.product_variant_ids.action_generate_default_code()

        self.assertEqual(template.product_variant_ids.default_code, "12.5")

    def test_a_whole_float_loses_its_decimal_point(self):
        self.make_rule([{"value_type": "field", "field_path": "weight"}])
        template = self.make_product()
        template.weight = 12.0
        template.product_variant_ids.action_generate_default_code()

        self.assertEqual(template.product_variant_ids.default_code, "12")

    def test_an_unknown_field_is_refused(self):
        for path in ("no_such_field", "categ_id.no_such_field", "name.anything"):
            with self.subTest(path=path), self.assertRaises(ValidationError):
                self.make_rule([{"value_type": "field", "field_path": path}])

    def break_path(self, line):
        """A field that disappears later, as when its module is uninstalled."""
        self.env.cr.execute(
            "UPDATE product_code_rule_line SET field_path = 'no_such_field' "
            "WHERE id = %s",
            [line.id],
        )
        line.invalidate_recordset()

    def test_a_broken_path_leaves_the_reference_alone(self):
        rule = self.make_rule([
            {"value_type": "field", "field_path": "categ_id.name"},
            {"value_type": "field", "field_path": "product_tmpl_id.name",
             "prefix": "-"},
        ])
        product = self.make_product(with_attributes=False).product_variant_ids
        self.assertEqual(product.default_code, "Code Panels-Code Panel")
        self.break_path(rule.line_ids[1])

        with self.assertLogs(LOGGER, "WARNING"):
            self.recategorise(product)
            self.assertEqual(product.default_code, "Code Panels-Code Panel")
            self.assertFalse(product._generate_default_code())
            self.assertEqual(self.preview(product).line_ids.state, "broken")
            self.assertEqual(rule.example, "Cannot read no_such_field")

    def test_a_new_product_under_a_broken_rule_gets_no_reference(self):
        rule = self.make_rule([
            {"value_type": "field", "field_path": "categ_id.name"},
            {"value_type": "field", "field_path": "product_tmpl_id.name"},
        ])
        self.break_path(rule.line_ids[1])

        with self.assertLogs(LOGGER, "WARNING"):
            product = self.make_product(with_attributes=False).product_variant_ids
        self.assertFalse(product.default_code)

    # -- transforms ------------------------------------------------------

    def test_truncate_keeps_the_first_characters(self):
        self.make_rule([{"value_type": "field", "field_path": "categ_id.name",
                         "transform": "truncate", "length": 4}])

        self.assertEqual(self.make_product().product_variant_ids.default_code, "Code")

    def test_upper_and_lower_normalise_the_value(self):
        self.make_rule([{"value_type": "field", "field_path": "categ_id.name",
                         "transform": "upper"}])
        self.assertEqual(
            self.make_product("Upper").product_variant_ids.default_code, "CODE PANELS"
        )

    def test_pad_reaches_a_fixed_width(self):
        self.make_rule([{"value_type": "text", "text": "18",
                         "transform": "pad", "length": 4}])

        self.assertEqual(self.make_product().product_variant_ids.default_code, "0018")

    def test_digits_only_strips_everything_else(self):
        self.make_rule([{"value_type": "text", "text": "AB-12/34",
                         "transform": "digits"}])

        self.assertEqual(self.make_product().product_variant_ids.default_code, "1234")

    # -- rules and domains -----------------------------------------------

    def test_the_domain_decides_which_products_a_rule_covers(self):
        self.make_rule(
            [{"value_type": "text", "text": "PANEL"}],
            domain=f"[('categ_id', '=', {self.category.id})]",
        )
        other = self.env["product.category"].create({"name": "Code Other"})
        outside = self.env["product.template"].create(
            {"name": "Code Outside", "type": "consu", "categ_id": other.id,
             "default_code": "KEEP"}
        )

        self.assertEqual(self.make_product().product_variant_ids.default_code, "PANEL")
        self.assertEqual(outside.product_variant_ids.default_code, "KEEP")

    def test_the_first_matching_rule_wins(self):
        self.make_rule([{"value_type": "text", "text": "SPECIFIC"}],
                       domain=f"[('categ_id', '=', {self.category.id})]",
                       sequence=1, name="Specific")
        self.make_rule([{"value_type": "text", "text": "FALLBACK"}],
                       sequence=99, name="Fallback")

        self.assertEqual(
            self.make_product().product_variant_ids.default_code, "SPECIFIC"
        )

    def test_a_catch_all_rule_covers_what_is_left(self):
        self.make_rule([{"value_type": "text", "text": "FALLBACK"}], sequence=99)

        product = self.env["product.template"].create(
            {"name": "Code Anything", "type": "consu"}
        )
        self.assertEqual(product.product_variant_ids.default_code, "FALLBACK")

    def test_a_product_no_rule_matches_keeps_its_reference(self):
        """The 14.0 module blanked the reference of every unrelated product."""
        product = self.env["product.product"].create(
            {"name": "Code Widget", "default_code": "MANUAL-001"}
        )

        self.assertEqual(product.default_code, "MANUAL-001")

    def test_a_reference_given_explicitly_survives_a_catch_all_rule(self):
        """A catch-all rule is what the Apply To help text suggests, and it
        must not overwrite a reference the caller supplied."""
        self.make_rule([{"value_type": "text", "text": "GENERATED"}], sequence=99)

        product = self.env["product.product"].create(
            {"name": "Code Supplied", "default_code": "SUPPLIED-001"}
        )

        self.assertEqual(product.default_code, "SUPPLIED-001")

    def test_a_product_created_without_a_reference_still_gets_one(self):
        self.make_rule([{"value_type": "text", "text": "GENERATED"}], sequence=99)

        product = self.env["product.product"].create({"name": "Code Blank"})

        self.assertEqual(product.default_code, "GENERATED")

    def test_the_manual_action_still_overwrites_a_supplied_reference(self):
        self.make_rule([{"value_type": "text", "text": "GENERATED"}], sequence=99)
        product = self.env["product.product"].create(
            {"name": "Code Manual", "default_code": "SUPPLIED-002"}
        )

        product.action_generate_default_code()

        self.assertEqual(product.default_code, "GENERATED")

    def test_the_example_follows_an_edit_to_a_part(self):
        """The Example exists to show the effect of an edit, so it must not
        keep answering from before the write."""
        rule = self.make_rule([{"value_type": "text", "text": "AAA"}])
        self.make_product()
        before = rule.example

        rule.line_ids[0].prefix = "X"

        self.assertEqual(before, "AAA")
        self.assertEqual(rule.example, "XAAA")

    def test_a_length_of_zero_is_refused(self):
        """Length 0 would silently delete the part."""
        with self.assertRaises(ValidationError):
            self.make_rule([{"value_type": "text", "text": "ABC",
                             "transform": "truncate", "length": 0}])

    def test_an_oversized_length_is_refused(self):
        with self.assertRaises(ValidationError):
            self.make_rule([{"value_type": "text", "text": "1",
                             "transform": "pad", "length": 1000}])

    def test_only_products_that_changed_are_counted(self):
        self.make_rule([{"value_type": "text", "text": "SAME"}])
        variants = self.make_product().product_variant_ids
        self.assertEqual(variants.default_code, "SAME")

        self.assertFalse(variants._generate_default_code())

    def test_nothing_is_generated_while_the_switch_is_off(self):
        self.env["ir.config_parameter"].sudo().set_bool(
            "bs_generate_product_code.autogenerate", False
        )
        self.make_rule([{"value_type": "text", "text": "X"}])

        self.assertFalse(self.make_product().product_variant_ids.default_code)

    # -- manual regeneration ---------------------------------------------

    def test_the_manual_action_applies_a_rule_added_later(self):
        self.env["ir.config_parameter"].sudo().set_bool(
            "bs_generate_product_code.autogenerate", False
        )
        template = self.make_product()
        self.assertFalse(template.product_variant_ids.default_code)

        self.make_rule([{"value_type": "text", "text": "LATER"}])
        template.product_variant_ids.action_generate_default_code()

        self.assertEqual(template.product_variant_ids.default_code, "LATER")

    def test_the_manual_action_leaves_unmatched_products_alone(self):
        product = self.env["product.product"].create(
            {"name": "Code Plain", "default_code": "KEEP-ME"}
        )
        product.action_generate_default_code()

        self.assertEqual(product.default_code, "KEEP-ME")

    # -- validation ------------------------------------------------------

    def test_a_field_part_needs_a_field(self):
        with self.assertRaises(ValidationError):
            self.make_rule([{"value_type": "field"}])


    # -- values that arrive after the product ----------------------------

    def test_a_combination_written_after_creation_rebuilds_the_reference(self):
        """Core writes single-value attributes onto variants that already
        exist, so the values a reference is built from can arrive after the
        product does.  See product/models/product_template.py, the
        `single_value_lines` block of _create_variant_ids.
        """
        self.make_rule(
            [
                {"value_type": "text", "text": "PANEL-"},
                {
                    "value_type": "field",
                    "field_path": self.ATTRIBUTE_NAMES,
                    "separate_with": "/",
                },
            ]
        )
        template = self.make_product(with_attributes=False)
        self.assertEqual(template.product_variant_ids.default_code, "PANEL-")

        template.write(
            {
                "attribute_line_ids": [
                    (0, 0, {"attribute_id": self.thickness.id, "sequence": 10,
                            "value_ids": [(6, 0, self.thick_18.ids)]}),
                    (0, 0, {"attribute_id": self.width.id, "sequence": 20,
                            "value_ids": [(6, 0, self.width_1220.ids)]}),
                ]
            }
        )

        self.assertEqual(
            template.product_variant_ids.default_code, "PANEL-18 mm/1220 mm"
        )

    def test_a_generated_reference_follows_a_watched_field(self):
        self.make_rule([{"value_type": "field", "field_path": "categ_id.name"}])
        product = self.env["product.product"].create(
            {"name": "Code Follow", "categ_id": self.category.id}
        )
        self.assertEqual(product.default_code, "Code Panels")

        product.categ_id = self.env["product.category"].create(
            {"name": "Code Other"}
        )

        self.assertEqual(product.default_code, "Code Other")

    def test_a_template_edit_rebuilds_every_variant_reference(self):
        """The product form writes the template, never the variants."""
        self.make_rule([
            {"value_type": "field", "field_path": "categ_id.name", "suffix": "/"},
            {"value_type": "field", "field_path": self.ATTRIBUTE_NAMES,
             "transform": "digits"},
        ])
        template = self.env["product.template"].create({
            "name": "Code Template", "categ_id": self.category.id,
            "attribute_line_ids": [(0, 0, {
                "attribute_id": self.thickness.id,
                "value_ids": [(6, 0, (self.thick_18 | self.thick_25).ids)],
            })],
        })
        variants = template.product_variant_ids
        variants[1].active = False

        template.categ_id = self.env["product.category"].create({"name": "Moved"})

        self.assertEqual(
            sorted(variants.with_context(active_test=False).mapped("default_code")),
            ["Moved/18", "Moved/25"],
        )

    def test_a_template_edit_keeps_a_typed_reference(self):
        self.make_rule([{"value_type": "field", "field_path": "categ_id.name"}])
        template = self.make_product(with_attributes=False)
        template.product_variant_ids.default_code = "TYPED-001"

        template.categ_id = self.env["product.category"].create({"name": "Moved"})

        self.assertEqual(template.product_variant_ids.default_code, "TYPED-001")

    def test_a_template_edit_respects_freezing(self):
        self.freeze_setting(True)
        product = self.used_product()

        product.product_tmpl_id.categ_id = self.env["product.category"].create(
            {"name": "Moved"}
        )

        self.assertEqual(product.default_code, "Code Panels")

    def test_a_blank_reference_is_filled_when_a_watched_field_changes(self):
        """A product made before its rule, or while the switch was off."""
        Config = self.env["ir.config_parameter"].sudo()
        Config.set_bool("bs_generate_product_code.autogenerate", False)
        self.make_rule([{"value_type": "field", "field_path": "categ_id.name"}])
        variant = self.make_product("Code Blank", with_attributes=False).product_variant_ids
        template = self.make_product("Code Blank T", with_attributes=False)
        self.assertFalse(variant.default_code)
        Config.set_bool("bs_generate_product_code.autogenerate", True)
        moved = self.env["product.category"].create({"name": "Moved"})

        variant.categ_id = moved
        template.categ_id = moved

        self.assertEqual(variant.default_code, "Moved")
        self.assertEqual(template.product_variant_ids.default_code, "Moved")

    def test_a_blank_reference_is_filled_even_when_used(self):
        self.freeze_setting(True)
        product = self.used_product()
        product.default_code = False

        self.recategorise(product)

        self.assertEqual(product.default_code, "Moved")

    def test_a_typed_reference_survives_a_change_to_a_watched_field(self):
        """The write hook rewrites what it wrote; a reference a user typed is
        still a decision."""
        self.make_rule([{"value_type": "field", "field_path": "categ_id.name"}])
        product = self.env["product.product"].create(
            {
                "name": "Code Typed",
                "default_code": "TYPED-001",
                "categ_id": self.category.id,
            }
        )

        product.categ_id = self.env["product.category"].create(
            {"name": "Code Other"}
        )

        self.assertEqual(product.default_code, "TYPED-001")

    def test_a_write_to_an_unwatched_field_leaves_the_reference_alone(self):
        self.make_rule([{"value_type": "field", "field_path": "categ_id.name"}])
        product = self.env["product.product"].create(
            {"name": "Code Untouched", "categ_id": self.category.id}
        )
        product.default_code = "MANUAL-001"

        product.write({"barcode": "0000000000017"})

        self.assertEqual(product.default_code, "MANUAL-001")

    def test_nothing_is_rebuilt_while_the_switch_is_off(self):
        self.make_rule([{"value_type": "field", "field_path": "categ_id.name"}])
        product = self.env["product.product"].create(
            {"name": "Code Off", "categ_id": self.category.id}
        )
        self.env["ir.config_parameter"].sudo().set_bool(
            "bs_generate_product_code.autogenerate", False
        )

        product.categ_id = self.env["product.category"].create(
            {"name": "Code Other"}
        )

        self.assertEqual(product.default_code, "Code Panels")

    # -- watched fields --------------------------------------------------

    def test_the_watched_fields_are_read_off_the_rules(self):
        """No module is named in the code: the rules say what to watch."""
        self.make_rule(
            [{"value_type": "field", "field_path": "categ_id.name"}],
            domain="[('type', '=', 'consu')]",
        )

        watched = self.env["product.code.rule"]._watched_fields()

        self.assertIn("categ_id", watched)
        self.assertIn("type", watched)
        self.assertNotIn("barcode", watched)

    def test_a_fixed_text_part_watches_nothing(self):
        # Demo data ships a rule of its own, and this asserts on the whole set.
        self.env["product.code.rule"].search([]).unlink()
        self.make_rule([{"value_type": "text", "text": "STATIC"}])

        self.assertEqual(self.env["product.code.rule"]._watched_fields(), frozenset())

    def test_the_watched_fields_follow_an_edit_to_a_part(self):
        self.env["product.code.rule"].search([]).unlink()
        rule = self.make_rule(
            [{"value_type": "field", "field_path": "categ_id.name"}]
        )

        rule.line_ids.field_path = "barcode"

        watched = self.env["product.code.rule"]._watched_fields()
        self.assertIn("barcode", watched)
        self.assertNotIn("categ_id", watched)

    # -- running number --------------------------------------------------

    def number_rule(self, **number):
        return self.make_rule(
            [
                {"value_type": "text", "text": "RUN"},
                dict({"value_type": "number", "prefix": "-", "length": 3}, **number),
            ],
            domain="[('name', 'like', 'Run ')]",
        )

    def test_a_running_number_keeps_equal_references_apart(self):
        self.number_rule()

        first = self.env["product.product"].create({"name": "Run One"})
        second = self.env["product.product"].create({"name": "Run Two"})

        self.assertEqual(first.default_code, "RUN-001")
        self.assertEqual(second.default_code, "RUN-002")

    def test_products_generated_together_take_different_numbers(self):
        self.number_rule()

        products = self.env["product.product"].create(
            [{"name": f"Run {index}"} for index in range(3)]
        )

        self.assertEqual(
            products.mapped("default_code"), ["RUN-001", "RUN-002", "RUN-003"]
        )

    def test_numbering_counts_per_reference(self):
        self.make_rule(
            [
                {"value_type": "field", "field_path": self.ATTRIBUTE_NAMES,
                 "transform": "digits"},
                {"value_type": "number", "prefix": "-", "length": 2},
            ]
        )
        self.env["product.template"].create({
            "name": "Numbered Panel",
            "attribute_line_ids": [
                (0, 0, {"attribute_id": self.thickness.id,
                        "value_ids": [(6, 0, (self.thick_18 | self.thick_25).ids)]}),
            ],
        })
        other = self.env["product.template"].create({
            "name": "Numbered Panel Two",
            "attribute_line_ids": [
                (0, 0, {"attribute_id": self.thickness.id,
                        "value_ids": [(6, 0, self.thick_18.ids)]}),
            ],
        })

        self.assertEqual(other.product_variant_ids.default_code, "18-02")
        codes = self.env["product.product"].search(
            [("default_code", "=like", "25-%")]
        ).mapped("default_code")
        self.assertEqual(codes, ["25-01"])

    def test_numbering_continues_after_the_highest_number(self):
        self.number_rule()
        self.env["product.product"].create(
            {"name": "Typed", "default_code": "RUN-041"}
        )

        product = self.env["product.product"].create({"name": "Run After"})

        self.assertEqual(product.default_code, "RUN-042")

    def test_numbering_sees_archived_products(self):
        self.number_rule()
        self.env["product.product"].create({"name": "Run Old"}).active = False

        product = self.env["product.product"].create({"name": "Run New"})

        self.assertEqual(product.default_code, "RUN-002")

    def test_numbering_starts_where_the_part_says(self):
        self.number_rule(start_number=500, length=4)

        product = self.env["product.product"].create({"name": "Run Start"})

        self.assertEqual(product.default_code, "RUN-0500")

    def test_regenerating_keeps_a_product_its_number(self):
        self.number_rule()
        first, second = self.env["product.product"].create(
            [{"name": "Run A"}, {"name": "Run B"}]
        )

        changed = (first | second).action_generate_default_code()

        self.assertEqual(changed["params"]["type"], "warning")
        self.assertEqual(
            (first | second).mapped("default_code"), ["RUN-001", "RUN-002"]
        )

    def test_a_numbered_reference_follows_a_watched_field(self):
        self.make_rule(
            [
                {"value_type": "field", "field_path": "categ_id.name",
                 "transform": "truncate", "length": 4},
                {"value_type": "number", "prefix": "-", "length": 3},
            ]
        )
        product = self.make_product(with_attributes=False).product_variant_ids
        self.assertEqual(product.default_code, "Code-001")

        product.categ_id = self.env["product.category"].create({"name": "Wood"})

        self.assertEqual(product.default_code, "Wood-001")

    def test_a_like_wildcard_in_the_reference_is_literal(self):
        self.make_rule(
            [
                {"value_type": "text", "text": "A_"},
                {"value_type": "number", "length": 1},
            ],
            domain="[('name', 'like', 'Wild')]",
        )
        self.env["product.product"].create(
            {"name": "Other", "default_code": "AB9"}
        )

        product = self.env["product.product"].create({"name": "Wild"})

        self.assertEqual(product.default_code, "A_1")

    def test_a_rule_takes_one_running_number(self):
        with self.assertRaises(ValidationError):
            self.make_rule(
                [{"value_type": "number"}, {"value_type": "number"}]
            )

    def test_a_running_number_needs_a_length(self):
        with self.assertRaises(ValidationError):
            self.make_rule([{"value_type": "number", "length": 0}])

    def test_a_running_number_watches_nothing(self):
        self.env["product.code.rule"].search([]).unlink()
        self.make_rule([{"value_type": "number"}])

        self.assertEqual(self.env["product.code.rule"]._watched_fields(), frozenset())

    def test_a_number_cannot_run_into_a_varying_digit(self):
        """DEM-18 + 001 would read as DEM-180 + 01."""
        with self.assertRaises(ValidationError):
            self.make_rule(
                [
                    {"value_type": "field", "field_path": "product_tmpl_id.name"},
                    {"value_type": "number", "length": 3},
                ]
            )

    def test_a_prefix_ending_in_a_digit_does_not_separate(self):
        with self.assertRaises(ValidationError):
            self.make_rule(
                [
                    {"value_type": "field", "field_path": "product_tmpl_id.name"},
                    {"value_type": "number", "prefix": "-1"},
                ]
            )

    def test_a_number_cannot_run_into_a_varying_digit_after_it(self):
        with self.assertRaises(ValidationError):
            self.make_rule(
                [
                    {"value_type": "number", "length": 3},
                    {"value_type": "field", "field_path": "product_tmpl_id.name"},
                ]
            )

    def test_fixed_text_around_a_number_needs_no_separator(self):
        rule = self.make_rule(
            [
                {"value_type": "text", "text": "P7"},
                {"value_type": "number", "length": 3},
                {"value_type": "text", "text": "9"},
            ],
            domain="[('name', 'like', 'Fixed ')]",
        )

        product = self.env["product.product"].create({"name": "Fixed One"})

        self.assertEqual(product.default_code, "P70019")
        self.assertTrue(rule)

    def test_a_suffix_separates_a_number_from_a_field_after_it(self):
        self.make_rule(
            [
                {"value_type": "number", "length": 3, "suffix": "/"},
                {"value_type": "field", "field_path": "product_tmpl_id.name"},
            ],
            domain="[('name', 'like', 'Tail ')]",
        )

        product = self.env["product.product"].create({"name": "Tail 5"})

        self.assertEqual(product.default_code, "001/Tail 5")

    def test_removing_the_separating_part_is_refused(self):
        rule = self.make_rule(
            [
                {"value_type": "field", "field_path": "product_tmpl_id.name"},
                {"value_type": "text", "text": "-"},
                {"value_type": "number", "length": 3},
            ]
        )
        separator = rule.line_ids.filtered(lambda line: line.value_type == "text")

        with self.assertRaises(ValidationError):
            rule.write({"line_ids": [(2, separator.id)]})

    def test_sequences_of_references_sharing_a_start_stay_apart(self):
        self.make_rule(
            [
                {"value_type": "field", "field_path": "product_tmpl_id.name"},
                {"value_type": "number", "prefix": "-", "length": 3},
            ],
            domain="[('name', '=like', 'X18%')]",
        )
        Product = self.env["product.product"]

        self.assertEqual(Product.create({"name": "X18"}).default_code, "X18-001")
        self.assertEqual(Product.create({"name": "X180"}).default_code, "X180-001")
        self.assertEqual(Product.create({"name": "X18"}).default_code, "X18-002")

    # -- duplicates ------------------------------------------------------

    def test_the_duplicate_filter_finds_products_sharing_a_reference(self):
        Product = self.env["product.product"]
        first, second = Product.create(
            [{"name": "Dup A", "default_code": "DUP-1"},
             {"name": "Dup B", "default_code": "DUP-1"}]
        )
        single = Product.create({"name": "Dup C", "default_code": "DUP-2"})

        found = Product.search([("has_duplicate_code", "=", True)])

        self.assertIn(first, found)
        self.assertIn(second, found)
        self.assertNotIn(single, found)
        self.assertTrue(first.has_duplicate_code)
        self.assertFalse(single.has_duplicate_code)

    def test_an_archived_product_still_counts_as_a_duplicate(self):
        Product = self.env["product.product"]
        old = Product.create({"name": "Dup Old", "default_code": "DUP-9"})
        new = Product.create({"name": "Dup New", "default_code": "DUP-9"})
        old.active = False

        self.assertTrue(new.has_duplicate_code)

    def test_the_duplicate_filter_works_on_templates(self):
        Template = self.env["product.template"]
        first = Template.create({"name": "Dup T1", "default_code": "DUP-T"})
        Template.create({"name": "Dup T2", "default_code": "DUP-T"})
        other = Template.create({"name": "Dup T3", "default_code": "DUP-U"})

        found = Template.search([("has_duplicate_code", "=", True)])

        self.assertIn(first, found)
        self.assertNotIn(other, found)
        self.assertTrue(first.has_duplicate_code)

    # -- freezing --------------------------------------------------------

    def freeze_setting(self, value):
        self.env["ir.config_parameter"].sudo().set_bool(
            "bs_generate_product_code.freeze_used", value
        )

    def used_product(self, **rule):
        self.make_rule(
            [{"value_type": "field", "field_path": "categ_id.name"}], **rule
        )
        product = self.make_product(with_attributes=False).product_variant_ids
        self.env["stock.move"].create({
            "product_id": product.id,
            "product_uom_qty": 1,
            "location_id": self.env.ref("stock.stock_location_stock").id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
        })
        return product

    def recategorise(self, product):
        product.categ_id = self.env["product.category"].create({"name": "Moved"})

    def test_the_setting_freezes_a_used_reference(self):
        self.freeze_setting(True)
        product = self.used_product()

        self.recategorise(product)

        self.assertEqual(product.default_code, "Code Panels")

    def test_an_unused_reference_still_follows_its_fields(self):
        self.freeze_setting(True)
        self.make_rule([{"value_type": "field", "field_path": "categ_id.name"}])
        product = self.make_product(with_attributes=False).product_variant_ids

        self.recategorise(product)

        self.assertEqual(product.default_code, "Moved")

    def test_without_freezing_a_used_reference_follows_its_fields(self):
        self.freeze_setting(False)
        product = self.used_product()

        self.recategorise(product)

        self.assertEqual(product.default_code, "Moved")

    def test_a_rule_can_freeze_without_the_setting(self):
        self.freeze_setting(False)
        product = self.used_product()
        self.env["product.code.rule"].search([]).freeze_policy = "used"

        self.recategorise(product)

        self.assertEqual(product.default_code, "Code Panels")

    def test_a_rule_can_keep_following_despite_the_setting(self):
        self.freeze_setting(True)
        product = self.used_product()
        self.env["product.code.rule"].search([]).freeze_policy = "never"

        self.recategorise(product)

        self.assertEqual(product.default_code, "Moved")

    def test_the_manual_action_still_updates_a_frozen_reference(self):
        self.freeze_setting(True)
        product = self.used_product()
        self.recategorise(product)

        product.action_generate_default_code()

        self.assertEqual(product.default_code, "Moved")

    # -- preview ---------------------------------------------------------

    def preview(self, products):
        action = products.action_preview_default_code()
        return self.env["product.code.preview"].browse(action["res_id"])

    def test_the_preview_writes_nothing(self):
        Product = self.env["product.product"]
        stale = Product.create({"name": "Prev Stale", "default_code": "OLD"})
        self.make_rule([{"value_type": "text", "text": "NEW"}],
                       domain="[('name', 'like', 'Prev ')]")

        wizard = self.preview(stale)

        self.assertEqual(stale.default_code, "OLD")
        self.assertEqual(wizard.line_ids.new_code, "NEW")
        self.assertEqual(wizard.line_ids.state, "change")

    def test_the_preview_sorts_products_by_what_happens_to_them(self):
        Product = self.env["product.product"]
        stale = Product.create({"name": "Prev Stale", "default_code": "OLD"})
        current = Product.create({"name": "Prev Current", "default_code": "NEW"})
        unmatched = Product.create({"name": "Elsewhere", "default_code": "KEEP"})
        self.make_rule([{"value_type": "text", "text": "NEW"}],
                       domain="[('name', 'like', 'Prev ')]")

        wizard = self.preview(stale | current | unmatched)

        states = {line.product_id: line.state for line in wizard.line_ids}
        self.assertEqual(states, {stale: "change", current: "same", unmatched: "skip"})
        self.assertEqual(
            (wizard.change_count, wizard.same_count, wizard.skip_count), (1, 1, 1)
        )
        self.assertFalse(wizard.line_ids.filtered(lambda l: l.state != "change").mapped("selected")[0])

    def test_applying_changes_only_the_ticked_products(self):
        Product = self.env["product.product"]
        first, second = Product.create(
            [{"name": "Prev A", "default_code": "A"}, {"name": "Prev B", "default_code": "B"}]
        )
        self.make_rule([{"value_type": "field", "field_path": "product_tmpl_id.name",
                         "transform": "upper"}],
                       domain="[('name', 'like', 'Prev ')]")
        wizard = self.preview(first | second)
        wizard.line_ids.filtered(lambda line: line.product_id == first).selected = True
        wizard.line_ids.filtered(lambda line: line.product_id == second).selected = False

        wizard.action_apply()

        self.assertEqual(first.default_code, "PREV A")
        self.assertEqual(second.default_code, "B")

    def test_the_preview_unticks_a_used_product_its_rule_freezes(self):
        self.freeze_setting(True)
        product = self.used_product()
        self.recategorise(product)

        line = self.preview(product).line_ids

        self.assertEqual((line.state, line.is_used, line.selected), ("change", True, False))
        self.assertEqual(line.wizard_id.used_count, 1)

    def test_the_preview_ticks_a_used_product_its_rule_keeps_following(self):
        self.freeze_setting(False)
        product = self.used_product()
        self.env["ir.config_parameter"].sudo().set_bool(
            "bs_generate_product_code.autogenerate", False
        )
        self.recategorise(product)

        line = self.preview(product).line_ids

        self.assertEqual((line.state, line.is_used, line.selected), ("change", True, True))

    def test_the_preview_unticks_a_typed_reference(self):
        """A reference no rule built is someone's decision, as product 37's
        FURN_6666 was: replacing it must be chosen line by line."""
        typed = self.env["product.product"].create(
            {"name": "Prev Typed", "default_code": "FURN_6666"}
        )
        self.make_rule([{"value_type": "text", "text": "NEW"}],
                       domain="[('name', 'like', 'Prev ')]")

        wizard = self.preview(typed)

        line = wizard.line_ids
        self.assertEqual((line.state, line.is_typed, line.selected), ("change", True, False))
        self.assertEqual(wizard.typed_count, 1)

    def test_the_preview_ticks_a_stale_generated_reference(self):
        self.env["ir.config_parameter"].sudo().set_bool(
            "bs_generate_product_code.autogenerate", False
        )
        self.make_rule([{"value_type": "field", "field_path": "categ_id.name"}])
        product = self.make_product(with_attributes=False).product_variant_ids
        product.action_generate_default_code()
        self.recategorise(product)

        line = self.preview(product).line_ids

        self.assertEqual(
            (line.current_code, line.new_code, line.is_typed, line.selected),
            ("Code Panels", "Moved", False, True),
        )

    def test_the_template_action_previews_every_variant(self):
        self.make_rule([{"value_type": "field", "field_path": self.ATTRIBUTE_NAMES,
                         "transform": "digits"}])
        self.env["ir.config_parameter"].sudo().set_bool(
            "bs_generate_product_code.autogenerate", False
        )
        template = self.env["product.template"].create({
            "name": "Code Template", "categ_id": self.category.id,
            "attribute_line_ids": [(0, 0, {
                "attribute_id": self.thickness.id,
                "value_ids": [(6, 0, (self.thick_18 | self.thick_25).ids)],
            })],
        })

        action = template.action_preview_default_code()

        wizard = self.env["product.code.preview"].browse(action["res_id"])
        self.assertEqual(sorted(wizard.line_ids.mapped("new_code")), ["18", "25"])

    def test_the_preview_flags_a_reference_that_would_be_duplicated(self):
        Product = self.env["product.product"]
        Product.create({"name": "Holder", "default_code": "SAME"})
        first, second = Product.create([{"name": "Prev A"}, {"name": "Prev B"}])
        self.make_rule([{"value_type": "text", "text": "SAME"}],
                       domain="[('name', 'like', 'Prev ')]")

        wizard = self.preview(first | second)

        self.assertEqual(wizard.duplicate_count, 2)

    def test_the_preview_numbers_products_in_turn(self):
        Product = self.env["product.product"]
        products = Product.create([{"name": "Prev A"}, {"name": "Prev B"}])
        self.make_rule(
            [{"value_type": "text", "text": "PV"},
             {"value_type": "number", "prefix": "-", "length": 3}],
            domain="[('name', 'like', 'Prev ')]",
        )

        wizard = self.preview(products)

        self.assertEqual(
            sorted(wizard.line_ids.mapped("new_code")), ["PV-001", "PV-002"]
        )
        self.assertFalse(wizard.duplicate_count)
        self.assertFalse(any(products.mapped("default_code")))

    # -- history ---------------------------------------------------------

    def test_every_generated_reference_is_recorded(self):
        rule = self.make_rule([{"value_type": "field", "field_path": "categ_id.name"}])
        product = self.make_product(with_attributes=False).product_variant_ids
        self.recategorise(product)

        History = self.env["product.code.history"]
        rows = History.search([("product_id", "=", product.id)], order="id")
        self.assertEqual(
            [(row.old_code, row.new_code, row.rule_id) for row in rows],
            [(False, "Code Panels", rule), ("Code Panels", "Moved", rule)],
        )

    def test_a_typed_reference_is_not_recorded(self):
        self.make_rule([{"value_type": "field", "field_path": "categ_id.name"}])
        product = self.env["product.product"].create(
            {"name": "Typed", "default_code": "TYPED-1", "categ_id": self.category.id}
        )
        self.assertFalse(
            self.env["product.code.history"].search([("product_id", "=", product.id)])
        )

    def test_the_migration_records_references_earlier_versions_built(self):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).parents[1] / "migrations" / "20.0.1.1.0" / "post-migrate.py"
        spec = importlib.util.spec_from_file_location("pcode_post_migrate", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        self.make_rule([{"value_type": "field", "field_path": "categ_id.name"}])
        built = self.make_product("Built", with_attributes=False).product_variant_ids
        typed = self.env["product.product"].create(
            {"name": "Typed", "default_code": "TYPED-1", "categ_id": self.category.id}
        )
        History = self.env["product.code.history"].sudo()
        History.search([]).unlink()

        migration.migrate(self.env.cr, "20.0.1.0.0")

        recorded = History.search([]).mapped(lambda row: (row.product_id, row.new_code))
        self.assertIn((built, "Code Panels"), recorded)
        self.assertNotIn((typed, "TYPED-1"), recorded)

    # -- date placeholders -----------------------------------------------

    def created_on(self, product, moment):
        self.env.cr.execute(
            "UPDATE product_product SET create_date = %s WHERE id = %s",
            [moment, product.id],
        )
        product.invalidate_recordset(["create_date"])

    def unnumbered(self, *names):
        """Products without a reference yet, so their dates can be set first."""
        self.env["ir.config_parameter"].sudo().set_bool(
            "bs_generate_product_code.autogenerate", False
        )
        return self.env["product.product"].create([{"name": name} for name in names])

    def test_every_date_placeholder_reads_the_creation_date(self):
        self.env.user.sudo().tz = "UTC"
        product = self.unnumbered("Dated")
        self.created_on(product, "2024-03-05 07:08:09")
        line = self.make_rule([{"value_type": "text", "text": "X"}]).line_ids
        expected = {
            "year": "2024", "y": "24", "month": "03", "day": "05", "doy": "065",
            "woy": "10", "weekday": "2", "h24": "07", "h12": "07", "min": "08",
            "sec": "09", "isoyear": "2024", "isoy": "24", "isoweek": "10",
        }
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(line._interpolate(f"%({key})s", product), value)

    def test_placeholders_fill_prefix_suffix_and_text(self):
        product = self.unnumbered("Dated")
        self.created_on(product, "2024-03-05 07:00:00")
        self.make_rule([
            {"value_type": "text", "text": "T%(y)s", "prefix": "P%(year)s-",
             "suffix": "-%(month)s", "transform": "lower"},
        ])

        product.action_generate_default_code()

        self.assertEqual(product.default_code, "P2024-t24-03")

    def test_the_date_follows_the_creator_time_zone(self):
        self.env.user.sudo().tz = "Asia/Yangon"
        product = self.unnumbered("Dated")
        # 20:00 UTC is 02:30 the next day in Yangon.
        self.created_on(product, "2024-12-31 20:00:00")
        self.make_rule([{"value_type": "text", "text": "%(year)s%(month)s%(day)s"}])

        product.with_context(tz="UTC").action_generate_default_code()

        self.assertEqual(product.default_code, "20250101")

    def test_a_lone_percent_sign_stays_as_typed(self):
        self.make_rule([{"value_type": "text", "text": "50%", "suffix": "%s"}])
        self.assertEqual(
            self.env["product.product"].create({"name": "Pct"}).default_code, "50%%s"
        )

    def test_an_unknown_placeholder_is_refused(self):
        with self.assertRaises(ValidationError):
            self.make_rule([{"value_type": "text", "text": "%(yeer)s"}])

    def test_numbering_starts_again_for_each_year(self):
        first, second, later = self.unnumbered("Y1", "Y2", "Y3")
        self.created_on(first, "2025-02-01 00:00:00")
        self.created_on(second, "2025-11-01 00:00:00")
        self.created_on(later, "2026-01-15 00:00:00")
        self.make_rule([
            {"value_type": "text", "text": "P%(year)s"},
            {"value_type": "number", "prefix": "-", "length": 3},
        ])

        (first | second | later).action_generate_default_code()

        self.assertEqual(
            (first | second | later).mapped("default_code"),
            ["P2025-001", "P2025-002", "P2026-001"],
        )

    def test_a_number_cannot_run_into_a_date(self):
        refused = [
            [{"value_type": "text", "text": "P%(y)s"},
             {"value_type": "number", "length": 3}],
            [{"value_type": "text", "text": "P"},
             {"value_type": "number", "prefix": "-%(y)s", "length": 3}],
            [{"value_type": "number", "suffix": "%(y)s", "length": 3}],
        ]
        for lines in refused:
            with self.subTest(lines=lines), self.assertRaises(ValidationError):
                self.make_rule(lines)
        self.make_rule([
            {"value_type": "text", "text": "P%(y)s-"},
            {"value_type": "number", "length": 3},
        ])

    def test_a_dated_reference_stays_the_same_when_regenerated(self):
        product = self.unnumbered("Dated")
        self.created_on(product, "2020-06-01 00:00:00")
        self.make_rule([
            {"value_type": "text", "text": "P%(year)s"},
            {"value_type": "number", "prefix": "-", "length": 3},
        ])
        product.action_generate_default_code()

        self.assertEqual(self.preview(product).line_ids.state, "same")
        self.assertEqual(product.default_code, "P2020-001")

    # -- import ----------------------------------------------------------

    def test_an_import_test_run_leaves_nothing_behind(self):
        """The import dialog's Test button creates inside a savepoint it rolls
        back: no product, and no running number, may survive it."""
        if "base_import.import" not in self.env:
            self.skipTest("base_import is not installed")
        self.make_rule(
            [{"value_type": "text", "text": "IMP"},
             {"value_type": "number", "prefix": "-", "length": 3}],
            domain="[('name', 'like', 'Imported ')]",
        )
        Product = self.env["product.product"].with_context(active_test=False)
        before = Product.search_count([])
        wizard = self.env["base_import.import"].create({
            "res_model": "product.product",
            "file": BinaryBytes(b"name\nImported One\nImported Two\n", "products.csv"),
            "file_type": "text/csv",
        })

        result = wizard.execute_import(
            ["name"], ["name"],
            {"has_headers": True, "separator": ",", "quoting": '"',
             "encoding": "utf-8", "import_skip_records": [],
             "import_set_empty_fields": [], "name_create_enabled_fields": {}},
            dryrun=True,
        )

        self.assertFalse(
            [m for m in result["messages"] if m.get("type") == "error"], result
        )
        self.assertEqual(len(result["ids"]), 2)
        self.assertEqual(Product.search_count([]), before)
        self.assertEqual(
            self.env["product.product"].create({"name": "Imported Later"}).default_code,
            "IMP-001",
        )
