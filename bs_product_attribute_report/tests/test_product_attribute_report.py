# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon


@tagged("post_install", "-at_install")
class TestProductAttributeReport(BaseCommon):
    _test_user_groups = (
        "base.group_user",
        "product.group_product_variant",
        "stock.group_stock_manager",
        "sales_team.group_sale_manager",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        admin = cls.env(su=True)
        Attribute = admin["product.attribute"]
        Value = admin["product.attribute.value"]
        cls.thickness = Attribute.create({"name": "Rep Thickness"})
        cls.thick_18, cls.thick_25 = Value.create([
            {"name": "18 mm", "attribute_id": cls.thickness.id},
            {"name": "25 mm", "attribute_id": cls.thickness.id},
        ])
        cls.finish = Attribute.create({"name": "Rep Finish"})
        cls.matt = Value.create({"name": "Matt", "attribute_id": cls.finish.id})
        template = admin["product.template"].create({
            "name": "Rep Panel",
            "is_storable": True,
            "attribute_line_ids": [
                (0, 0, {"attribute_id": cls.thickness.id,
                        "value_ids": [(6, 0, (cls.thick_18 | cls.thick_25).ids)]}),
                (0, 0, {"attribute_id": cls.finish.id,
                        "value_ids": [(6, 0, cls.matt.ids)]}),
            ],
        })
        variants = template.product_variant_ids
        cls.panel_18 = variants.filtered(
            lambda v: cls.thick_18 in v.product_template_attribute_value_ids.product_attribute_value_id
        ).with_env(cls.env)
        cls.panel_25 = (variants - cls.panel_18).with_env(cls.env)
        cls.stock = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        ).lot_stock_id
        cls.customer = cls.env["res.partner"].create({"name": "Rep Customer"})

    def put_in_stock(self, product, quantity):
        self.env["stock.quant"].sudo()._update_available_quantity(product, self.stock, quantity)

    def sell(self, product, quantity, uom=None, confirm=True, date=None):
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [(0, 0, {
                "product_id": product.id,
                "product_uom_qty": quantity,
                **({"product_uom_id": uom.id} if uom else {}),
            })],
        })
        if confirm:
            order.action_confirm()
        if date:
            order.date_order = date
        return order

    def totals(self, attribute, domain=()):
        groups = self.env["bs.product.attribute.report"].formatted_read_group(
            [("attribute_id", "=", attribute.id),
             ("product_tmpl_id.name", "=", "Rep Panel"), *domain],
            ["value_id"],
            ["qty_on_hand:sum", "sales_qty:sum"],
        )
        return {
            group["value_id"][0]: (group["qty_on_hand:sum"], group["sales_qty:sum"])
            for group in groups
        }

    def test_stock_on_hand_is_counted_per_value(self):
        self.put_in_stock(self.panel_18, 10)
        self.put_in_stock(self.panel_25, 4)

        self.assertEqual(
            self.totals(self.thickness),
            {self.thick_18.id: (10, 0), self.thick_25.id: (4, 0)},
        )

    def test_a_variant_counts_under_each_of_its_attributes(self):
        self.put_in_stock(self.panel_18, 10)
        self.put_in_stock(self.panel_25, 4)

        self.assertEqual(self.totals(self.finish), {self.matt.id: (14, 0)})

    def test_confirmed_sales_are_counted(self):
        self.sell(self.panel_18, 3)
        self.sell(self.panel_18, 5, confirm=False)

        self.assertEqual(self.totals(self.thickness)[self.thick_18.id][1], 3)

    def test_sales_are_counted_in_the_product_unit(self):
        self.sell(self.panel_25, 2, uom=self.env.ref("uom.product_uom_dozen"))

        self.assertEqual(self.totals(self.thickness)[self.thick_25.id][1], 24)

    def test_a_sales_period_keeps_the_stock(self):
        self.put_in_stock(self.panel_18, 10)
        self.sell(self.panel_18, 3, date=fields.Datetime.now() - timedelta(days=200))
        self.sell(self.panel_18, 2)
        since = fields.Date.today() - timedelta(days=30)

        totals = self.totals(
            self.thickness, ["|", ("date", "=", False), ("date", ">=", since)]
        )

        self.assertEqual(totals[self.thick_18.id], (10, 2))

    def test_the_report_opens_on_one_attribute(self):
        self.put_in_stock(self.panel_18, 1)
        server_action = self.env.ref(
            "bs_product_attribute_report.action_product_attribute_report_open"
        )

        action = server_action.run()

        self.assertEqual(action["res_model"], "bs.product.attribute.report")
        self.assertTrue(action["context"]["searchpanel_default_attribute_id"])

    def test_a_pivot_cell_opens_a_readable_list(self):
        """Drilling into a cell lists the rows behind it, not bare ids."""
        arch = self.env["bs.product.attribute.report"].get_view(view_type="list")["arch"]

        for field in ("product_id", "value_id", "qty_on_hand", "sales_qty"):
            self.assertIn(f'name="{field}"', arch)
        action = self.env.ref("bs_product_attribute_report.action_product_attribute_report").sudo()
        self.assertIn("list", action.view_mode.split(","))
