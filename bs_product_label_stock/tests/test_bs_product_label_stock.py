# -*- coding: utf-8 -*-

from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon


@tagged("post_install", "-at_install")
class TestBsProductLabelStock(BaseCommon):
    _test_user_groups = (
        "base.group_user",
        "stock.group_stock_manager",
        "stock.group_production_lot",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.profile = cls.env["bs.label.profile"].create({
            "name": "Test lot roll",
            "label_width_mm": 50,
            "label_height_mm": 30,
            "barcode_source": "lot",
        })
        cls.unit_product = cls.env["product.product"].create({
            "name": "Label Bolt", "is_storable": True, "default_code": "BOLT", "barcode": "BOLT-EAN",
        })
        cls.lot_product = cls.env["product.product"].create({
            "name": "Label Paint", "is_storable": True, "tracking": "lot",
        })
        cls.kg_product = cls.env["product.product"].create({
            "name": "Label Sand", "is_storable": True,
            "uom_id": cls.env.ref("uom.product_uom_kgm").id,
        })
        cls.lot = cls.env["stock.lot"].create({"name": "LOT-A", "product_id": cls.lot_product.id})
        warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.env.company.id)], limit=1)
        cls.picking = cls.env["stock.picking"].create({
            "picking_type_id": warehouse.in_type_id.id,
            "location_id": cls.env.ref("stock.stock_location_suppliers").id,
            "location_dest_id": warehouse.lot_stock_id.id,
            "move_ids": [
                (0, 0, {"product_id": cls.unit_product.id, "product_uom_qty": 3}),
                (0, 0, {"product_id": cls.kg_product.id, "product_uom_qty": 12.5}),
                (0, 0, {"product_id": cls.lot_product.id, "product_uom_qty": 4}),
            ],
        })

    def lines_by_product(self, lines):
        return {line["product_id"]: line for line in lines}

    def test_a_transfer_counts_units_and_labels_other_units_once(self):
        lines = self.lines_by_product(
            self.env["bs.label.print.wizard"]._lines_from_stock_picking(self.picking)
        )

        self.assertEqual(lines[self.unit_product.id]["quantity"], 3)
        self.assertEqual(lines[self.kg_product.id]["quantity"], 1)
        self.assertEqual(lines[self.unit_product.id]["source"], self.picking.name)

    def test_a_received_lot_gets_its_own_line(self):
        self.picking.action_confirm()
        move = self.picking.move_ids.filtered(lambda m: m.product_id == self.lot_product)
        move.move_line_ids.unlink()
        self.env["stock.move.line"].create({
            "move_id": move.id,
            "picking_id": self.picking.id,
            "product_id": self.lot_product.id,
            "lot_id": self.lot.id,
            "quantity": 4,
            "location_id": move.location_id.id,
            "location_dest_id": move.location_dest_id.id,
        })

        lines = self.env["bs.label.print.wizard"]._lines_from_stock_picking(self.picking)

        lot_line = next(line for line in lines if line["product_id"] == self.lot_product.id)
        self.assertEqual((lot_line["lot_id"], lot_line["quantity"]), (self.lot.id, 4))

    def test_a_lot_prints_its_name_and_barcode(self):
        line = self.env["bs.label.print.wizard"]._lines_from_stock_lot(self.lot)[0]

        values = self.profile._prepare_label_values(line)

        self.assertEqual(values["lot"], "LOT-A")
        self.assertEqual(values["barcode_value"], "LOT-A")

    def test_without_a_lot_the_product_barcode_is_used(self):
        values = self.profile._prepare_label_values({"product_id": self.unit_product.id, "quantity": 1})

        self.assertEqual(values["barcode_value"], "BOLT-EAN")

    def test_the_lot_is_on_the_printed_label(self):
        self.profile.output = "html"
        report = self.profile._get_report().with_context(bs_label_profile_id=self.profile.id)
        data = {
            "profile_id": self.profile.id, "pricelist_id": False, "test": False,
            "lines": [{"product_id": self.lot_product.id, "lot_id": self.lot.id, "quantity": 1}],
        }

        html, _type = report._render_qweb_html(report.report_name, None, data=data)

        self.assertIn("LOT-A", html.decode())

    def test_the_dialog_carries_the_lot(self):
        action = self.env["bs.label.print.wizard"]._action_open(self.lot)
        wizard = self.env["bs.label.print.wizard"].browse(action["res_id"])

        self.assertEqual(wizard.line_ids.lot_id, self.lot)
        self.assertEqual(wizard._label_lines()[0]["lot_id"], self.lot.id)

    def test_the_lot_column_shows_only_for_tracked_products(self):
        Wizard = self.env["bs.label.print.wizard"]
        untracked = Wizard.create({"line_ids": [(0, 0, {"product_id": self.unit_product.id})]})
        tracked = Wizard.create({"line_ids": [(0, 0, {"product_id": self.lot_product.id})]})

        self.assertFalse(untracked.has_tracked_line)
        self.assertTrue(tracked.has_tracked_line)

    def test_a_lot_on_an_untracked_product_is_ignored(self):
        wizard = self.env["bs.label.print.wizard"].create({
            "line_ids": [(0, 0, {"product_id": self.unit_product.id, "lot_id": self.lot.id})],
        })

        self.assertFalse(wizard._label_lines()[0]["lot_id"])

    def test_the_menu_opens_an_empty_dialog(self):
        action = self.env.ref("bs_product_label_stock.action_print_labels_blank").run()
        wizard = self.env["bs.label.print.wizard"].browse(action["res_id"])

        self.assertEqual(action["target"], "new")
        self.assertFalse(wizard.line_ids)
        self.assertTrue(wizard.profile_id)
