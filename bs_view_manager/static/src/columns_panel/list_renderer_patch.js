import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

import { BsColumnsPanel } from "./columns_panel";

// Methods on the prototype rather than an entry in static components: subclasses
// (sale, account, stock, ...) copy the components object when they are defined.
patch(ListRenderer.prototype, {
    get hasActionsColumn() {
        return super.hasActionsColumn || this.bsIsViewManagerEnabled();
    },

    /**
     * Only the main list of a window action gets the panel: x2many lists inside
     * a form run with viewType "form" and have no layout of their own.
     */
    bsIsViewManagerEnabled() {
        const config = this.env.config || {};
        return Boolean(
            config.actionId &&
                config.viewType === "list" &&
                this.props.list === this.props.list.model.root &&
                !this.uiService.isSmall
        );
    },

    /** Whether the layout sets this flag attribute on the list arch. */
    bsArchFlag(name) {
        return this.env.config.viewArch?.getAttribute(name) === "1";
    },

    bsPanelComponent() {
        return BsColumnsPanel;
    },

    /**
     * The columns a Properties field unfolds into. They are not in the arch, so
     * the layout cannot hold them; the native optional-column switch does.
     */
    bsPropertyColumnGroups() {
        return this.optionalFieldGroups.filter((group) => group.id);
    },

    bsActiveColumnNames() {
        return this.columns.filter((col) => col.type === "field").map((col) => col.name);
    },

    bsGetWidths() {
        const widths = {};
        for (const th of this.tableRef().querySelectorAll("thead th[data-name]")) {
            widths[th.dataset.name] = Math.round(th.getBoundingClientRect().width);
        }
        return widths;
    },

    /** Classes of the list table; the other features add theirs. */
    bsTableClass() {
        return {};
    },

    /** Inline style of the list table; the other features add theirs. */
    bsTableStyle() {
        return "";
    },
});
