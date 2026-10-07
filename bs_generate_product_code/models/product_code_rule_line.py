# -*- coding: utf-8 -*-

import html
import logging
import re
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.sql import escape_like_value

_logger = logging.getLogger(__name__)

# Markup reaches a reference through html and text fields, and would carry
# angle brackets straight into an internal reference.
HTML_TAG = re.compile(r"<[^>]+>")

# An internal reference is printed on labels and carried by other systems, so
# a mistyped Length must not be able to build a thousand-character one.
MAX_LENGTH = 64

# The placeholders of ir.sequence, so they read the same here. They are filled
# from the day the product was created rather than today: a reference is
# master data, and must not change with the calendar.
DATE_FORMATS = {
    "year": "%Y", "y": "%y", "month": "%m", "day": "%d",
    "doy": "%j", "woy": "%W", "weekday": "%w",
    "h24": "%H", "h12": "%I", "min": "%M", "sec": "%S",
    "isoyear": "%G", "isoy": "%g", "isoweek": "%V",
}
# Only %(key)s is a placeholder, so a lone % - "50%" - stays as typed.
PLACEHOLDER = re.compile(r"%\((\w+)\)s")


class UnreadablePath(Exception):
    """A part names a field path that no longer reads.

    Building the reference without that part would hand the product a
    shorter one, and a running number from another sequence, so the product
    is left alone instead.
    """


