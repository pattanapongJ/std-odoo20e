import { CheckBox } from "@web/core/checkbox/checkbox";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { _t } from "@web/core/l10n/translation";
import { rpcBus } from "@web/core/network/rpc";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { useService } from "@web/core/utils/hooks";
import { useSortable } from "@web/core/utils/sortable_owl";

import { Component, proxy, signal, t, useProps } from "@odoo/owl";

const AGGREGATABLE_TYPES = ["integer", "float", "monetary"];
const ADD_MATCH_LIMIT = 8;

/**
 * The sortable list lives in its own component: the dropdown content is mounted
 * in a popover when it opens, so the drag hook must be set up by a component
 * mounted there, not by the panel.
 */
export class BsColumnsList extends Component {
    static template = "bs_view_manager.ColumnsList";
    static components = { CheckBox };
    props = useProps({
        columns: t.array(),
        onMove: t.function(),
    });

    listRef = signal.ref();

    setup() {
        useSortable({
            ref: this.listRef,
            elements: ".o_bs_view_manager_column",
            handle: ".o_bs_view_manager_handle",
            cursor: "grabbing",
            onDrop: ({ element, previous }) =>
                this.props.onMove(element.dataset.name, previous?.dataset.name),
        });
    }

    isAggregatable(column) {
        return AGGREGATABLE_TYPES.includes(column.type);
    }
}

export class BsColumnsPanel extends Component {
    static template = "bs_view_manager.ColumnsPanel";
    static components = { BsColumnsList, CheckBox, Dropdown, MultiRecordSelector };
    props = useProps({
        resModel: t.string(),
        actionId: t.number(),
        viewId: t.any().optional(),
        activeColumnNames: t.array(),
        propertyGroups: t.array().optional([]),
        onTogglePropertyColumn: t.function().optional(),
        getWidths: t.function(),
        inlineEditing: t.boolean().optional(false),
    });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({
            loaded: false,
            columns: [],
            addable: [],
            source: "default",
            teamApplies: false,
            canShare: false,
            teamGroupIds: [],
            showFilterRow: false,
            showRowNumbers: false,
            inlineEdit: false,
            showAdmin: false,
            keepWidths: false,
            addQuery: "",
            saving: false,
        });
    }

    async load() {
        const data = await this.orm.call("bs.view.layout", "bs_get_panel_data", [
            this.props.resModel,
            this.props.actionId,
            this.props.viewId || false,
        ]);
        for (const column of data.columns) {
            column.label ||= column.default_label;
        }
        if (data.source === "default") {
            // start from what the list shows now, native optional toggles included
            const active = new Set(this.props.activeColumnNames);
            for (const column of data.columns) {
                column.visible = active.has(column.name);
            }
        }
        Object.assign(this.state, {
            loaded: true,
            columns: data.columns,
            addable: data.addable,
            source: data.source,
            teamApplies: data.team_applies,
            canShare: data.can_share,
            teamGroupIds: data.team_group_ids,
            showFilterRow: data.show_filter_row,
            showRowNumbers: data.show_row_numbers,
            addQuery: "",
            inlineEdit: data.inline_edit,
            keepWidths: false,
        });
    }

    move(name, previousName) {
        const columns = this.state.columns;
        const moved = columns.splice(columns.findIndex((col) => col.name === name), 1)[0];
        const index = previousName ? columns.findIndex((col) => col.name === previousName) + 1 : 0;
        columns.splice(index, 0, moved);
    }

    addField(name) {
        const index = this.state.addable.findIndex((field) => field.name === name);
        if (index < 0) {
            return;
        }
        const [field] = this.state.addable.splice(index, 1);
        this.state.columns.push({
            name: field.name,
            type: field.type,
            default_label: field.label,
            label: field.label,
            visible: true,
            width: false,
            aggregate: "",
            in_arch: false,
        });
    }

    /** Fields not shown yet whose label or technical name contains the query. */
    addableMatches() {
        const query = this.state.addQuery.trim().toLowerCase();
        if (!query) {
            return [];
        }
        return this.state.addable
            .filter(
                (field) =>
                    field.label.toLowerCase().includes(query) || field.name.toLowerCase().includes(query)
            )
            .slice(0, ADD_MATCH_LIMIT);
    }

    pickField(name) {
        this.addField(name);
        this.state.addQuery = "";
    }

    onAddQueryKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            const [first] = this.addableMatches();
            if (first) {
                this.pickField(first.name);
            }
        } else if (ev.key === "Escape" && this.state.addQuery) {
            // clear the search instead of closing the panel
            ev.stopPropagation();
            this.state.addQuery = "";
        }
    }

    serializeColumns() {
        const widths = this.state.keepWidths ? this.props.getWidths() : {};
        return this.state.columns.map((col) => ({
            name: col.name,
            visible: col.visible,
            // a label equal to the default one is not a rename
            label: col.label && col.label !== col.default_label ? col.label : "",
            width: widths[col.name] || col.width || false,
            aggregate: col.aggregate || "",
        }));
    }

    options() {
        return {
            show_filter_row: this.state.showFilterRow,
            show_row_numbers: this.state.showRowNumbers,
        };
    }

    toggleTitle() {
        return this.props.inlineEditing
            ? _t("Columns. Rows are edited inline: click a cell to change it.")
            : _t("Columns");
    }

    sourceText() {
        return {
            personal: _t("Your own layout"),
            team: _t("Team layout"),
            default: _t("Default layout"),
        }[this.state.source];
    }

    async save() {
        await this.run("bs_save_layout", [
            this.props.resModel,
            this.props.actionId,
            this.props.viewId || false,
            this.serializeColumns(),
            this.options(),
        ]);
    }

    async reset() {
        await this.run("bs_reset_layout", [this.props.resModel, this.props.actionId]);
    }

    async share() {
        await this.run("bs_share_layout", [
            this.props.resModel,
            this.props.actionId,
            this.props.viewId || false,
            this.serializeColumns(),
            { ...this.options(), group_ids: this.state.teamGroupIds },
        ]);
    }

    async setInlineEdit(enabled) {
        await this.run("bs_set_editable", [this.props.resModel, this.props.actionId, enabled ? "on" : "off"]);
    }

    async unshare() {
        await this.run("bs_unshare_layout", [this.props.resModel, this.props.actionId]);
    }

    async run(method, args) {
        this.state.saving = true;
        try {
            await this.orm.call("bs.view.layout", method, args);
        } finally {
            this.state.saving = false;
        }
        // the layout is applied by get_views, whose result the client caches on disk
        rpcBus.trigger("CLEAR-CACHES", "get_views");
        const controller = this.action.currentController;
        await this.action.doAction(controller.action, { stackPosition: "replaceCurrentAction" });
    }
}
