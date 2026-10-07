import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import { createContext, runInContext } from "node:vm";

const source = process.env.ODOO_SOURCE;
assert.ok(source, "Provide ODOO_SOURCE");
const read = (path) => readFileSync(path, "utf8");
const patch = read(resolve(source, "addons/web/static/src/core/utils/patch.js"))
    .replace("export function patch", "function patch");
const helpers = read(resolve(source, "addons/web_tour/static/src/tour_helpers/tour_helpers.js"))
    .replace("export class TourHelpers", "class TourHelpers");
const replacement = read(new URL("../static/compat/tour_helpers_clipboard.js", import.meta.url));
const upstream = read(resolve(source, "addons/web_tour/static/src/tour_helpers/tour_helpers_clipboard.js"));
function load(module, navigator) {
    const context = createContext({ window: { navigator } });
    runInContext(patch + "\n" + helpers + "\n" + module.replace(/^import .*;\n/gm, ""), context);
    return runInContext("new TourHelpers()", context);
}

test("tour helper loads and runs without clipboard on HTTP", () => {
    const navigator = {};
    const helper = load(replacement, navigator);
    helper.allowClipboardWrite();
    helper.restoreClipboardWrite();
    assert.equal(navigator.clipboard, undefined);
});

test("HTTPS clipboard mock resolves without writing and restores original method", async () => {
    let writes = 0;
    const clipboard = { writeText() { writes++; return Promise.resolve(); } };
    const original = clipboard.writeText;
    const helper = load(replacement, { clipboard });
    for (let i = 0; i < 2; i++) {
        helper.allowClipboardWrite();
        await clipboard.writeText("test");
        assert.equal(writes, i);
        helper.restoreClipboardWrite();
        assert.equal(clipboard.writeText, original);
        await clipboard.writeText("test");
        assert.equal(writes, i + 1);
    }
});

test("upstream helper reproduces the reported HTTP import failure", () => {
    assert.throws(() => load(upstream, {}), /writeText/);
});
