# Product Code Generator — Odoo 20

Ported from `std-odoo19/stb_bs_apps/bs_generate_product_code` (19.0.1.1.1)
to 20.0.1.0.0. Dependencies: `product`, `stock`.

## Changes for 20.0

- Access rights moved to `security/ir.access.csv` (v20 replaces
  `ir.model.access.csv`).
- Cache invalidation uses `_clear_cache_name = "default"` on both rule models;
  `registry.clear_cache()` no longer exists. `tools.ormcache` became `api.ormcache`.
- The settings switch is read with `ir.config_parameter.get_bool`; `get_param` and
  `set_param` are gone. The demo uses `set_bool`.
- `product.code.rule.line` has its own file (one model per file).
- Owl 3: the field selector template reads `this.selectorProps`.
- Settings button icon is `arrow_forward` (Font Awesome is gone in v20).
- Tests: Python tests run as a non-superuser (`_test_user_groups` adds Inventory
  Administrator and Product Manager). The JS test defines mail models and uses
  `th[data-name]`.

## New in 20.0

**Running Number part.** A rule can end, or contain, one Running Number part. It
keeps references unique. Products whose other parts render the same value are
numbered one after another (`DEM-18-001`, `DEM-18-002`), padded to **Length**,
starting at **Start At**.

- The next number follows the highest existing one for that reference, archived
  products and other companies included.
- A product that already holds a number in its own sequence keeps it. So
  regenerating, or editing a field the rule does not change, never renumbers it.
- Changing a watched field moves the product into the matching sequence of its
  new reference.
- Generation updates the numbered rule's row. A concurrent transaction numbering
  the same rule waits, then fails with a serialization error that Odoo retries.
  Two transactions therefore cannot take the same number.

A Running Number must not touch digits that vary. `DEM-18` numbered `001` gives
`DEM-18001`, which also reads as number `01` of `DEM-180`. So a rule is refused
when the number sits next to a part whose value can end (or start) in a digit.
The fix is a Prefix or Suffix that begins/ends with a letter or symbol, or fixed
text on that side.

**Duplicate References filter.** Product and variant lists have a Duplicate
References filter. It finds references held by more than one product, counting
archived products and all companies. The field behind it (`has_duplicate_code`)
is computed and not stored.

**Freezing used references.** Settings has "Freeze References Once Used", and
each rule has "Once Used" (As in Settings / Freeze once used / Keep following
the rule). A product counts as used once a stock move, sale, purchase, invoice,
POS or BoM line refers to it. Models of modules that are not installed are
skipped. Extend the list with `_code_usage_fields()`. A frozen reference stops
following its fields automatically. The Generate Internal Reference action
still updates it.

**Preview before generating.** Generate Internal Reference now opens a preview.
It lists each selected product's current and new reference and its state: will
change, already up to date, or no rule. It also marks new references that would
duplicate an existing one, or another line's. Nothing is written until Apply,
and only ticked lines are applied. Generation runs again on Apply, so running
numbers close up over any line you untick.

**Text fixes.** Settings, action help and the manifest no longer mention an
"attribute value" source. The only sources are Product Field, Fixed Text and
Running Number.

**Review fixes (2026-10-01).**

- Editing the product form now rebuilds references. Fields such as the category
  are written on the template and never pass through the variant's write, so
  `product.template.write` now rebuilds all its variants too, archived ones
  included.
- A blank reference is filled when a watched field changes, which covers products
  made before their rule existed or while the switch was off. This applies even
  to frozen products: no one depends on a blank reference.
- A part whose field path does not exist is refused when the rule is saved. If a
  path breaks later (say, its module is uninstalled), the product keeps its
  reference. The old behaviour dropped the part and wrote a shorter reference.
  The rule's Example shows "Cannot read ...", and the preview shows the product as
  "Rule cannot be read".
- The preview has a Used column and a warning. If a used product's rule freezes
  used references, that product is unticked by default.

