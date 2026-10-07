import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { createContext, runInContext } from "node:vm";

const source = process.env.ODOO_SOURCE;
assert.ok(source, "Provide ODOO_SOURCE");
const read = (path) => readFileSync(path, "utf8");
const patch = read(resolve(source, "addons/web/static/src/core/utils/patch.js"))
    .replace("export function patch", "function patch");
const helpers = read(resolve(source, "addons/web_tour/static/src/tour_helpers/tour_helpers.js"))
    .replace("export class TourHelpers", "class TourHelpers");
const replacement = read(new URL("../static/src/compat/tour_helpers_clipboard.js", import.meta.url));
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

// Exercise Odoo's actual module detection/transformation, then execute the output
// through a loader with the real patch utility and TourHelpers class.
test("tour asset is transpiled and loads through odoo.define", () => {
    const result = spawnSync("python3", ["-c", `
import sys
from pathlib import Path
# Only isolate OrderedSet to avoid bootstrapping an Odoo database/environment.
class OrderedSet(dict):
    def add(self, value):
        self[value] = None
scope = {"OrderedSet": OrderedSet}
transpiler = Path(sys.argv[1]) / "odoo/tools/js_transpiler.py"
code = transpiler.read_text().replace("from odoo.tools.misc import OrderedSet", "")
exec(compile(code, str(transpiler), "exec"), scope)
url = "/bs_web_chatter_position/static/src/compat/tour_helpers_clipboard.js"
content = sys.stdin.read()
assert scope["is_odoo_module"](url, content)
print(scope["transpile_javascript"](url, content))
`, source], { input: replacement, encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /odoo\.define/);
    assert.doesNotMatch(result.stdout, /^import /m);
    const context = createContext({ window: { navigator: {} } });
    runInContext(patch + "\n" + helpers + `
        const loaded = new Map();
        const dependencies = {
            "@web/core/utils/patch": { patch },
            "@web_tour/tour_helpers/tour_helpers": { TourHelpers },
        };
        const odoo = { define(name, deps, factory) {
            for (const dep of deps) {
                if (!dependencies[dep]) throw new Error("Missing dependency: " + dep);
            }
            loaded.set(name, factory((name) => dependencies[name]));
        } };
    ` + result.stdout, context);
    assert.equal(runInContext('loaded.has("@bs_web_chatter_position/compat/tour_helpers_clipboard")', context), true);
    runInContext("const helper = new TourHelpers(); helper.allowClipboardWrite(); helper.restoreClipboardWrite();", context);
});
