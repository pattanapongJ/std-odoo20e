import { patch } from "@web/core/utils/patch";
import { SIZES } from "@web/core/ui/ui_utils";
import { session } from "@web/session";
import { FormCompiler } from "@web/views/form/form_compiler";
import { FormController } from "@web/views/form/form_controller";
import { FormRenderer } from "@web/views/form/form_renderer";

const position = session.bs_chatter_position || "auto";

/** Whether the chatter goes beside the form for this screen size. */
export function isChatterAside(size) {
    if (position === "bottom") {
        return false;
    }
    if (position === "side") {
        return size >= SIZES.LG;
    }
    return size >= SIZES.XXL;
}

const STANDARD_SIZE_TEST = `__comp__.uiService.size < ${SIZES.XXL}`;

patch(FormCompiler.prototype, {
    compileForm(el, params) {
        const form = super.compileForm(el, params);
        const classes = form.getAttribute("t-attf-class");
        if (position !== "auto" && classes?.includes(STANDARD_SIZE_TEST)) {
            form.setAttribute(
                "t-attf-class",
                classes.replace(STANDARD_SIZE_TEST, "!__comp__.bsChatterAside()")
            );
        }
        return form;
    },
});

patch(FormRenderer.prototype, {
    bsChatterAside() {
        return isChatterAside(this.uiService.size);
    },
    mailLayout(hasAttachmentContainer) {
        if (position === "auto") {
            return super.mailLayout(hasAttachmentContainer);
        }
        // Same decision tree as mail's mailLayout, with the size test swapped.
        const aside = this.bsChatterAside();
        const hasFile = this.hasFile();
        if (this.mailPopoutService.externalWindow && hasFile && hasAttachmentContainer) {
            return aside ? "EXTERNAL_COMBO_XXL" : "EXTERNAL_COMBO";
        }
        if (this.mailStore) {
            if (aside) {
                return hasAttachmentContainer && hasFile ? "COMBO" : "SIDE_CHATTER";
            }
            return "BOTTOM_CHATTER";
        }
        return "NONE";
    },
});

patch(FormController.prototype, {
    get className() {
        const result = super.className;
        if (position !== "auto" && !this.env.inDialog) {
            const aside = isChatterAside(this.ui.size);
            delete result["o_xxl_form_view h-100"];
            if (aside) {
                result["o_xxl_form_view h-100"] = true;
            }
        }
        return result;
    },
});
