import { Domain } from "@web/core/domain";
import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

import { BsColumnFilter } from "./column_filter";
import { getFilterKind } from "./filter_domain";

patch(ListRenderer.prototype, {
    bsShowFilterRow() {
        return (
            this.bsIsViewManagerEnabled() &&
            this.bsArchFlag("bs_filter_row") &&
            Boolean(this.env.searchModel)
        );
    },

    bsFilterKind(column) {
        return column.type === "field" ? getFilterKind(this.props.list.fields[column.name]) : null;
    },

    bsFilterComponent() {
        return BsColumnFilter;
    },

    /** The facet created by the filter row for this column, if still active. */
    bsActiveFilter(column) {
        const searchModel = this.env.searchModel;
        for (const { searchItemId } of searchModel.query) {
            const item = searchModel.searchItems[searchItemId];
            if (item?.bsColumn === column.name) {
                return item;
            }
        }
        return null;
    },

    bsActiveFilterProps(column) {
        const item = this.bsActiveFilter(column);
        return item ? { display: item.bsDisplay, value: item.bsValue } : undefined;
    },

    /**
     * Current search domain without this column's own facet, for suggestions.
     * Relies on private SearchModel methods (_getGroups, _getSearchItemDomain):
     * check them when porting; without them, the whole list domain is used.
     */
    bsSuggestionDomain(column) {
        const searchModel = this.env.searchModel;
        const active = this.bsActiveFilter(column);
        if (!active || !searchModel._getGroups || !searchModel._getSearchItemDomain) {
            return this.props.list.domain;
        }
        const domains = [searchModel.globalDomain || []];
        for (const group of searchModel._getGroups()) {
            if (group.id === active.groupId) {
                continue;
            }
            domains.push(
                Domain.or(group.activeItems.map((item) => searchModel._getSearchItemDomain(item) || []))
            );
        }
        return Domain.and(domains).toList();
    },

    /** Add the filter as a real facet: it can be removed and saved as a favorite. */
    bsApplyColumnFilter(column, filter) {
        const searchModel = this.env.searchModel;
        const previous = this.bsActiveFilter(column);
        if (previous) {
            // Replace the column's facet with a single reload. blockNotification
            // is SearchModel's own internal switch (see splitAndAddDomain):
            // check it when porting.
            searchModel.blockNotification = true;
            searchModel.deactivateGroup(previous.groupId);
            searchModel.blockNotification = false;
        }
        searchModel.createNewFilters([
            {
                description: filter.description,
                domain: new Domain(filter.domain).toString(),
                invisible: "True",
                bsColumn: column.name,
                bsDisplay: filter.display,
                bsValue: filter.value,
            },
        ]);
    },

    bsClearColumnFilter(column) {
        const active = this.bsActiveFilter(column);
        if (active) {
            this.env.searchModel.deactivateGroup(active.groupId);
        }
    },
});
