# Product Labels - Inventory (`bs_product_label_stock`) - Odoo 20

Bridge between `bs_product_label` and `stock`, installed automatically when both
are present.

- **Print from lots/serials and transfers** (Actions > Custom Labels).
- **Transfer quantities follow core's label wizard.** Done or reserved
  quantities are used when there are any, else the demand. A product in units
  gets one label per unit. One in another unit (kg, m) gets a single label. Each
  lot gets its own line.
- **Lot on the label.** The profile has a **Lot/Serial Number** switch. Barcode
  source **Lot/Serial, else Product Barcode** encodes the lot.
- **Menu.** Inventory > Configuration > Products > Label Profiles, for
  inventory managers.

The lot is also the worked example of extending the label: see
`_prepare_label_values`, the `label_body` xpath and `_label_line`.

Tests: 6 (transfer quantities, lot line, lot value and barcode, lot on the
printed label, lot carried through the dialog).
