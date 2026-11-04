"""Every example of the style guide, typed into the dialog's fields, must come out as in the guide."""

from datetime import date

import pytest

from app.errors import UserError
from app.reftypes import FORMATTERS, format_reference, gazette_date, key_parts, newspaper_date, types

NL = " \\newline "

BOOK = {
    "authors": "Bragós Bardia, Ramon", "etal": True, "title": "Circuitos y dispositivos electrónicos",
    "subtitle": "fundamentos de electrónica", "edition": "4", "place": "Barcelona", "publisher": "Edicions UPC",
    "year": "1994", "extent": "463", "collection": "Politext", "collection_number": "35", "isbn": "84-8301-215-4",
}


def test_book():
    assert format_reference("book", BOOK) == (
        "BRAGÓS BARDIA, Ramon ... [et al.]. Circuitos y dispositivos electrónicos: fundamentos de electrónica. "
        "4ª ed. Barcelona: Edicions UPC, 1994. 463 p. (Politext; 35)." + NL + "ISBN 84-8301-215-4")


def test_book_chapter_by_the_same_authors():
    fields = {**BOOK, "authors": "Bragós Bardia, R.", "chapter": "Capítol 3. Circuitos lineales", "chapter_pages": "35-57"}
    assert format_reference("book", fields) == (
        "BRAGÓS BARDIA, R. ... [et al.]. Circuitos y dispositivos electrónicos: fundamentos de electrónica. "
        "4ª ed. Barcelona: Edicions UPC, 1994. 463 p. (Politext; 35)."
        + NL + "Capítol 3. Circuitos lineales: p. 35-57." + NL + "ISBN 84-8301-215-4")


def test_part_of_a_book():
    fields = {"authors": "Alcaide, C.", "part_title": "L'euro, la moneda del segle XXI",
              "book_title": "L'impacte de l'euro als mercats financers", "place": "Barcelona", "publisher": "La Caixa",
              "year": "1998", "extent": "276", "collection": "Estudis i informes", "collection_number": "14",
              "part_pages": "13-37"}
    assert format_reference("part", fields) == (
        "ALCAIDE, C. “L’euro, la moneda del segle XXI”. A: L’impacte de l’euro als mercats financers. "
        "Barcelona: La Caixa, 1998. 276 p. (Estudis i informes; 14). P. 13-37.")


def test_standard():
    fields = {"entity": "Asociación Española de Normalización y Certificación",
              "title": "Términos generales y sus definiciones relativos a la normalización y actividades relacionadas",
              "code": "UNE 0-007-91", "place": "Madrid", "publisher": "AENOR", "year": "1991"}
    assert format_reference("standard", fields) == (
        "ASOCIACIÓN ESPAÑOLA DE NORMALIZACIÓN Y CERTIFICACIÓN. Términos generales y sus definiciones relativos a la "
        "normalización y actividades relacionadas. UNE 0-007-91. Madrid: AENOR, 1991.")


def test_catalogues():
    assert format_reference("catalogue", {"company": "Ariston", "title": "Catálogo general núm. 8",
                                          "publisher": "Ariston", "year": "[1999]"}) == (
        "ARISTON. Catálogo general núm. 8. [S.l.]: Ariston, [1999].")
    assert format_reference("catalogue", {"company": "RS", "title": "Catálogo: 1999-2000", "place": "Madrid; Barcelona",
                                          "publisher": "RS", "year": "1999"}) == (
        "RS. Catálogo: 1999-2000. Madrid; Barcelona: RS, 1999.")


def test_periodicals():
    assert format_reference("periodical", {"title": "Electronic design",
                                           "subtitle": "technology applications, products, solutions",
                                           "place": "Cleveland", "numbering": "Vol. 47 (1999), 26",
                                           "issn": "0013-4872"}) == (
        "Electronic design: technology applications, products, solutions. [Cleveland]. Vol. 47 (1999), 26. "
        "ISSN 0013-4872.")
    assert format_reference("periodical", {"title": "Electrónica práctica actual", "place": "Madrid",
                                           "numbering": "Año 2, núm. 5", "issn": "1139-3432"}) == (
        "Electrónica práctica actual. [Madrid]. Año 2, núm. 5. ISSN 1139-3432.")


