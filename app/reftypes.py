"""Reference types of the house bibliography style and how each one is written.

Each type has a list of fields (the dialog is built from them) and a function
that turns the filled-in fields into the LaTeX text of one bibliography entry.
Line breaks inside an entry (ISBN, ISSN, a chapter line) use \\newline.

The rules follow the style guide, e.g.

  llibre   BRAGÓS BARDIA, Ramon ... [et al.]. Circuitos y dispositivos electrónicos:
           fundamentos de electrónica. 4ª ed. Barcelona: Edicions UPC, 1994. 463 p.
           (Politext; 35). / ISBN 84-8301-215-4
  article  KENNARD, L. “Novell certificate server 2.0: …?”. Netware connection.
           Vol. 11 (2000), núm. 1, p. 6-20. / ISSN 1076-3422.
  web      SIEMENS (Pàgina consultada l’11 de febrer de 2000). SIEMENS. Productos y
           soluciones, [En línia]. Adreça URL: http://…

Authors are typed as "Cognoms, Nom; Cognoms, Nom": the surnames are put in capitals.
Straight apostrophes become typographic ones (l'euro -> l’euro).
"""

import re
from datetime import date

from .errors import UserError

MONTHS = ["gener", "febrer", "març", "abril", "maig", "juny", "juliol", "agost",
          "setembre", "octubre", "novembre", "desembre"]

LATEX_SPECIALS = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}

NEWLINE = " \\newline "


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _of_month(month: str) -> str:
    return f"d’{month}" if month[0] in "aeiou" else f"de {month}"


def catalan_date(d: date) -> str:
    """Web pages: 'l’11 de febrer de 2000', 'el 2 d’abril de 2024'."""
    day = f"l’{d.day}" if d.day in (1, 11) else f"el {d.day}"
    return f"{day} {_of_month(MONTHS[d.month - 1])} de {d.year}"


def newspaper_date(d: date) -> str:
    """Newspapers: '10 de febrer del 2000'."""
    return f"{d.day} {_of_month(MONTHS[d.month - 1])} del {d.year}"


def gazette_date(d: date) -> str:
    """Official publications: '4 desembre 1996'."""
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def escape_latex(text: str) -> str:
    return "".join(LATEX_SPECIALS.get(ch, ch) for ch in text)


def _text(fields: dict, name: str) -> str:
    """Field value: whitespace collapsed, typographic apostrophes, LaTeX-escaped."""
    value = re.sub(r"\s+", " ", str(fields.get(name) or "")).strip()
    return escape_latex(value.replace("'", "’"))


def _required(fields: dict, name: str, label: str) -> str:
    value = _text(fields, name)
    if not value:
        raise UserError(f"“{label}” is required.")
    return value


def _end(part: str) -> str:
    """A part of the reference ends with a period (unless it already ends in . ? or !)."""
    return part if part.endswith((".", "?", "!")) else part + "."


def _sentences(*parts: str) -> str:
    return " ".join(_end(p) for p in parts if p)


def _authors(fields: dict, upper_surnames: bool = True) -> str:
    """'Bragós Bardia, Ramon; Pérez, J.' -> 'BRAGÓS BARDIA, Ramon; PÉREZ, J.' (+ ' ... [et al.]')."""
    raw = re.sub(r"\s+", " ", str(fields.get("authors") or "")).strip()
    if not raw:
        return ""
    people = []
    for person in (p.strip() for p in raw.split(";") if p.strip()):
        if upper_surnames and "," in person:
            surname, given = person.split(",", 1)
            person = f"{surname.strip().upper()}, {given.strip()}"
        people.append(person)
    text = "; ".join(people)
    if fields.get("etal"):
        text += " ... [et al.]"
    return escape_latex(text.replace("'", "’"))


def _title(fields: dict, title: str = "title", subtitle: str = "subtitle", label: str = "Title") -> str:
    main, sub = _required(fields, title, label), _text(fields, subtitle)
    return f"{main}: {sub}" if sub else main


