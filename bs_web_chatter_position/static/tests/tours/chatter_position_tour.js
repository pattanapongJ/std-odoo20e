import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("bs_chatter_position_side", {
    steps: () => [
        { trigger: ".o_form_view.o_xxl_form_view .o-mail-Form-chatter.o-aside" },
    ],
});

registry.category("web_tour.tours").add("bs_chatter_position_bottom", {
    steps: () => [
        { trigger: ".o_form_view:not(.o_xxl_form_view) .o_form_renderer.flex-column .o-mail-Form-chatter:not(.o-aside)" },
    ],
});
