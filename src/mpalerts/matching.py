import re
from dataclasses import dataclass, field

SNIPPET_RADIUS = 120


def compile_term(term):
    """Compile a config keyword into a regex.

    "re:..." is used verbatim. Otherwise the phrase must start and end on a word
    boundary (allowing a plural s/es), and spaces/hyphens in it are optional.
    """
    term = str(term)
    if term.startswith("re:"):
        return re.compile(term[3:], re.IGNORECASE)
    words = [re.escape(w) for w in re.split(r"[\s\-]+", term.strip()) if w]
    body = r"[\s\-]*".join(words)
    return re.compile(rf"(?<![a-z0-9]){body}(?:e?s)?(?![a-z0-9])", re.IGNORECASE)


def compile_terms(terms):
    return [compile_term(t) for t in terms]


def any_match(patterns, text):
    for p in patterns:
        m = p.search(text)
        if m:
            return m
    return None


@dataclass
class Watch:
    name: str
    keywords: list
    require: list = field(default_factory=list)
    exclude: list = field(default_factory=list)

    def match(self, text):
        """Return the keyword match object if `text` satisfies this watch, else None."""
        m = any_match(self.keywords, text)
        if not m:
            return None
        if not all(p.search(text) for p in self.require):
            return None
        if any_match(self.exclude, text):
            return None
        return m


def snippet(text, m):
    start = max(0, m.start() - SNIPPET_RADIUS)
    end = min(len(text), m.end() + SNIPPET_RADIUS)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix
