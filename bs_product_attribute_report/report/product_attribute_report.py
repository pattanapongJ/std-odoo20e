# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools
from odoo.tools import SQL


class ProductAttributeReport(models.Model):
    """Stock and sales of product variants, one row per attribute value.

    Long rather than wide: a column per attribute would change the schema
    whenever the catalogue gains one. The price is that a variant appears once
    for each of its attributes, so a total only means something inside a
    single attribute - the view keeps exactly one selected.

    Stock rows carry no date; sales rows carry the order date. The date filters
    keep undated rows, so narrowing the sales period never hides stock.
    """

    _name = "bs.product.attribute.report"
    _description = "Product Attribute Report"
    _auto = False
    _order = "attribute_id, value_id"
    _rec_name = "product_id"
    # So the ORM flushes pending writes to these before the view is read.
    _depends = {
        "product.product": ["product_tmpl_id"],
        "product.template": ["categ_id", "uom_id"],
        "product.template.attribute.value": ["attribute_id", "product_attribute_value_id"],
        "stock.quant": ["product_id", "company_id", "location_id", "quantity"],
        "stock.location": ["usage", "warehouse_id"],
        "sale.order": ["state", "company_id", "warehouse_id", "date_order"],
        "sale.order.line": [
            "order_id", "product_id", "product_uom_qty", "product_uom_id",
            "display_type", "is_downpayment",
        ],
        "uom.uom": ["factor"],
    }

    product_id = fields.Many2one("product.product", string="Product Variant", readonly=True)
    product_tmpl_id = fields.Many2one("product.template", string="Product", readonly=True)
    categ_id = fields.Many2one("product.category", string="Product Category", readonly=True)
    attribute_id = fields.Many2one("product.attribute", string="Attribute", readonly=True)
    value_id = fields.Many2one("product.attribute.value", string="Value", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    warehouse_id = fields.Many2one("stock.warehouse", string="Warehouse", readonly=True)
    date = fields.Date(string="Order Date", readonly=True)
    qty_on_hand = fields.Float(string="On Hand", digits="Product Unit", readonly=True)
    sales_qty = fields.Float(string="Qty Sold", digits="Product Unit", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("CREATE OR REPLACE VIEW %s AS (%s)", SQL.identifier(self._table), self._query()))

    def _query(self):
        return SQL("""
            WITH variant_value AS (
                SELECT combination.product_product_id AS product_id,
                       ptav.attribute_id,
                       ptav.product_attribute_value_id AS value_id
                  FROM product_variant_combination combination
                  JOIN product_template_attribute_value ptav
                    ON ptav.id = combination.product_template_attribute_value_id
            ),
            measure AS (
                SELECT quant.product_id,
                       quant.company_id,
                       location.warehouse_id,
                       NULL::date AS date,
                       SUM(quant.quantity) AS qty_on_hand,
                       0.0 AS sales_qty
                  FROM stock_quant quant
                  JOIN stock_location location ON location.id = quant.location_id
                 WHERE location.usage = 'internal'
              GROUP BY quant.product_id, quant.company_id, location.warehouse_id
                UNION ALL
                SELECT line.product_id,
                       sale.company_id,
                       sale.warehouse_id,
                       (sale.date_order AT TIME ZONE 'UTC')::date AS date,
                       0.0 AS qty_on_hand,
                       -- In the product's own unit, as sale.report does.
                       SUM(line.product_uom_qty * COALESCE(line_uom.factor, 1)
                           / NULLIF(COALESCE(product_uom.factor, 1), 0.0)) AS sales_qty
                  FROM sale_order_line line
                  JOIN sale_order sale ON sale.id = line.order_id
                  JOIN product_product product ON product.id = line.product_id
                  JOIN product_template template ON template.id = product.product_tmpl_id
             LEFT JOIN uom_uom line_uom ON line_uom.id = line.product_uom_id
             LEFT JOIN uom_uom product_uom ON product_uom.id = template.uom_id
                 WHERE sale.state = 'sale'
                   AND line.display_type IS NULL
                   AND line.is_downpayment IS NOT TRUE
              GROUP BY line.product_id, sale.company_id, sale.warehouse_id,
                       (sale.date_order AT TIME ZONE 'UTC')::date
            )
            SELECT row_number() OVER () AS id,
                   measure.product_id,
                   product.product_tmpl_id,
                   template.categ_id,
                   variant_value.attribute_id,
                   variant_value.value_id,
                   measure.company_id,
                   measure.warehouse_id,
                   measure.date,
                   measure.qty_on_hand,
                   measure.sales_qty
              FROM measure
              JOIN variant_value ON variant_value.product_id = measure.product_id
              JOIN product_product product ON product.id = measure.product_id
              JOIN product_template template ON template.id = product.product_tmpl_id
        """)

    @api.model
    def action_open(self):
        """Open the report on the first attribute that has data, never on
        all of them at once."""
        attribute = self.search([], limit=1).attribute_id
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "bs_product_attribute_report.action_product_attribute_report"
        )
        action["context"] = {
            "searchpanel_default_attribute_id": attribute.id,
            # The panel already names the attribute; rows show the value alone.
            "show_attribute": False,
        }
        return action
