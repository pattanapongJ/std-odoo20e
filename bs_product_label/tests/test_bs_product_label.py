# -*- coding: utf-8 -*-

import io
from contextlib import nullcontext
from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools.pdf import PdfReader

from odoo.addons.base.tests.common import BaseCommon


@tagged("post_install", "-at_install")
class TestBsProductLabel(BaseCommon):
    _test_user_groups = ("base.group_user", "product.group_product_manager")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Profile = cls.env["bs.label.profile"]
        cls.roll = cls.Profile.create({
            "name": "Test roll 2-up",
            "media": "roll",
            "label_width_mm": 50,
            "label_height_mm": 30,
            "columns": 2,
            "gap_x_mm": 1.6,
        })
        cls.sheet = cls.Profile.create({
            "name": "Test sheet",
            "media": "sheet",
            "label_width_mm": 70,
            "label_height_mm": 37,
            "columns": 3,
            "rows": 8,
        })
        cls.product = cls.env["product.product"].create({
            "name": "Label Chair",
            "default_code": "LBL-001",
            "barcode": "4006381333931",
            "list_price": 120.0,
        })

    def line(self, product=None, quantity=1, **extra):
        return dict({"product_id": (product or self.product).id, "quantity": quantity}, **extra)

    def render(self, profile, lines, output, test=False):
        profile.output = output
        # force_report_rendering: in tests Odoo returns the HTML instead of a PDF.
        report = profile._get_report().with_context(
            bs_label_profile_id=profile.id, force_report_rendering=True
        )
        data = {"profile_id": profile.id, "pricelist_id": False, "lines": lines, "test": test}
        method = {
            "pdf": report._render_qweb_pdf,
            "html": report._render_qweb_html,
            "zpl": report._render_qweb_text,
        }[output]
        with self.allow_pdf_render() if output == "pdf" else nullcontext():
            content, _type = method(report.report_name, None, data=data)
        return content

    # -- layout ---------------------------------------------------------

    def test_a_roll_page_is_one_row_rounded_up_to_whole_mm(self):
        layout = self.roll._layout()

        self.assertAlmostEqual(layout["page_width"], 101.6)
        self.assertEqual(layout["per_page"], 2)
        self.assertEqual((layout["paper_width"], layout["paper_height"]), (102, 30))
        self.assertEqual(self.roll.driver_page_size, "102 x 30 mm")

    def test_a_sheet_page_holds_rows_and_columns(self):
        self.assertEqual(self.sheet.labels_per_page, 24)
        self.assertEqual(self.sheet.driver_page_size, "210 x 297 mm")

    def test_labels_that_do_not_fit_the_sheet_are_refused(self):
        with self.assertRaises(ValidationError):
            self.sheet.rows = 9

    def test_pages_fill_rows_then_leave_empty_cells(self):
        pages = self.roll._paginate([{"n": 1}, {"n": 2}, {"n": 3}])

        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[1], [[{"n": 3}, None]])

    # -- paperformat ----------------------------------------------------

    def test_each_profile_owns_its_paperformat(self):
        paperformat = self.roll.paperformat_id

        self.assertEqual((paperformat.format, paperformat.page_width, paperformat.page_height),
                         ("custom", 102, 30))
        self.assertNotEqual(paperformat, self.sheet.paperformat_id)

    def test_the_paperformat_follows_the_profile(self):
        self.roll.label_height_mm = 40

        self.assertEqual(self.roll.paperformat_id.page_height, 40)

    def test_the_report_takes_the_printed_profiles_page(self):
        report = self.roll._get_report()

        paperformat = report.with_context(bs_label_profile_id=self.roll.id).get_paperformat()

        self.assertEqual(paperformat.page_width, 102)
        self.assertNotEqual(report.get_paperformat().page_width, 102)

    def test_paper_muncher_gets_its_own_dpi_without_a_write(self):
        report = self.roll._get_report().with_context(bs_label_profile_id=self.roll.id)
        with patch.object(type(report), "_get_pdf_engine", return_value="paper-muncher"):
            paperformat = report.get_paperformat()

        self.assertEqual(paperformat.dpi, 76)
        self.assertFalse(paperformat.id)
        self.assertEqual(self.roll.paperformat_id.dpi, 96)

    def test_printing_writes_no_paperformat(self):
        before = self.roll.paperformat_id.write_date
        with patch.object(type(self.env["report.paperformat"]), "write") as write:
            self.render(self.roll, [self.line()], "html")

        write.assert_not_called()
        self.assertEqual(self.roll.paperformat_id.write_date, before)

    # -- content --------------------------------------------------------

    def test_label_values_follow_the_profile(self):
        values = self.roll._prepare_label_values(self.line(extra_text="Aisle 4"))

        self.assertEqual(values["code"], "LBL-001")
        self.assertEqual(values["name"], "Label Chair")
        self.assertEqual(values["extra_text"], "Aisle 4")
        self.assertEqual(values["price"], "")
        self.assertTrue(values["barcode_src"].startswith("data:image/png;base64,"))

    def test_hidden_parts_are_left_out(self):
        self.roll.write({"show_code": False, "barcode_source": "none"})

        values = self.roll._prepare_label_values(self.line())

        self.assertEqual(values["code"], "")
        self.assertEqual(values["barcode_src"], "")

    def test_the_price_comes_from_the_pricelist(self):
        pricelist = self.env["product.pricelist"].create({
            "name": "Label promo",
            "item_ids": [(0, 0, {
                "applied_on": "0_product_variant",
                "product_id": self.product.id,
                "compute_price": "fixed",
                "fixed_price": 99.0,
            })],
        })
        self.roll.show_price = True

        with_list = self.roll._prepare_label_values(self.line())["price"]
        with_pricelist = self.roll._prepare_label_values(self.line(), pricelist)["price"]

        self.assertIn("120", with_list)
        self.assertIn("99", with_pricelist)

    def test_an_invalid_ean_still_prints_a_barcode(self):
        """Odoo turns a value that is not EAN-13 into Code 128."""
        self.roll.barcode_type = "EAN13"
        self.product.barcode = "NOT-AN-EAN"

        values = self.roll._prepare_label_values(self.line())

        self.assertTrue(values["barcode_src"])

    def test_lines_that_do_not_fit_are_left_out_whole(self):
        """A small label with a barcode keeps the name and drops lines
        rather than printing one cut in half."""
        self.roll.write({
            "label_width_mm": 38, "label_height_mm": 20, "barcode_type": "Code128",
            "show_price": True, "custom_text": "Shop",
        })

        values = self.roll._fit_label(
            self.roll._prepare_label_values(self.line(extra_text="Aisle 4"))
        )

        self.assertEqual(values["name_lines"], 1)
        self.assertLess(len(values["lines"]), 3)

    def test_a_roomy_label_keeps_every_line_in_order(self):
        self.roll.custom_text = "Shop"

        values = self.roll._fit_label(
            self.roll._prepare_label_values(self.line(extra_text="Aisle 4"))
        )

        self.assertEqual([line["text"] for line in values["lines"]], ["LBL-001", "Aisle 4", "Shop"])

    def test_quantities_expand_into_labels(self):
        labels = self.roll._expand_lines([self.line(quantity=3), self.line(quantity=0)])

        self.assertEqual(len(labels), 3)

    def test_a_runaway_quantity_is_refused(self):
        with self.assertRaises(UserError):
            self.roll._expand_lines([self.line(quantity=5001)])

    # -- outputs --------------------------------------------------------

    def test_html_output_shows_the_label(self):
        html = self.render(self.roll, [self.line(quantity=3)], "html").decode()

        self.assertEqual(html.count("LBL-001"), 3)

    def test_zpl_output_has_a_label_per_row(self):
        zpl = self.render(self.roll, [self.line(quantity=3)], "zpl").decode()

        self.assertEqual(zpl.count("^XA"), 2)
        self.assertIn("^FDLBL-001^FS", zpl)
        self.assertIn("^BQN", zpl)

    def test_zpl_linear_barcode(self):
        self.roll.barcode_type = "EAN13"

        zpl = self.render(self.roll, [self.line()], "zpl").decode()

        self.assertIn("^BEN", zpl)

    def test_pdf_output_has_the_profiles_page_size(self):
        engine = self.env["ir.actions.report"]._get_pdf_engine(self.roll._get_report())
        if self.env["ir.actions.report"].get_pdf_engine_state(engine) != "ok":
            self.skipTest("no working PDF engine")

        pdf = self.render(self.roll, [self.line(quantity=3)], "pdf")

        pages = PdfReader(io.BytesIO(pdf)).pages
        self.assertEqual(len(pages), 2)
        width_mm = float(pages[0].mediabox.width) / 72 * 25.4
        height_mm = float(pages[0].mediabox.height) / 72 * 25.4
        self.assertAlmostEqual(width_mm, 102, delta=0.5)
        self.assertAlmostEqual(height_mm, 30, delta=0.5)

    def test_report_table_styles_are_reset(self):
        """The company's document layout borders report tables."""
        html = self.render(self.roll, [self.line()], "html").decode()

        self.assertIn(".o_bs_label_pages table, .o_bs_label_pages tbody, .o_bs_label_pages tr, .o_bs_label_pages td", html)
        self.assertIn("border: 0 none !important", html)

    def test_the_test_page_fills_one_page(self):
        html = self.render(self.sheet, [], "html", test=True).decode()

        self.assertEqual(html.count('class="o_bs_label"'), 24)

    # -- print dialog ---------------------------------------------------

    def test_the_dialog_opens_with_a_line_per_variant(self):
        action = self.env["bs.label.print.wizard"]._action_open(self.product.product_tmpl_id)
        wizard = self.env["bs.label.print.wizard"].browse(action["res_id"])

        self.assertEqual(wizard.line_ids.product_id, self.product)
        self.assertTrue(wizard.profile_id)

    def test_the_dialog_previews_and_counts(self):
        wizard = self.env["bs.label.print.wizard"].create({
            "profile_id": self.roll.id,
            "line_ids": [(0, 0, {"product_id": self.product.id, "quantity": 3})],
        })

        self.assertEqual((wizard.label_count, wizard.page_count), (3, 2))
        self.assertIn("LBL-001", wizard.preview_html)

    def test_printing_remembers_the_profile(self):
        wizard = self.env["bs.label.print.wizard"].create({
            "profile_id": self.sheet.id,
            "line_ids": [(0, 0, {"product_id": self.product.id, "quantity": 1})],
        })

        action = wizard.action_print()

        self.assertEqual(action["context"]["bs_label_profile_id"], self.sheet.id)
        self.assertEqual(self.env["bs.label.print.wizard"].default_get(["profile_id"])["profile_id"],
                         self.sheet.id)

    def test_a_model_without_a_source_is_refused(self):
        with self.assertRaises(UserError):
            self.env["bs.label.print.wizard"]._action_open(self.env.user.partner_id)

    def test_only_managers_edit_profiles(self):
        user = self.env["res.users"].sudo().create({
            "name": "Label clerk", "login": "label_clerk",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        profile = self.roll.with_user(user)

        self.assertTrue(profile.name)
        with self.assertRaises(Exception):
            profile.name = "Mine"

    def test_zpl_preserves_special_characters_without_commands_or_entities(self):
        import re
        value = 'A&B<"\'_^XZ~JA'
        self.product.barcode = value
        zpl = self.render(self.roll, [self.line()], "zpl").decode()
        self.assertNotIn('&amp;', zpl)
        self.assertEqual(zpl.count('^XZ'), 1)
        self.assertNotIn('~JA', zpl)
        encoded = re.search(r'\^FH\^FDLA,(.*?)\^FS', zpl).group(1)
        decoded = re.sub(r'_([0-9A-F]{2})', lambda m: chr(int(m[1], 16)), encoded)
        self.assertEqual(decoded, value)

    def test_ean_validation_is_identical_in_all_outputs(self):
        self.roll.barcode_type = "EAN13"
        for value, expected in (
            ("4006381333931", "EAN13"),
            ("4006381333932", "Code128"),
            ("400638133393", "Code128"),
            ("ABC-123", "Code128"),
        ):
            with self.subTest(value=value):
                self.product.barcode = value
                values = self.roll._prepare_label_values(self.line())
                self.assertEqual(values["barcode_type"], expected)
                zpl = self.render(self.roll, [self.line()], "zpl").decode()
                self.assertIn("^BEN" if expected == "EAN13" else "^BCN", zpl)

    def test_preview_allocation_is_bounded_by_page_size(self):
        import tracemalloc
        # Warm the renderer before measuring the expansion branch alone.
        self.roll._render_values([self.line()], limit=2)
        with patch.object(type(self.roll), "_prepare_label_values", return_value={}), \
             patch.object(type(self.roll), "_fit_label", return_value={"line_height": 1.15}):
            already_tracing = tracemalloc.is_tracing()
            if not already_tracing:
                tracemalloc.start()
            try:
                before = tracemalloc.get_traced_memory()[0]
                tracemalloc.reset_peak()
                values = self.roll._render_values([self.line(quantity=100000)], limit=2)
                peak = tracemalloc.get_traced_memory()[1] - before
            finally:
                if not already_tracing:
                    tracemalloc.stop()
        self.assertEqual(len(values["pages"]), 1)
        self.assertLess(peak, 1000000)

    def test_clearing_pricelist_uses_sales_price_in_preview_and_report(self):
        pricelist = self.env["product.pricelist"].create({
            "name": "Profile promo", "item_ids": [(0, 0, {
                "applied_on": "0_product_variant", "product_id": self.product.id,
                "compute_price": "fixed", "fixed_price": 99,
            })],
        })
        self.roll.write({"show_price": True, "pricelist_id": pricelist.id})
        wizard = self.env["bs.label.print.wizard"].create({
            "profile_id": self.roll.id,
            "line_ids": [(0, 0, {"product_id": self.product.id, "quantity": 1})],
        })
        wizard._onchange_profile_id()
        self.assertIn("99", wizard.preview_html)
        wizard.pricelist_id = False
        self.assertIn("120", wizard.preview_html)
        action = wizard.action_print()
        self.assertFalse(action["data"]["pricelist_id"])
        values = self.env["report.bs_product_label.label_document"]._get_report_values(
            [], action["data"]
        )
        self.assertIn("120", values["pages"][0][0][0]["price"])
        self.assertIn("99", self.roll._prepare_label_values(self.line())["price"])

    def test_profile_defaults_survive_company_switch_and_archival(self):
        company_a = self.env.company
        company_b = self.env["res.company"].sudo().create({"name": "Label Company B"})
        user = self.env["res.users"].sudo().create({
            "name": "Multi company label clerk", "login": "label_multi_company",
            "company_id": company_a.id,
            "company_ids": [(6, 0, [company_a.id, company_b.id])],
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        self.roll.company_id = company_a
        Wizard = self.env["bs.label.print.wizard"].with_user(user)
        Defaults = self.env["ir.default"].with_user(user)
        # A legacy default, saved without a company, must be safely ignored.
        Defaults.set(Wizard._name, "profile_id", self.roll.id, user_id=user.id)
        wizard_b = Wizard.with_context(allowed_company_ids=[company_b.id])
        profile_id = wizard_b.default_get(["profile_id"])["profile_id"]
        self.assertNotEqual(profile_id, self.roll.id)
        action = wizard_b.action_open_blank()
        self.assertTrue(wizard_b.browse(action["res_id"]).profile_id.name)
        wizard_a = Wizard.with_context(allowed_company_ids=[company_a.id]).create({
            "profile_id": self.roll.id,
            "line_ids": [(0, 0, {"product_id": self.product.id, "quantity": 1})],
        })
        wizard_a.action_print()
        self.assertEqual(Defaults._get(
            Wizard._name, "profile_id", user_id=user.id, company_id=company_a.id
        ), self.roll.id)
        self.roll.active = False
        defaults = Wizard.with_context(allowed_company_ids=[company_a.id]).default_get(["profile_id"])
        self.assertNotEqual(defaults["profile_id"], self.roll.id)

    def test_myanmar_and_thai_html_preview_and_zpl_message(self):
        for name, note in (
            ("မြန်မာ လက်ဖက်ခြောက်", "ရန်ကုန်ဆိုင်"),
            ("ชาเขียวไทย", "สาขากรุงเทพ"),
        ):
            with self.subTest(name=name):
                self.product.name = name
                self.roll.write({"label_width_mm": 70, "label_height_mm": 50})
                line = self.line(extra_text=note)
                html = self.render(self.roll, [line], "html").decode()
                preview = str(self.roll._render_preview([line]))
                for rendered in (html, preview):
                    self.assertIn(name, rendered)
                    self.assertIn(note, rendered)
                    self.assertIn("data:font/ttf;base64,", rendered)
                    self.assertIn("line-height: 1.5", rendered)
                with self.assertRaisesRegex(UserError, "Myanmar or Thai"):
                    self.render(self.roll, [line], "zpl")

    def test_myanmar_and_thai_pdf_embeds_script_fonts(self):
        engine = self.env["ir.actions.report"]._get_pdf_engine(self.roll._get_report())
        if self.env["ir.actions.report"].get_pdf_engine_state(engine) != "ok":
            self.skipTest("no working PDF engine")
        products = self.env["product.product"].create([
            {"name": "မြန်မာ လက်ဖက်ခြောက်", "default_code": "MM-001", "barcode": "MM-001"},
            {"name": "ชาเขียวไทย", "default_code": "TH-001", "barcode": "TH-001"},
        ])
        self.roll.write({"label_width_mm": 70, "label_height_mm": 50, "columns": 1})
        pdf = self.render(self.roll, [self.line(product=p) for p in products], "pdf")
        pages = PdfReader(io.BytesIO(pdf)).pages
        self.assertEqual(len(pages), 2)
        font_names = []
        for page in pages:
            fonts = page["/Resources"]["/Font"]
            for ref in fonts.values():
                font_names.append(str(ref.get_object().get("/BaseFont", "")))
        self.assertTrue(any("Myanmar" in font for font in font_names), font_names)
        self.assertTrue(any("Thai" in font for font in font_names), font_names)


    def test_code128_does_not_interpret_reference_as_subset_commands(self):
        self.roll.barcode_type = "Code128"
        self.product.barcode = "ABC>9&^~_"
        zpl = self.render(self.roll, [self.line()], "zpl").decode()
        self.assertIn("^FH^FDABC_3E09_26_5E_7E_5F^FS", zpl)

    def test_script_font_spans_keep_user_text_escaped(self):
        text = '<script>alert(1)</script> မြန်မာ ไทย & tea'
        html = str(self.roll._format_label_text(text))
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('&amp; tea', html)
        self.assertIn('font-family: BS Label Myanmar;', html)
        self.assertIn('font-family: BS Label Thai;', html)