def _imprint(fields: dict, unknown_place: bool = False) -> str:
    """'Barcelona: Edicions UPC, 1994'; an empty place may be written [S.l.]."""
    place, publisher, year = _text(fields, "place"), _text(fields, "publisher"), _text(fields, "year")
    if not (place or publisher or year):
        return ""
    if not place and unknown_place:
        place = "[S.l.]"
    text = f"{place}: {publisher}" if place and publisher else place or publisher
    return f"{text}, {year}" if text and year else text or year


def _edition(fields: dict) -> str:
    edition = _text(fields, "edition")
    return f"{edition}ª ed." if edition.isdigit() else edition


def _extent_and_collection(fields: dict) -> str:
    """'463 p. (Politext; 35)'"""
    extent = _text(fields, "extent")
    if extent.isdigit():
        extent = f"{extent} p."
    collection, number = _text(fields, "collection"), _text(fields, "collection_number")
    series = f"({collection}; {number})" if collection and number else f"({collection})" if collection else ""
    return " ".join(p for p in (extent, series) if p)


def _numbering(fields: dict) -> str:
    """'Vol. 11 (2000), núm. 1, p. 6-20'"""
    volume, year = _text(fields, "volume"), _text(fields, "year")
    issue, pages = _text(fields, "issue"), _text(fields, "pages")
    first = f"Vol. {volume} ({year})" if volume and year else f"Vol. {volume}" if volume else f"({year})" if year else ""
    return ", ".join(p for p in (first, f"núm. {issue}" if issue else "", f"p. {pages}" if pages else "") if p)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

def _book(f: dict) -> str:
    text = _sentences(_authors(f) or _required(f, "authors", "Author(s)"), _title(f), _edition(f),
                      _imprint(f), _extent_and_collection(f))
    chapter, chapter_pages = _text(f, "chapter"), _text(f, "chapter_pages")
    if chapter:
        text += NEWLINE + _end(f"{chapter}: p. {chapter_pages}" if chapter_pages else chapter)
    isbn = _text(f, "isbn")
    return text + (NEWLINE + f"ISBN {isbn}" if isbn else "")


def _part(f: dict) -> str:
    whole = _sentences(_authors({"authors": f.get("book_authors")}), _title(f, "book_title", "book_subtitle", "Book title"),
                       _edition(f), _imprint(f), _extent_and_collection(f))
    text = _sentences(_authors(f) or _required(f, "authors", "Author(s)"),
                      f"“{_required(f, 'part_title', 'Title of the part')}”") + " A: " + whole
    pages = _text(f, "part_pages")
    if pages:
        text += f" P. {pages}."
    isbn = _text(f, "isbn")
    return text + (NEWLINE + f"ISBN {isbn}" if isbn else "")


def _standard(f: dict) -> str:
    return _sentences(_required(f, "entity", "Responsible body").upper(), _required(f, "title", "Title"),
                      _text(f, "code"), _edition(f), _imprint(f))


def _catalogue(f: dict) -> str:
    return _sentences(_required(f, "company", "Company").upper(), _required(f, "title", "Title"),
                      _imprint(f, unknown_place=True))


def _periodical(f: dict) -> str:
    place, issn = _text(f, "place"), _text(f, "issn")
    return _sentences(_title(f), f"[{place}]" if place else "", _text(f, "numbering"), f"ISSN {issn}" if issn else "")


def _article(f: dict) -> str:
    text = _sentences(_authors(f) or _required(f, "authors", "Author(s)"), f"“{_required(f, 'title', 'Article title')}”",
                      _required(f, "journal", "Journal"), _numbering(f))
    issn = _text(f, "issn")
    return text + (NEWLINE + f"ISSN {issn}." if issn else "")


def _newspaper(f: dict) -> str:
    paper, place = _required(f, "newspaper", "Newspaper"), _text(f, "place")
    issue, pages = _text(f, "issue"), _text(f, "pages")
    tail = paper + (f" [{place}]" if place else "") + f" ({_required(f, 'date', 'Date')})"
    tail += (f", núm. {issue}" if issue else "") + (f", p. {pages}" if pages else "")
    return _sentences(_authors(f), f"“{_required(f, 'title', 'Article title')}”", tail)


