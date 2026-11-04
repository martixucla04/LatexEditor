from app.logparser import collect_problems, parse_bibtex_blg, parse_biber_blg, parse_latex_log, unwrap


def simple(problems):
    return [(p.severity, p.file, p.line) for p in problems]


def test_unwrap_joins_79_byte_lines():
    first = "(C:/MiKTeX/tex/latex/biblatex/lbx/english.lb" + "x" * 35
    assert len(first) == 79
    assert unwrap(first + "\nrest)\nnext") == [first + "rest)", "next"]
    # multi-byte characters: TeX counts bytes
    accented = "à" * 39 + "x"  # 79 bytes, 40 characters
    assert unwrap(accented + "\ntail") == [accented + "tail"]


def test_file_line_error_with_context(tmp_path):
    log = """(./main.tex
(./sections/intro.tex
./sections/intro.tex:12: Undefined control sequence.
l.12 Some text \\badcommand
                           more
The control sequence (at the end) of the top line

)
)"""
    [p] = parse_latex_log(log, tmp_path)
    assert (p.severity, p.file, p.line, p.context) == ("error", "sections/intro.tex", 12, "Some text \\badcommand")
    assert p.message == "Undefined control sequence."


def test_warnings_follow_the_file_stack(tmp_path):
    log = """(./main.tex (C:/MiKTeX/tex/latex/base/article.cls
Document Class: article
(C:/MiKTeX/tex/latex/base/size10.clo))
(./chapters/one.tex
Text with (unbalanced paren in a font info line
)

LaTeX Warning: Reference `fig:x' on page 2 undefined on input line 7.

)
LaTeX Warning: Citation `k' on page 3 undefined on input line 20.

)"""
    problems = parse_latex_log(log, tmp_path)
    # the stray "(" in chapters/one.tex is balanced by its own ")" line; the next ")" closes the file
    assert simple(problems) == [("warning", "chapters/one.tex", 7), ("warning", "main.tex", 20)]


def test_package_warning_continuation_lines(tmp_path):
    log = """(./main.tex
Package natbib Warning: Citation `doe' on page 1 undefined on input line 5.

Package hyperref Warning: Token not allowed in a PDF string (Unicode):
(hyperref)                removing `math shift' on input line 9.

)"""
    problems = parse_latex_log(log, tmp_path)
    assert simple(problems) == [("warning", "main.tex", 5), ("warning", "main.tex", 9)]
    assert problems[1].message == "hyperref: Token not allowed in a PDF string (Unicode): removing `math shift' on input line 9."


def test_bang_error_without_file_line(tmp_path):
    log = """(./main.tex
! Missing } inserted.
<inserted text>
                }
l.42 \\end{equation}

)"""
    [p] = parse_latex_log(log, tmp_path)
    assert (p.severity, p.file, p.line) == ("error", "main.tex", 42)


def test_badboxes_and_font_warnings_are_info(tmp_path):
    log = """(./main.tex
Overfull \\hbox (15.2pt too wide) in paragraph at lines 10--12
[]\\TU/lmr/m/n/10 text with ( paren
 []


LaTeX Font Warning: Font shape `TU/lmr/m/scit' undefined
(Font)              using `TU/lmr/m/scsl' instead on input line 30.

Underfull \\vbox (badness 10000) has occurred while \\output is active []

)"""
    problems = parse_latex_log(log, tmp_path)
    assert simple(problems) == [("info", "main.tex", 10), ("info", "main.tex", 30), ("info", "main.tex", None)]


def test_errors_in_package_files_are_external(tmp_path):
    log = "(./main.tex\nC:/MiKTeX/tex/latex/foo/foo.sty:88: Package foo Error: Bad option.\n\n)"
    [p] = parse_latex_log(log, tmp_path)
    assert p.file is None and p.external == "C:/MiKTeX/tex/latex/foo/foo.sty" and p.line == 88


def test_emergency_stop_hidden_when_real_error_exists(tmp_path):
    log = """(./main.tex
./main.tex:3: LaTeX Error: File `missing.tex' not found.

! Emergency stop.
<read *>

*** (cannot \\read from terminal in nonstop modes)
)"""
    problems = parse_latex_log(log, tmp_path)
    assert [p.message for p in problems] == ["LaTeX Error: File `missing.tex' not found."]


def test_duplicates_removed(tmp_path):
    warning = "LaTeX Warning: Reference `a' on page 1 undefined on input line 3.\n\n"
    assert len(parse_latex_log("(./main.tex\n" + warning * 3 + ")", tmp_path)) == 1


def test_biber_blg(tmp_path):
    blg = r"""[0] Config.pm:308> INFO - This is Biber 2.20
[330] Biber.pm:1002> INFO - Found 2 citekeys in bib section 0
[454] bibtex.pm:1519> INFO - Found BibTeX data source 'refs.bib'
[454] Utils.pm:479> ERROR - BibTeX subsystem: C:\Temp\biber_tmp_x\8fe4c_36588.utf8, line 4, syntax error: found "b2", expected "="
[460] Biber.pm:131> WARN - I didn't find a database entry for 'nokey' (section 0)
"""
    problems = parse_biber_blg(blg, tmp_path)
    assert simple(problems) == [("error", "refs.bib", 4), ("warning", None, None)]
    assert problems[0].message == 'refs.bib: syntax error: found "b2", expected "="'


def test_bibtex_blg(tmp_path):
    blg = """This is BibTeX, Version 0.99d
The top-level auxiliary file: .build/main.aux
I was expecting a `,' or a `}'---line 3 of file bib/refs.bib
 :
 : @book{b2 author
(Error may have been on previous line)
Warning--I didn't find a database entry for "nokey"
Warning--empty journal in a1
while executing---line 1234 of file plainnat.bst
(There was 1 error message)
"""
    problems = parse_bibtex_blg(blg, tmp_path)
    assert simple(problems) == [("error", "bib/refs.bib", 3), ("warning", None, None), ("warning", None, None)]


def test_collect_reports_failed_tool_without_parsed_errors(tmp_path):
    class Step:
        tool, exit_code = "makeglossaries-lite", 1

    build = tmp_path / ".build"
    build.mkdir()
    problems = collect_problems(tmp_path, build, "main", log="(./main.tex)", steps=[Step()])
    assert [(p.severity, p.source) for p in problems] == [("error", "makeglossaries-lite")]
