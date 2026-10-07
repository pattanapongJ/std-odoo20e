# Product Attribute Report — Odoo 20

Pivot and graph of stock on hand and quantity sold by attribute value (Colour,
Size, Thickness …). Menus: Inventory > Reporting and Sales > Reporting >
Stock and Sales by Attribute. Both are for managers, since both Reporting menus are.

Depends on `bs_product_attribute_ui` and `sale_stock`.

## How it works

`bs.product.attribute.report` is a SQL view in long format: one row per
variant × attribute value, for each measure source.

- **On Hand:** `stock.quant` in internal locations, per company and warehouse,
  with no date.
- **Qty Sold:** confirmed sale order lines (`state = 'sale'`, no sections,
  notes or down payments), converted to the product's unit the way `sale.report`
  does, dated by order date.

Adding an attribute never changes the schema.

**Totals are only meaningful inside one attribute.** A variant appears once
under each of its attributes. The side panel therefore selects one attribute, and
the menu opens on the first one that has data. The panel still offers "All",
where the grand total counts a variant once per attribute.

The "Sold in the Last 30/90 Days / 12 Months" filters keep the undated stock
rows, so a sales period never hides stock. Dates are the UTC order date.

Clicking a pivot cell opens the rows behind it as a list: variant, value,
warehouse, order date, On Hand and Qty Sold, with totals. Without a list view it
showed only ids.

Only products with attributes appear. POS sales are not included (no `pos`
dependency).

## Verification — 2026-09-29

Scratch DB `odoo20_pcode` (Odoo 20.0+e, demo data):

- Install: passed. Python tests: 6 (stock per value, counted per attribute,
  confirmed sales only, unit conversion from Dozens, period filter keeps
  stock, and the menu's server action as a non-admin user), 0 failures.
- Browser: the menu opens on Color, showing White 165 / 1 and Black 136 / 47
  (On Hand / Qty Sold), which matches `formatted_read_group` on the same data.
  Switching to Legs shows Steel, Aluminium and Custom. Row labels show the value
  alone. No console errors.
- 2026-09-29, on `odoo20_e_demo` (port 8020): clicking a pivot cell listed
  "Solid Shampoo (Argan Oil) | Argan Oil | Odoo Cosmetics Store | 9.00 | 0.00".
  Python tests: 7.
