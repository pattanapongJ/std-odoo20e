import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { expect, test } from "@odoo/hoot";
import {
    contains,
    defineModels,
    fields,
    MockServer,
    models,
    mountView,
} from "@web/../tests/web_test_helpers";
import "@bs_generate_product_code/fields/product_code_field_selector";

class Category extends models.Model {
    name = fields.Char({ string: "Category Name" });
}
class Product extends models.Model {
    category_id = fields.Many2one({ relation: "category", string: "Product Category" });
}
class RulePart extends models.Model {
    res_model = fields.Char();
    field_path = fields.Char();
    text = fields.Char();
    _records = [{ id: 1, res_model: "product", field_path: "category_id.name" }];
}
defineModels([Category, Product, RulePart]);
// stock pulls in mail, whose services load in every backend test.
defineMailModels();

function expectStoredPath() {
    const [part] = MockServer.env["rule.part"].read([1], ["field_path"]);
    expect(part.field_path).toBe("category_id.name");
}

function expectFriendlyPath() {
    expect(".o_model_field_selector_chain_part:first").toHaveText("Product Category");
    expect(".o_model_field_selector_chain_part:last").toHaveText("Category Name");
}

test("readonly shows labels and does not open the picker", async () => {
    await mountView({
        type: "form", resModel: "rule.part", resId: 1,
        arch: `<form>
            <field name="res_model" invisible="1"/>
            <field name="field_path" widget="product_code_field_selector"
                options="{'model': 'res_model'}" readonly="1"/>
        </form>`,
    });
    expectFriendlyPath();
    await contains(".o_model_field_selector").click();
    expect(".o_popover_field_selector").toHaveCount(0);
    expectStoredPath();
});

test("list labels survive entering and leaving row editing", async () => {
    await mountView({
        type: "list", resModel: "rule.part",
        arch: `<list editable="bottom">
            <field name="res_model" column_invisible="1"/>
            <field name="field_path" widget="product_code_field_selector"
                options="{'model': 'res_model'}"/>
            <field name="text"/>
        </list>`,
    });
    expectFriendlyPath();
    await contains(".o_data_cell[name='text']").click();
    expectFriendlyPath();
    await contains(".o_list_view th[data-name='text']").click();
    expectFriendlyPath();
    expectStoredPath();
});
