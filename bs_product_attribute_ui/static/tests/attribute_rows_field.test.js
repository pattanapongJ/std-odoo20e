import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { expect, test } from "@odoo/hoot";
import { queryAllTexts } from "@odoo/hoot-dom";
import { defineModels, fields, models, mountView } from "@web/../tests/web_test_helpers";

class Attribute extends models.Model {
    _name = "product.attribute";
    name = fields.Char();
    _records = [
        { id: 1, name: "Thickness" },
        { id: 2, name: "Finish" },
    ];
}
class AttributeValue extends models.Model {
    _name = "product.template.attribute.value";
    name = fields.Char();
    attribute_id = fields.Many2one({ relation: "product.attribute" });
    _records = [
        { id: 11, name: "18 mm", attribute_id: 1 },
        { id: 12, name: "Matt", attribute_id: 2 },
        { id: 13, name: "Gloss", attribute_id: 2 },
        { id: 14, name: "Orphan", attribute_id: false },
    ];
}
class Product extends models.Model {
    _name = "product.product";
    value_ids = fields.Many2many({ relation: "product.template.attribute.value" });
    _records = [{ id: 1, value_ids: [11, 12, 13, 14] }];
}
defineModels([Attribute, AttributeValue, Product]);
// Installed alongside mail, whose services load in every backend test.
defineMailModels();

test("one row per attribute, values side by side", async () => {
    await mountView({
        type: "form",
        resModel: "product.product",
        resId: 1,
        arch: `<form><field name="value_ids" widget="product_attribute_rows" readonly="1"/></form>`,
    });
    expect(queryAllTexts(".o_attribute_label")).toEqual(["Thickness", "Finish"]);
    expect(queryAllTexts(".o_attribute_row:last .o_attribute_value")).toEqual(["Matt", "Gloss"]);
    // A value without an attribute has no row to sit in.
    expect(".o_attribute_value").toHaveCount(3);
});