def test_journal_article():
    fields = {"authors": "Kennard, L.", "title": "Novell certificate server 2.0: is your network certifiably secure?",
              "journal": "Netware connection", "volume": "11", "year": "2000", "issue": "1", "pages": "6-20",
              "issn": "1076-3422"}
    assert format_reference("article", fields) == (
        "KENNARD, L. “Novell certificate server 2.0: is your network certifiably secure?”. Netware connection. "
        "Vol. 11 (2000), núm. 1, p. 6-20." + NL + "ISSN 1076-3422.")
    del fields["issn"]  # optional
    assert format_reference("article", fields).endswith("núm. 1, p. 6-20.")


def test_newspaper_article():
    fields = {"authors": "Capdevila, J.", "title": "Els llibreters abandonen la Fira del Llibre de Barcelona",
              "newspaper": "Avui", "place": "Barcelona", "date": "10 de febrer del 2000", "issue": "8.026", "pages": "33"}
    assert format_reference("newspaper", fields) == (
        "CAPDEVILA, J. “Els llibreters abandonen la Fira del Llibre de Barcelona”. Avui [Barcelona] "
        "(10 de febrer del 2000), núm. 8.026, p. 33.")


def test_official_publications():
    assert format_reference("official", {"gazette": "Diari Oficial de la Generalitat de Catalunya",
                                         "date": "4 desembre 1996", "issue": "2289"}) == (
        "Diari Oficial de la Generalitat de Catalunya (4 desembre 1996), núm. 2289.")
    assert format_reference("official", {"title": "Ley Orgánica 10/1995, de 23 de noviembre, del Código Penal",
                                         "gazette": "Boletín Oficial del Estado", "date": "24 noviembre 1995",
                                         "issue": "281", "pages": "33987-34058"}) == (
        "“Ley Orgánica 10/1995, de 23 de noviembre, del Código Penal”. Boletín Oficial del Estado "
        "(24 noviembre 1995), núm. 281, p. 33987-34058.")


def test_web_pages():
    assert format_reference("web", {"author": "Equip Mediterrani", "consulted": "2000-02-11",
                                    "title": "Proyecto Despertaferro", "medium": "En línia",
                                    "url": "http://www.racingservices.net/cochesolar/"}) == (
        "Equip Mediterrani (Pàgina consultada l’11 de febrer de 2000). Proyecto Despertaferro, [En línia]. "
        "Adreça URL: \\url{http://www.racingservices.net/cochesolar/}")


def test_default_dates():
    d = date(2026, 11, 5)
    assert newspaper_date(d) == "5 de novembre del 2026"
    assert newspaper_date(date(2026, 4, 1)) == "1 d’abril del 2026"
    assert gazette_date(d) == "5 novembre 2026"


def test_required_fields_and_unknown_type():
    with pytest.raises(UserError):
        format_reference("book", {**BOOK, "title": " "})
    with pytest.raises(UserError):
        format_reference("article", {"title": "x", "journal": "y"})  # no author
    with pytest.raises(UserError):
        format_reference("poem", {})


def test_schema_matches_formatters():
    schema = types(date(2026, 11, 5))
    assert [t["id"] for t in schema] == list(FORMATTERS)
    for t in schema:
        assert all({"id", "label", "required", "type"} <= set(f) for f in t["fields"])
    newspaper = next(t for t in schema if t["id"] == "newspaper")
    assert next(f for f in newspaper["fields"] if f["id"] == "date")["default"] == "5 de novembre del 2026"


def test_key_parts():
    assert key_parts("book", BOOK) == ("Bragós Bardia", "1994")
    assert key_parts("standard", {"entity": "AENOR", "year": "1991"}) == ("AENOR", "1991")
    assert key_parts("newspaper", {"newspaper": "Avui", "date": "10 de febrer del 2000"}) == ("Avui", "2000")
