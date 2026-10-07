import { patch } from "@web/core/utils/patch";
import { TourHelpers } from "@web_tour/tour_helpers/tour_helpers";

// Odoo 20's helper dereferences clipboard at import time, breaking HTTP tours.
// Keep this replacement outside static/src so it only loads with tour helpers.
const clipboard = window.navigator.clipboard;
const originalClipboardWriteText = clipboard?.writeText;

patch(TourHelpers.prototype, {
    allowClipboardWrite() {
        if (clipboard) {
            clipboard.writeText = () => Promise.resolve();
        }
    },
    restoreClipboardWrite() {
        if (clipboard) {
            clipboard.writeText = originalClipboardWriteText;
        }
    },
});