**Date placeholders (2026-10-01).** Prefix, Suffix and Fixed Text accept the
same placeholders as `ir.sequence`: `%(year)s`, `%(y)s`, `%(month)s`, `%(day)s`,
`%(doy)s`, `%(woy)s`, `%(weekday)s`, `%(h24)s`, `%(h12)s`, `%(min)s`,
`%(sec)s`, `%(isoyear)s`, `%(isoy)s`, `%(isoweek)s`. The rule form lists them.

- They are filled from the product's `create_date`, in the creator's time zone,
  never from today's date. A reference is master data: rebuilding it next year,
  or as another user, gives the same result.
- With a Running Number, each date gets its own sequence: `P%(year)s` with `-001`
  gives `P2025-001`, `P2025-002`, then `P2026-001`.
- A placeholder the module does not know (`%(yeer)s`) is refused when saving. A lone
  `%` stays as typed.
- A date always ends in digits, so a Running Number next to one needs a separator,
  just as it does next to a field.
- `%(weekday)s` is Python's `%w`, where 0 is Sunday. Odoo's own sequence legend
  says "0: Monday", which is wrong.
- In view XML, the placeholders are written `%%(year)s`. A single `%(...)s` is read
  as an xmlid reference.

**Bulk action and reference history (20.0.1.1.0, 2026-10-01).**

- Generate Internal Reference is also on `product.template` (list, kanban and
  form). It previews all the variants of the selected products. Odoo 20 has no
  list of variants across products, so before this the action could only run on
  one product's Variants at a time.
- New model `product.code.history` (Inventory > Configuration > Products >
  Reference History) records each reference generation writes: product, previous
  and new reference, rule, user and date.
- The preview's **Typed** flag marks a current reference that is not in that
  history, meaning it was typed or imported. Such lines start unticked, so a bulk
  run cannot replace a code such as `FURN_6666` without someone noticing.
- `migrations/20.0.1.1.0/post-migrate.py` records the references that still
  match their rule. A generated reference that has gone stale since cannot be told
  from a typed one, so the preview flags it as Typed.

## Use

Install Product Code Generator from Apps. Define rules under
Inventory > Configuration > Products > Product Code Rules. Turn on automatic
generation in Inventory settings, or run Generate Internal Reference on selected
product variants. The first matching active rule wins.

Automatic generation keeps a reference that was supplied explicitly. The manual
action can replace it.

## Verification — 2026-09-28

Tested against Odoo 20.0+e (`config/std.conf`) on the scratch database
`odoo20_pcode`, with demo data:

- Clean install with demo data: passed. The demo panels got `Dem-12/915` …
  `Dem-18/1220`, and the bracket kept `BRACKET-001`.
- Python suite (`--test-tags=/bs_generate_product_code`): 81 tests (47 ported,
  12 Running Number, 7 number boundary, 3 duplicates, 6 freezing, 5 preview,
  1 import test run), 0 failures.
- Import test run: the import dialog's Test button (`execute_import(dryrun=True)`)
  creates the products inside a savepoint and rolls it back. The references and
  running numbers it generated are rolled back with them. Checked in the test suite
  and through the browser with a 2-row product CSV: "Everything seems valid", and
  the product and template counts were unchanged (53 / 40) before and after.
- Module update (`-u`): passed.
- Hoot JS tests, run in Chromium at `/web/tests`: 2 passed, 11 assertions.
  The Odoo runner skips them on this machine because `websocket-client` is not
  installed.
- Browser: in the rule form, the field selector shows labels, and adding a Running
  Number part shows only Length and Start At. After save, the example read
  `Dem-12/1220-001`. The freeze checkbox shows in Inventory settings. The
  Duplicate References filter found both products sharing a reference, in the
  template kanban and in the variant list. No console errors.

The concurrency lock is reasoned from PostgreSQL REPEATABLE READ semantics. It was
not exercised with two live sessions.

2026-10-01, 20.0.1.1.0: 102 Python tests, 0 failures, on `odoo20_pcode` and `odoo20_e_demo` (migration ran on both). Before that, after the review fixes and date placeholders: 96 Python tests, 0 failures (`-u` included). Rule form legend checked in Chromium, no console errors.

Databases on 19.0 need their rules and settings migrated. This port adds no
migration script.
