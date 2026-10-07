import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
import { ListRenderer } from "@web/views/list/list_renderer";

// defines bsTableClass/bsTableStyle, extended below with super
import "../columns_panel/list_renderer_patch";

/**
 * When this module turned inline editing on, only existing rows are edited in
 * the list: New still opens the form, as it did before.
 */
patch(ListController.prototype, {
    async createRecord() {
        if (this.env.config?.viewArch?.getAttribute("bs_inline_edit") === "1") {
            return this.props.createRecord();
        }
        return super.createRecord(...arguments);
    },
});

patch(ListRenderer.prototype, {
    bsIsInlineEditing() {
        return this.bsIsViewManagerEnabled() && this.bsArchFlag("bs_inline_edit");
    },

    bsTableClass() {
        const classes = super.bsTableClass();
        if (this.bsIsInlineEditing()) {
            classes.o_bs_view_manager_inline_edit = true;
        }
        return classes;
    },
});
