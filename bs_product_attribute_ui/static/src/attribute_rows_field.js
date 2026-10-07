import { Component, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * A variant's attributes, one row per attribute.
 *
 * Reads product.template.attribute.value records, which know both the
 * attribute they belong to and their own value. Splitting their display_name
 * ("Attribute: Value") back apart would break on any value containing a colon,
 * so the two fields are asked for instead, through relatedFields.
 */
export class ProductAttributeRowsField extends Component {
    static template = "bs_product_attribute_ui.ProductAttributeRows";
    props = useProps(standardFieldProps);

    /**
     * @returns {Array<{id: number, label: string, values: string[]}>} the
     *   attributes in the order their values arrive, each with every value the
     *   variant carries for it.
     */
    get attributeRows() {
        const rows = new Map();
        for (const record of this.props.record.data[this.props.name].records) {
            const attribute = record.data.attribute_id;
            if (!attribute) {
                // A value whose attribute was deleted under it: nothing to
                // label the row with.
                continue;
            }
            if (!rows.has(attribute.id)) {
                rows.set(attribute.id, {
                    id: attribute.id,
                    label: attribute.display_name,
                    values: [],
                });
            }
            rows.get(attribute.id).values.push(record.data.name || record.data.display_name);
        }
        return [...rows.values()];
    }
}

export const productAttributeRowsField = {
    component: ProductAttributeRowsField,
    displayName: _t("Attribute Rows"),
    supportedTypes: ["many2many"],
    relatedFields: () => [
        { name: "attribute_id", type: "many2one" },
        // "name" is the value on its own; display_name is only the fallback.
        { name: "name", type: "char" },
        { name: "display_name", type: "char" },
    ],
};

registry.category("fields").add("product_attribute_rows", productAttributeRowsField);
