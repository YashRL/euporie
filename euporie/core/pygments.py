"""Contains lexers for pygments."""

from __future__ import annotations

from pygments.lexer import RegexLexer
from pygments.style import Style
from pygments.token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Name,
    Number,
    Operator,
    String,
    Text,
)


class ArgparseLexer(RegexLexer):
    """A pygments lexer for agrparse help text."""

    name = "argparse"
    aliases = ["argparse"]
    filenames: "list[str]" = []

    tokens = {
        "root": [
            (r"(?<=usage: )[^\s]+", Name.Namespace),
            (r"\{", Operator, "options"),
            (r"[\[\{\|\}\]]", Operator),
            (r"((?<=\s)|(?<=\[))(--[a-zA-Z0-9-]+|-[a-zA-Z0-9-])", Keyword),
            (r"^(\w+\s)?\w+:", Generic.Heading),
            (r"\b(str|int|bool|UPath|loads)\b", Name.Builtin),
            (r"\b[A-Z]+_[A-Z]*\b", Name.Variable),
            (r"'.*?'", String),
            (r".", Text),
        ],
        "options": [
            (r"\d+", Number),
            (r",", Text),
            (r"[^\}]", String),
            (r"\}", Operator, "#pop"),
        ],
    }


class EuporiePygmentsStyle(Style):
    """Version of pygment's "native" style which works better on light backgrounds."""

    styles = {
        Comment: "italic #888888",
        Comment.Preproc: "noitalic bold #cd2828",
        Comment.Special: "noitalic bold #e50808 bg:#520000",
        Keyword: "bold #6ebf26",
        Keyword.Pseudo: "nobold",
        Operator.Word: "bold #6ebf26",
        String: "#ed9d13",
        String.Other: "#ffa500",
        Number: "#51b2fd",
        Name.Builtin: "#2fbccd",
        Name.Variable: "#40ffff",
        Name.Constant: "#40ffff",
        Name.Class: "underline #71adff",
        Name.Function: "#71adff",
        Name.Namespace: "underline #71adff",
        Name.Exception: "noinherit bold",
        Name.Tag: "bold #6ebf26",
        Name.Attribute: "noinherit",
        Name.Decorator: "#ffa500",
        Generic.Heading: "bold",
        Generic.Subheading: "underline",
        Generic.Deleted: "#d22323",
        Generic.Inserted: "#589819",
        Generic.Error: "#d22323",
        Generic.Emph: "italic",
        Generic.Strong: "bold",
        Generic.Traceback: "#d22323",
        Error: "bg:#e3d2d2 #a61717",
    }
