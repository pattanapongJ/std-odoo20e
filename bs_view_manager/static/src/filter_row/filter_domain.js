import { formatDate, serializeDate, serializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";

const NUMBER_RE = /^(<=|>=|!=|<|>|=)?\s*(-?\d+(?:[.,]\d+)?)$/;

/**
 * Input kind of the filter cell for a field, or null when the column cannot be
 * filtered from the list header.
 */
export function getFilterKind(field) {
    switch (field?.type) {
        case "char":
        case "text":
        case "many2one":
        case "many2many":
            return "text";
        case "integer":
        case "float":
        case "monetary":
            return "number";
        case "date":
        case "datetime":
            return "date";
        case "selection":
        case "boolean":
            return "choice";
    }
    return null;
}

/** Filter matching records whose field contains the typed text. */
export function containsFilter(fieldName, label, text) {
    return {
        domain: [[fieldName, "ilike", text]],
        description: _t("%(field)s contains \"%(value)s\"", { field: label, value: text }),
        display: text,
    };
}

/** Filter matching one exact value picked from the suggestions. */
export function exactFilter(fieldName, field, label, value, valueLabel) {
    let domain;
    if (field.type === "many2many") {
        domain = [[fieldName, "in", [value]]];
    } else {
        domain = [[fieldName, "=", value]];
    }
    return { domain, description: `${label}: ${valueLabel}`, display: valueLabel, value };
}

/**
 * Filter for a number typed with an optional operator, e.g. ">100".
 *
 * @returns {Object | null | false} null when empty, false when not a number
 */
export function numberFilter(fieldName, label, text) {
    const value = text.trim();
    if (!value) {
        return null;
    }
    const match = value.match(NUMBER_RE);
    if (!match) {
        return false;
    }
    const operator = match[1] || "=";
    return {
        domain: [[fieldName, operator, Number(match[2].replace(",", "."))]],
        description: `${label} ${operator} ${match[2]}`,
        display: value,
    };
}

/** Filter for a range of days; datetimes cover the user's whole days. */
export function dateRangeFilter(fieldName, field, label, start, end) {
    const [from, to] = start <= end ? [start, end] : [end, start];
    const bounds =
        field.type === "date"
            ? [serializeDate(from), serializeDate(to)]
            : [serializeDateTime(from.startOf("day")), serializeDateTime(to.endOf("day"))];
    const text = from.hasSame(to, "day")
        ? formatDate(from)
        : `${formatDate(from)} - ${formatDate(to)}`;
    return {
        domain: [
            [fieldName, ">=", bounds[0]],
            [fieldName, "<=", bounds[1]],
        ],
        description: `${label}: ${text}`,
        display: text,
    };
}

/** Choices of a selection or boolean column. */
export function choiceOptions(field) {
    if (field.type === "boolean") {
        return [
            { value: true, label: _t("Yes") },
            { value: false, label: _t("No") },
        ];
    }
    return (field.selection || []).map(([value, label]) => ({ value, label }));
}
