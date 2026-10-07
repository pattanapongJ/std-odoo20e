import { xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import {
    FieldSelectorField,
    fieldSelectorField,
} from "@web/views/fields/field_selector/field_selector_field";

// Keep the native translated field path in both list display and edit modes.
// ModelFieldSelector respects readonly and retains the technical path as data.
export class ProductCodeFieldSelector extends FieldSelectorField {
    static template = xml`<ModelFieldSelector t-props="this.selectorProps" />`;
}

registry.category("fields").add("product_code_field_selector", {
    ...fieldSelectorField,
    component: ProductCodeFieldSelector,
});
