import { AutoComplete } from "@web/core/autocomplete/autocomplete";
import { useDateTimePicker } from "@web/core/datetime/datetime_picker_hook";
import { Domain } from "@web/core/domain";
import { _t } from "@web/core/l10n/translation";
import { SelectMenu } from "@web/core/select_menu/select_menu";
import { useService } from "@web/core/utils/hooks";

import { Component, signal, t, useProps } from "@odoo/owl";
import {
    choiceOptions,
    containsFilter,
    dateRangeFilter,
    exactFilter,
    getFilterKind,
    numberFilter,
} from "./filter_domain";

const SUGGESTION_LIMIT = 8;

/**
 * One cell of the filter row. The applied value is not kept here: it is read
 * back from the search facet (`active`), so removing the facet in the search
 * bar clears the cell and the cell survives a re-render.
 */
export class BsColumnFilter extends Component {
    static template = "bs_view_manager.ColumnFilter";
    static components = { AutoComplete, SelectMenu };
    props = useProps({
        resModel: t.string(),
        fieldName: t.string(),
        field: t.object(),
        label: t.string(),
        active: t.object().optional(),
        getSuggestionDomain: t.function(),
        onApply: t.function(),
        onClear: t.function(),
    });

    dateTargetRef = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.kind = getFilterKind(this.props.field);
        this.sources = [{ options: (term) => this.loadOptions(term), optionSlot: "option" }];
        if (this.kind === "date") {
            this.datePicker = useDateTimePicker({
                target: this.dateTargetRef,
                pickerProps: { type: "date", range: true, value: [false, false] },
                onApply: (value) => this.onDateApply(value),
            });
        }
    }

    canSuggest() {
        const field = this.props.field;
        return Boolean(field.store && field.groupable);
    }

    async loadOptions(term) {
        const { fieldName, field, label } = this.props;
        const text = (term || "").trim();
        const options = [];
        if (text) {
            options.push({
                label: _t("Contains \"%s\"", text),
                onSelect: () => this.props.onApply(containsFilter(fieldName, label, text)),
            });
        }
        if (this.canSuggest()) {
            const domain = Domain.and([
                this.props.getSuggestionDomain(),
                text ? [[fieldName, "ilike", text]] : [],
            ]).toList();
            const groups = await this.orm.formattedReadGroup(
                this.props.resModel,
                domain,
                [fieldName],
                ["__count"],
                { limit: SUGGESTION_LIMIT, order: "__count desc" }
            );
            for (const group of groups) {
                const value = group[fieldName];
                if (value === false || value === null || value === undefined) {
                    continue;
                }
                const [key, valueLabel] = Array.isArray(value) ? value : [value, String(value)];
                options.push({
                    label: valueLabel,
                    data: { count: group.__count },
                    onSelect: () =>
                        this.props.onApply(exactFilter(fieldName, field, label, key, valueLabel)),
                });
            }
        }
        if (!options.length) {
            options.push({ label: _t("No values") });
        }
        return options;
    }

    onNumberKeydown(ev) {
        if (ev.key !== "Enter") {
            return;
        }
        ev.preventDefault();
        const filter = numberFilter(this.props.fieldName, this.props.label, ev.target.value);
        if (filter === false) {
            this.notification.add(
                _t("Type a number, optionally after <, >, <=, >= or != (for example >100)."),
                { type: "warning" }
            );
        } else if (filter) {
            this.props.onApply(filter);
        } else if (this.props.active) {
            this.props.onClear();
        }
    }

    openDatePicker() {
        this.datePicker.open(0);
    }

    onDateApply(value) {
        const [start, end] = Array.isArray(value) ? value : [value, value];
        if (!start) {
            return;
        }
        const { fieldName, field, label } = this.props;
        this.props.onApply(dateRangeFilter(fieldName, field, label, start, end || start));
    }

    choices() {
        return choiceOptions(this.props.field);
    }

    onChoiceSelect(value) {
        const { fieldName, field, label } = this.props;
        const choice = this.choices().find((option) => option.value === value);
        if (!choice) {
            this.props.onClear();
            return;
        }
        this.props.onApply(exactFilter(fieldName, field, label, choice.value, choice.label));
    }
}
