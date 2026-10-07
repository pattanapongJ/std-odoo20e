import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

// defines bsTableClass/bsTableStyle, extended below with super
import "../columns_panel/list_renderer_patch";

patch(ListRenderer.prototype, {
    bsShowRowNumbers() {
        return this.bsIsViewManagerEnabled() && this.hasSelectors && this.bsArchFlag("bs_row_numbers");
    },

    bsTableClass() {
        const classes = super.bsTableClass();
        if (this.bsShowRowNumbers()) {
            classes.o_bs_view_manager_row_numbers = true;
            classes.o_bs_view_manager_has_selection = Boolean(this.props.list.selection?.length);
        }
        return classes;
    },

    bsTableStyle() {
        const style = super.bsTableStyle();
        if (!this.bsShowRowNumbers()) {
            return style;
        }
        // numbering continues across pages
        return `${style}--bs-view-manager__row-offset: ${this.props.list.offset || 0};`;
    },
});
