# Product Attribute UI — Odoo 20

Ported from `std-odoo17c/std_bs_apps/bs_product_attribute_ui` (17.0.1.0.0) to
20.0.1.0.2. Depends on `product` only.

## What is ported

1. **Attribute rows on the variant form.** One row per attribute, with the
   attribute name on the left and its value(s) on the right. It replaces the
   core tags. Core v20 still filters those tags to lines with more than one value
   (`product_template_variant_value_ids`), so single-value attributes stay
   hidden without this module.
2. **Attribute search panel on variant lists.** Values are grouped under
   their attribute, with counters, and multi-select. It uses a stored
   `product_attribute_value_ids`, so "18 mm" is one value across templates. It is
   added in `_get_view`, extending a panel the view already has (catalogue,
   stock report) rather than replacing it. A per-attribute "In Filter Panel"
   switch leaves large attributes out. A Group By "Attribute Value" is also added.

## Added in 20.0

3. **Attribute Summary column.** The variant list has an optional column
   (hidden until picked). It holds the whole combination as text, for example
   "Thickness: 18 mm, Width: 915 mm", with single-value lines included. It is
   computed and not stored, so it cannot be grouped or sorted by.

For stock and sales by attribute, see `bs_product_attribute_report`.

4. **Attribute columns, as properties.** An attribute marked **Column on
   Variants** (on the attribute form or list) gets a column of its own in every
   product-variant list, including Inventory > Reporting > Stock. The column is
   optional and hidden until picked. It also gets a Group By under **Attribute
   Columns**.
   - Stored in one Properties field on the variant (`attribute_properties`,
     JSONB). Switching a column on or off changes no table and does not reload
     the registry.
   - The definition is core's `properties.base.definition` for
     `product.product.attribute_properties`, the mechanism
     `properties.base.definition.mixin` uses for `res.partner`. The link field
     `attribute_properties_definition_id` is computed, with `compute_sql`, and not
     stored. The definition is written only by code: one selection property per
     attribute, named `attribute_<id>`, with options `value_<id>`.
   - Kept in sync on these events: variant create, variant combination change,
     attribute on/off/rename/resequence, and value create/rename/delete.
     Renames relabel the column and its options without rewriting variants.
     Switching an attribute on or off rewrites only the variants that carry it,
     batched by identical values.
   - Why the core definition (20.0.1.0.2): 20.0.1.0.0/1 kept their own
     container record and a stored link. That had two problems. Variants that
     existed before install were left unlinked, which showed "No Properties".
     Actions opened from a template (Variants button) set `active_id`, and the
     web client then looked for a container with that id, which also showed "No
     Properties". A base definition has neither problem. The 20.0.1.0.2
     migration rewrites the definition there and drops the old
     `bs_product_attribute_column_set` table. Variant values keep their keys.
   - The list and search nodes are added in `_get_view`, so any
     product.product list gets the columns. The column is read-only.
   - The web client offers property columns through the native optional-column
     menu. `bs_view_manager` replaces that menu, so its Columns panel now lists
     them under the property field's name. They switch on at once and are
     remembered per browser, like native optional columns.

## Not ported

The 17.0 implementation of Column on Variants was left out on purpose. It used
`x_pav_<id>` manual computed fields, their `read_group` label override and the
uninstall hook. It changed the database schema from the UI and reloaded the
registry inside a user transaction. Item 4 above replaces it with properties.
The boolean keeps its 17.0 name, `variant_column`.

A 17.0 database that used it still holds `x_pav_*` fields in `ir.model.fields`.
After upgrading, drop them. Then turn each attribute's Column on Variants off and
on, or call `product.attribute._sync_column_definition()` and
`product.product._sync_attribute_columns()` on all variants, to fill the
properties. There is no migration script yet.

## Changes for 20.0

- The Owl 3 widget uses `useProps` and `this.` in the template. v20 many2one values are
  `{id, display_name}` objects, not `[id, name]` pairs.
- Search panel icon `sell` (Font Awesome is gone). The Group By filter is anchored
  on `group_by_product_tmpl_id`.
- The stored field's label is "Shared Attribute Values", to avoid a label clash
  with core's "Attribute Values".
- Tests added. The 17.0 module had none.

## Verification — 2026-09-28

Scratch DB `odoo20_pcode` (Odoo 20.0+e, demo data):

- Install: passed. Python tests: 20, 0 failures (8 of them for attribute columns). Hoot test (Chromium,
  `/web/tests`): 1 passed, 3 assertions.
- Browser: the variant list panel shows Color, Demo Thickness, Demo Width,
  Fabric and Legs sections with counters. Picking "18 mm" narrowed 53 variants
  to 2. The variant form shows "Demo Thickness | 18 mm", "Demo Width | 915 mm". No
  console errors.
- Attribute columns (2026-09-29): Color was switched on in the scratch DB. In
  Inventory > Reporting > Stock, "Color" appears among the optional columns and
  shows White / Black. Group By > Attribute Columns > Color gives White 4, Black 3,
  and 33 without a colour. No console errors.
- 20.0.1.0.1 (2026-09-29): `odoo20_e_demo` had all 196 variants unlinked, so the
  Group By showed "No Properties". After the upgrade all were linked. A fresh install
  with demo data (a throwaway DB) left 0 of 50 variants unlinked. Python tests: 21.
- 20.0.1.0.2 (2026-09-29), checked through the UI on `odoo20_e_demo` (with
  `bs_view_manager`): Casual T-shirt > Variants. The Columns panel lists Size and
  color. Ticking color shows White/Black/Green/Purple. Group By > Attribute
  Columns > color gives four groups of 8. No console errors. Python tests: 24 here,
  plus 23 for bs_view_manager, all passing.
