import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
import { ListRenderer } from "@web/views/list/list_renderer";

const AGGREGATES = ["sum", "avg", "min", "max"];

function columnAggregate(column) {
    return AGGREGATES.find((agg) => column.attrs?.[agg]);
}

/**
 * Group rows get their totals from the server with each field's own aggregator
 * (a sum for amounts), whatever the column shows. On lists laid out by this
 * module, ask the server for the column's function instead.
 */
patch(ListController.prototype, {
    get modelParams() {
        const params = super.modelParams;
        if (params.state || this.env.config?.viewArch?.getAttribute("bs_layout") !== "1") {
            return params;
        }
        const fields = { ...params.config.fields };
        for (const column of this.archInfo.columns) {
            const aggregate = column.type === "field" && columnAggregate(column);
            const field = aggregate && fields[column.name];
            if (field?.aggregator && field.aggregator !== aggregate) {
                // copy: the field descriptions are shared with the other views
                fields[column.name] = { ...field, aggregator: aggregate };
            }
        }
        params.config = { ...params.config, fields };
        return params;
    },
});

/**
 * Grouped lists compute the footer from the group totals. That is right for sum,
 * min and max, but an average of group averages ignores the group sizes: weight
 * them by record count.
 */
patch(ListRenderer.prototype, {
    /**
     * Name of a footer total that is not a sum: the list only shows the value,
     * so a minimum or an average would read as a total.
     */
    bsAggregateLabel(column) {
        const attrs = column.attrs || {};
        if (attrs.sum) {
            return "";
        }
        return (attrs.avg && _t("Avg")) || (attrs.min && _t("Min")) || (attrs.max && _t("Max")) || "";
    },

    computeAggregates() {
        const aggregates = super.computeAggregates(...arguments);
        const list = this.props.list;
        if (!this.bsIsViewManagerEnabled() || !list.isGrouped || list.selection.length) {
            return aggregates;
        }
        const formatters = registry.category("formatters");
        for (const column of this.columns) {
            const aggregate = aggregates[column.name];
            if (column.type !== "field" || columnAggregate(column) !== "avg" || !aggregate || aggregate.multiCurrency) {
                continue;
            }
            let total = 0;
            let count = 0;
            for (const group of list.groups) {
                const value = group.aggregates[column.name];
                if (value || value === 0) {
                    total += value * group.count;
                    count += group.count;
                }
            }
            if (!count) {
                continue;
            }
            const field = this.fields[column.name];
            const formatter = formatters.get(column.widget, false) || formatters.get(field.type, false);
            const formatOptions = {
                ...(formatter?.extractOptions?.(column) || {}),
                digits: column.attrs.digits ? JSON.parse(column.attrs.digits) : undefined,
                escape: true,
            };
            if (field.type === "monetary" || column.widget === "monetary") {
                const currencyField = this.getCurrencyField(column);
                const currencies = list.groups.find((group) => group.aggregates[currencyField]?.length);
                if (currencies) {
                    formatOptions.currencyId = currencies.aggregates[currencyField][0];
                }
            }
            aggregate.rawValue = total / count;
            aggregate.value = formatter ? formatter(aggregate.rawValue, formatOptions) : aggregate.rawValue;
        }
        return aggregates;
    },
});
