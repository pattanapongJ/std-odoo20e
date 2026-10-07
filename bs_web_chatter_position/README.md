# Chatter Position (bs_web_chatter_position) — Odoo 20

Per-user preference (My Preferences, and the user form for admins): **Automatic** (standard), **Below the form**,
**Beside the form**. Saving preferences reloads the page, which applies it.

- Below: forms always use the full content width; the chatter follows the sheet.
- Beside: chatter goes aside from the LG breakpoint up (standard waits for XXL).
- Dialogs and forms without a sheet are untouched.

How: the value is sent in `session_info`; JS patches `FormRenderer.mailLayout`, the form root's flex class in
`FormCompiler.compileForm` and `FormController.className` (`o_xxl_form_view`). The field is `user_writeable`
(v20 field-level self-write).

Tests include two tours (side at 1366px, bottom at 1920px). Tours need `websocket-client` in the venv and
`ODOO_BROWSER_BIN` pointing at a Chrome/Chromium when none is on PATH.

Odoo 20 compatibility: replaces the tour clipboard helper in `web_tour.helpers` to
avoid an import-time crash when HTTP provides no `navigator.clipboard`. The helper
keeps its mock/restore behavior on HTTPS and does nothing when the API is absent.
This does not enable clipboard features on HTTP or remove the secure-context warning.
Remove the replacement when the upstream helper guards clipboard access.

Run the isolated clipboard regression checks with:
`ODOO_SOURCE=/path/to/odoo node --test bs_web_chatter_position/tests/clipboard_compat.test.mjs`.

The compatibility helper lives under `static/src/compat` so Odoo transpiles its
ES module imports. The backend bundle lists only `chatter_position.js`; the
compatibility helper loads exclusively through `web_tour.helpers`. Regression
checks also execute the real Odoo JS transpiler and its resulting module.