def _official(f: dict) -> str:
    title, issue, pages = _text(f, "title"), _text(f, "issue"), _text(f, "pages")
    tail = f"{_required(f, 'gazette', 'Publication')} ({_required(f, 'date', 'Date')})"
    tail += (f", núm. {issue}" if issue else "") + (f", p. {pages}" if pages else "")
    return _sentences(f"“{title}”" if title else "", tail)


def _web(f: dict) -> str:
    author = _required(f, "author", "Author")
    title = _required(f, "title", "Page title")
    medium = _text(f, "medium") or "En línia"
    url = re.sub(r"\s+", "", str(f.get("url") or ""))
    if not url:
        raise UserError("“URL” is required.")
    try:
        day = date.fromisoformat(str(f.get("consulted") or ""))
    except ValueError as exc:
        raise UserError("The consultation date is not valid.") from exc
    return (f"{author} (Pàgina consultada {catalan_date(day)}). {title}, [{medium}]. "
            f"Adreça URL: \\url{{{url}}}")


def _field(id, label, placeholder="", required=False, hint="", type="text", default=""):
    return {"id": id, "label": label, "placeholder": placeholder, "required": required,
            "hint": hint, "type": type, "default": default}


AUTHORS = _field("authors", "Author(s)", "Bragós Bardia, Ramon; Pérez, J.", True,
                 "Cognoms, Nom — several separated by ;  (surnames are capitalised)")
ETAL = _field("etal", "More authors", type="checkbox", hint="adds “... [et al.]”")
IMPRINT = [
    _field("place", "Place", "Barcelona"),
    _field("publisher", "Publisher", "Edicions UPC"),
    _field("year", "Year", "1994", True),
]
EXTENT = [
    _field("extent", "Pages / volumes", "463", hint="a number becomes “463 p.”"),
    _field("collection", "Collection", "Politext"),
    _field("collection_number", "Collection no.", "35"),
]