class ProductCodeRuleLine(models.Model):
    """One piece of a generated reference."""

    _name = "product.code.rule.line"
    _description = "Product Code Rule Part"
    _order = "sequence, id"
    # A part is what names a field, so editing one changes the watched set as
    # surely as editing the rule it belongs to.
    _clear_cache_name = "default"

    rule_id = fields.Many2one("product.code.rule", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)

    value_type = fields.Selection(
        [
            ("field", "Product Field"),
            ("text", "Fixed Text"),
            ("number", "Running Number"),
        ],
        string="Source",
        default="field",
        required=True,
    )
    # Held as a dotted path so related models can be walked, the way Odoo's own
    # export dialog does. The widget writes it; nothing needs to parse it here
    # beyond splitting on the dots.
    field_path = fields.Char(string="Field")
    res_model = fields.Char(default="product.product", readonly=True)
    text = fields.Char(
        string="Text",
        help="May hold date placeholders such as %(year)s, filled from the day "
        "the product was created.",
    )

    prefix = fields.Char(
        help="May hold date placeholders such as %(year)s, filled from the day "
        "the product was created.",
    )
    suffix = fields.Char(
        help="May hold date placeholders such as %(year)s, filled from the day "
        "the product was created.",
    )
    separate_with = fields.Char(
        string="Separate With",
        help="Placed between the values when this part reads a list of "
        "records and finds several. Without it they run together.",
    )
    is_multi_value = fields.Boolean(
        compute="_compute_is_multi_value",
        help="Whether the chosen field can hold several values, which is when "
        "a separator is worth setting.",
    )

    @api.depends("value_type", "field_path")
    def _compute_is_multi_value(self):
        for line in self:
            line.is_multi_value = line._path_crosses_a_list()

    def _path_crosses_a_list(self):
        """True when the path steps through a one2many or many2many.

        Only those can yield several values, so only those have anything to
        separate.
        """
        self.ensure_one()
        if self.value_type != "field":
            return False
        current = self.env["product.product"]
        for part in (self.field_path or "").strip().split("."):
            field = current._fields.get(part) if part else None
            if not field:
                return False
            if field.type in ("one2many", "many2many"):
                return True
            if not field.relational:
                return False
            current = self.env[field.comodel_name]
        return False

    transform = fields.Selection(
        [
            ("none", "As is"),
            ("upper", "UPPERCASE"),
            ("lower", "lowercase"),
            ("digits", "Digits only"),
            ("truncate", "First characters"),
            ("pad", "Pad with zeros"),
        ],
        default="none",
        required=True,
    )
    length = fields.Integer(
        string="Length",
        default=3,
        help="Number of characters kept by First characters, or the width "
        "reached by Pad with zeros. A Running Number is padded to this width.",
    )
    start_number = fields.Integer(
        string="Start At",
        default=1,
        help="The number given to the first product with a new reference.",
    )

    def _uses_length(self):
        return self.value_type == "number" or self.transform in ("truncate", "pad")

    @api.constrains("transform", "length", "value_type")
    def _check_length(self):
        """A Length of zero silently deletes the part, and an oversized one
        writes an unusable reference - neither should reach a product."""
        for line in self.filtered(lambda part: part._uses_length()):
            if line.length < 1:
                raise ValidationError(
                    self.env._(
                        "%(transform)s needs a Length of at least 1 on the "
                        "%(rule)s rule.",
                        transform=(
                            dict(self._fields["value_type"].selection)["number"]
                            if line.value_type == "number"
                            else dict(self._fields["transform"].selection)[
                                line.transform
                            ]
                        ),
                        rule=line.rule_id.name,
                    )
                )
            if line.length > MAX_LENGTH:
                raise ValidationError(
                    self.env._(
                        "A Length of %(length)s would build an unusable "
                        "reference; %(max)s is the most allowed.",
                        length=line.length,
                        max=MAX_LENGTH,
                    )
                )

    @api.constrains("value_type", "field_path")
    def _check_source(self):
        for line in self.filtered(lambda l: l.value_type == "field"):
            if not line.field_path:
                raise ValidationError(
                    self.env._("Choose a field for the %s part.", line.rule_id.name)
                )
            if not line._path_exists():
                raise ValidationError(
                    self.env._(
                        "The %(rule)s rule reads %(path)s, which is not a field "
                        "of the product.",
                        rule=line.rule_id.name,
                        path=line.field_path,
                    )
                )

    def _path_exists(self):
        current = self.env["product.product"]
        steps = (self.field_path or "").strip().split(".")
        for index, step in enumerate(steps):
            field = current._fields.get(step)
            if not field:
                return False
            if index < len(steps) - 1:
                if not field.relational:
                    return False
                current = self.env[field.comodel_name]
        return True

    @api.constrains("prefix", "suffix", "text")
    def _check_placeholders(self):
        for line in self:
            for text in (line.prefix, line.suffix, line.text):
                unknown = set(PLACEHOLDER.findall(text or "")) - DATE_FORMATS.keys()
                if unknown:
                    raise ValidationError(self.env._(
                        "The %(rule)s rule uses %(unknown)s, which is not a date "
                        "placeholder. Use one of: %(known)s.",
                        rule=line.rule_id.name,
                        unknown=", ".join(f"%({key})s" for key in sorted(unknown)),
                        known=", ".join(f"%({key})s" for key in DATE_FORMATS),
                    ))

    def _creation_moment(self, product):
        """When ``product`` was created, in its creator's time zone.

        Neither the viewer's time zone nor today's date is used, so rendering
        the reference again later, or as someone else, gives the same one.
        """
        if not product:
            # Only checks run without a product; any date serves them.
            return datetime.now(self.env.tz)
        try:
            zone = ZoneInfo(product.sudo().create_uid.tz or "UTC")
        except (ZoneInfoNotFoundError, ValueError):
            zone = UTC
        moment = (
            product.create_date.replace(tzinfo=UTC)
            if product.create_date
            else datetime.now(UTC)
        )
        return moment.astimezone(zone)

    def _interpolate(self, text, product):
        """``text`` with its date placeholders filled in for ``product``."""
        if not text or not PLACEHOLDER.search(text):
            return text or ""
        moment = self._creation_moment(product)
        return PLACEHOLDER.sub(
            lambda match: moment.strftime(DATE_FORMATS[match.group(1)])
            if match.group(1) in DATE_FORMATS
            else match.group(0),
            text,
        )

    def _is_constant(self):
        """Whether this part renders the same for every product."""
        return self.value_type == "text" and not any(
            PLACEHOLDER.search(text or "")
            for text in (self.text, self.prefix, self.suffix)
        )

    @api.constrains("value_type", "rule_id")
    def _check_one_number(self):
        for rule in self.filtered(lambda l: l.value_type == "number").rule_id:
            if len(rule.line_ids.filtered(lambda l: l.value_type == "number")) > 1:
                raise ValidationError(
                    self.env._(
                        "The %s rule can have only one Running Number part.",
                        rule.name,
                    )
                )

    @api.constrains("value_type", "start_number")
    def _check_start_number(self):
        for line in self.filtered(
            lambda l: l.value_type == "number" and l.start_number < 0
        ):
            raise ValidationError(
                self.env._(
                    "A Running Number cannot start below zero on the %s rule.",
                    line.rule_id.name,
                )
            )

    @api.constrains("value_type", "prefix", "suffix", "sequence", "text", "transform")
    def _check_number_boundary(self):
        """A running number must not run into digits that vary.

        Numbers are found again by reading the digits between the rest of the
        reference, so ``DEM-18`` numbered ``001`` gives ``DEM-18001`` - which
        also reads as number ``01`` of ``DEM-180``. Such a number would be
        counted in the wrong sequence. A letter or symbol on each side, or
        fixed text there, keeps every sequence apart.
        """
        for rule in self.rule_id:
            lines = rule.line_ids.sorted()
            for index, line in enumerate(lines):
                if line.value_type != "number":
                    continue
                if not line._number_side_is_safe(
                    lines[:index], line.prefix, lambda text: text[-1:]
                ):
                    raise ValidationError(self.env._(
                        "The Running Number of the %s rule follows a part whose "
                        "value can end in a digit. Give it a Prefix that ends "
                        "in a letter or symbol, such as '-'.",
                        rule.name,
                    ))
                if not line._number_side_is_safe(
                    list(reversed(lines[index + 1:])), line.suffix,
                    lambda text: text[:1],
                ):
                    raise ValidationError(self.env._(
                        "The Running Number of the %s rule is followed by a part "
                        "whose value can start with a digit. Give it a Suffix "
                        "that starts with a letter or symbol, such as '-'.",
                        rule.name,
                    ))

    def _number_side_is_safe(self, parts, own_text, edge):
        """Whether the text on one side of the number keeps it apart.

        ``parts`` lists that side's parts with the nearest one last, and
        ``edge`` picks the character touching the number. A date placeholder
        varies like a field, and always ends in digits.
        """
        sample = self.env["product.product"]
        if all(part._is_constant() for part in parts) and not PLACEHOLDER.search(
            own_text or ""
        ):
            # Fixed text renders the same for every product: one sequence.
            return True
        if own_text:
            return not edge(self._interpolate(own_text, sample)).isdigit()
        nearest = parts[-1]
        if nearest.value_type != "text":
            return False
        rendered = nearest._render(sample)
        return bool(rendered) and not edge(rendered).isdigit()

    def _render_number(self, product, before, after, counters=None):
        """The full reference, numbered after the other products sharing it.

        The number counts per reference rather than per rule: every product
        whose other parts render the same continues one sequence, so
        ``DEM-18-001`` and ``DEM-25-001`` can both exist. A product already
        holding a number in its own sequence keeps it, which is what lets the
        write path tell a generated reference from a typed one.
        """
        self.ensure_one()
        head = before + self._interpolate(self.prefix, product)
        tail = self._interpolate(self.suffix, product) + after
        pattern = re.compile(re.escape(head) + r"(\d+)" + re.escape(tail))
        # Archived products and other companies' products still hold their
        # references, and a number must not be handed out twice.
        Product = self.env["product.product"].sudo().with_context(active_test=False)

        current = product.default_code or ""
        if pattern.fullmatch(current) and not Product.search_count(
            [("default_code", "=", current), ("id", "!=", product.id)], limit=1
        ):
            return current

        key = (self.id, head, tail)
        if counters is not None and key in counters:
            last = counters[key]
        else:
            codes = Product.search_fetch(
                [
                    ("default_code", "=like",
                     f"{escape_like_value(head)}%{escape_like_value(tail)}"),
                    ("id", "!=", product.id),
                ],
                ["default_code"],
            ).mapped("default_code")
            numbers = [
                int(match.group(1))
                for match in map(pattern.fullmatch, codes)
                if match
            ]
            last = max(numbers, default=self.start_number - 1)
        number = max(last + 1, self.start_number)
        if counters is not None:
            counters[key] = number
        return f"{head}{str(number).rjust(self.length, '0')}{tail}"

    def _render(self, product):
        """This part's contribution, or '' when it has nothing to say."""
        self.ensure_one()
        # The transform runs on each value, not on the joined string: running
        # it after the join would let Digits only eat the separator, and would
        # pad or truncate the whole run instead of each value.
        pieces = [
            piece
            for piece in (
                self._apply_transform(raw) for raw in self._raw_pieces(product)
            )
            if piece
        ]
        if not pieces:
            # A part that resolves to nothing contributes nothing at all, so a
            # missing value does not leave a stray prefix behind.
            return ""
        value = (self.separate_with or "").join(pieces)
        prefix = self._interpolate(self.prefix, product)
        suffix = self._interpolate(self.suffix, product)
        return f"{prefix}{value}{suffix}"

    def _raw_pieces(self, product):
        """Every value this part reads, before any formatting."""
        if self.value_type == "text":
            return [self._interpolate(self.text, product)]
        if self.value_type == "number":
            # Numbered by the rule, which knows the rest of the reference.
            return []
        return self._field_pieces(product)

    def _field_pieces(self, product):
        """Read a dotted path, the way the export dialog writes them.

        Uses ``mapped`` rather than walking the path by hand: a step through a
        one2many or many2many yields several records, and reading a field off
        those directly raises "Expected singleton". A path that crosses such a
        step contributes every value it finds, in order.
        """
        path = (self.field_path or "").strip()
        if not path:
            return []
        try:
            values = product.mapped(path)
        except Exception as error:
            _logger.warning(
                "Rule part %s cannot read path %r on %s",
                self.id,
                path,
                product._name,
            )
            raise UnreadablePath(path) from error
        if isinstance(values, models.Model):
            values = values.mapped("display_name")
        return [
            piece for piece in (self._format_value(value) for value in values) if piece
        ]

    @staticmethod
    def _format_value(value):
        """Turn one raw field value into something safe for a reference.

        A user picks fields with the same picker Odoo uses everywhere, so any
        type can arrive here. Whitespace and markup are always removed - a
        newline in an internal reference breaks reports, exports and barcodes.
        Dates become compact digits, since a year or a month is a reasonable
        thing to build a code from and their written form is not.
        """
        if value is None or value is False:
            return ""
        if value is True:
            # A boolean has no meaningful place in a reference, and the word
            # "True" certainly has none.
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y%m%d")
        if isinstance(value, date):
            return value.strftime("%Y%m%d")
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        text = HTML_TAG.sub(" ", str(value))
        return " ".join(html.unescape(text).split())

    def _apply_transform(self, value):
        value = (value or "").strip()
        if not value or self.transform == "none":
            return value
        if self.transform == "upper":
            return value.upper()
        if self.transform == "lower":
            return value.lower()
        if self.transform == "digits":
            return "".join(character for character in value if character.isdigit())
        if self.transform == "truncate":
            return value[: max(self.length, 0)]
        if self.transform == "pad":
            return value.rjust(max(self.length, 0), "0")
        return value