def types(today: date | None = None) -> list[dict]:
    """Reference types with their fields, for the dialog (dates default to today)."""
    today = today or date.today()
    return [
        {"id": "book", "label": "Llibre (book)", "fields": [
            AUTHORS, ETAL,
            _field("title", "Title", "Circuitos y dispositivos electrónicos", True),
            _field("subtitle", "Subtitle", "fundamentos de electrónica"),
            _field("edition", "Edition", "4ª ed.", hint="a number becomes “4ª ed.”"),
            *IMPRINT, *EXTENT,
            _field("chapter", "Chapter (same author)", "Capítol 3. Circuitos lineales",
                   hint="optional: cite one chapter of this book"),
            _field("chapter_pages", "Chapter pages", "35-57"),
            _field("isbn", "ISBN", "84-8301-215-4"),
        ]},
        {"id": "part", "label": "Part of a book (other author)", "fields": [
            AUTHORS, ETAL,
            _field("part_title", "Title of the part", "L’euro, la moneda del segle XXI", True),
            _field("book_authors", "Book author(s)", "", hint="if different and known"),
            _field("book_title", "Book title", "L’impacte de l’euro als mercats financers", True),
            _field("book_subtitle", "Book subtitle"),
            _field("edition", "Edition", "", hint="a number becomes “2ª ed.”"),
            _field("place", "Place", "Barcelona"), _field("publisher", "Publisher", "La Caixa"),
            _field("year", "Year", "1998", True),
            _field("extent", "Pages / volumes", "276"),
            _field("collection", "Collection", "Estudis i informes"), _field("collection_number", "Collection no.", "14"),
            _field("part_pages", "Pages of the part", "13-37"),
            _field("isbn", "ISBN"),
        ]},
        {"id": "standard", "label": "Norma (standard)", "fields": [
            _field("entity", "Responsible body", "Asociación Española de Normalización y Certificación", True,
                   "written in capitals"),
            _field("title", "Title", "Términos generales y sus definiciones…", True),
            _field("code", "Code", "UNE 0-007-91", hint="if not part of the title"),
            _field("edition", "Edition"),
            _field("place", "Place", "Madrid"), _field("publisher", "Publisher", "AENOR"),
            _field("year", "Year", "1991", True),
        ]},
        {"id": "catalogue", "label": "Catàleg comercial (catalogue)", "fields": [
            _field("company", "Company", "Ariston", True, "written in capitals"),
            _field("title", "Title", "Catálogo general núm. 8", True),
            _field("place", "Place", "Madrid; Barcelona", hint="empty: [S.l.]"),
            _field("publisher", "Publisher", "Ariston"),
            _field("year", "Year", "1999", hint="estimated: [1999]"),
        ]},
        {"id": "periodical", "label": "Publicació periòdica (journal as a whole)", "fields": [
            _field("title", "Title", "Electronic design", True),
            _field("subtitle", "Subtitle", "technology applications, products, solutions"),
            _field("place", "Place of publication", "Cleveland", hint="shown in [ ]"),
            _field("numbering", "Volume / issue", "Vol. 47 (1999), 26"),
            _field("issn", "ISSN", "0013-4872"),
        ]},
        {"id": "article", "label": "Article de revista (journal article)", "fields": [
            AUTHORS, ETAL,
            _field("title", "Article title", "Novell certificate server 2.0: is your network certifiably secure?", True),
            _field("journal", "Journal", "Netware connection", True),
            _field("volume", "Volume", "11"), _field("year", "Year", "2000"),
            _field("issue", "Issue no.", "1"), _field("pages", "Pages", "6-20", hint="first-last"),
            _field("issn", "ISSN", "1076-3422", hint="optional"),
        ]},
        {"id": "newspaper", "label": "Article de diari (newspaper)", "fields": [
            {**AUTHORS, "required": False},
            _field("title", "Article title", "Els llibreters abandonen la Fira del Llibre de Barcelona", True),
            _field("newspaper", "Newspaper", "Avui", True),
            _field("place", "Place of edition", "Barcelona", hint="if not in the name; shown in [ ]"),
            _field("date", "Date", "", True, "in the language of the newspaper", default=newspaper_date(today)),
            _field("issue", "Issue no.", "8.026"), _field("pages", "Pages", "33"),
        ]},
        {"id": "official", "label": "Publicació oficial (official gazette)", "fields": [
            _field("title", "Text title", "Ley Orgánica 10/1995, de 23 de noviembre, del Código Penal",
                   hint="optional: the law or text cited"),
            _field("gazette", "Publication", "Boletín Oficial del Estado", True),
            _field("date", "Date", "", True, "in the language of the publication", default=gazette_date(today)),
            _field("issue", "Issue no.", "281"), _field("pages", "Pages", "33987-34058", hint="first-last"),
        ]},
        {"id": "web", "label": "Pàgina web (web page)", "fields": [
            _field("author", "Author", "SIEMENS", True, "organisation, or the person for a personal page"),
            _field("consulted", "Date consulted", type="date", required=True, default=today.isoformat()),
            _field("title", "Page title", "SIEMENS. Productos y soluciones", True),
            _field("medium", "Medium", default="En línia", required=True),
            _field("url", "URL", "https://…", True, type="url"),
        ]},
    ]


FORMATTERS = {
    "book": _book, "part": _part, "standard": _standard, "catalogue": _catalogue, "periodical": _periodical,
    "article": _article, "newspaper": _newspaper, "official": _official, "web": _web,
}


def format_reference(kind: str, fields: dict) -> str:
    """LaTeX text of one bibliography entry (without \\bibitem)."""
    try:
        formatter = FORMATTERS[kind]
    except KeyError as exc:
        raise UserError(f"Unknown reference type: {kind}") from exc
    return formatter(fields or {})


def key_parts(kind: str, fields: dict) -> tuple[str, str]:
    """(who, year) for a citation key such as bragos1994."""
    who = next((str(fields.get(n) or "") for n in ("authors", "author", "entity", "company", "newspaper",
                                                    "gazette", "title") if fields.get(n)), "")
    who = who.split(";")[0].split(",")[0]
    when = " ".join(str(fields.get(n) or "") for n in ("year", "consulted", "date", "numbering"))
    year = re.search(r"\d{4}", when)
    return who, year.group(0) if year else ""
