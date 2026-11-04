import shutil

import pytest

from app import synctex
from app.api import Api
from app.builder import Builder
from app.errors import UserError

pytestmark = [
    pytest.mark.latex,
    pytest.mark.skipif(shutil.which("synctex") is None or shutil.which("lualatex") is None,
                       reason="MiKTeX not installed"),
]

MAIN = "\\documentclass{article}\n\\begin{document}\nFirst paragraph on page one.\n\n\\input{chapters/capítol}\n\\end{document}\n"
CHAPTER = "Line one of the chapter.\n\n\\newpage\nA paragraph on the second page.\n"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("Tesi Martí")
    (root / "chapters").mkdir()
    (root / "main.tex").write_text(MAIN, encoding="utf-8")
    (root / "chapters" / "capítol.tex").write_text(CHAPTER, encoding="utf-8")
    assert Builder(root, "main.tex").run().status == "success"
    return root


def test_forward_and_inverse_roundtrip(built):
    boxes = synctex.forward(built, ".build/main.pdf", "chapters/capítol.tex", 4)
    assert boxes and boxes[0]["page"] == 2
    box = boxes[0]
    assert box["w"] > 0 and box["h"] > 0
    hit = synctex.inverse(built, ".build/main.pdf", box["page"], box["x"] + 5, box["y"] + box["h"] / 2)
    assert hit == {"file": "chapters/capítol.tex", "line": 4}


def test_main_file_location(built):
    [box, *_] = synctex.forward(built, ".build/main.pdf", "main.tex", 3)
    assert box["page"] == 1
    assert synctex.inverse(built, ".build/main.pdf", 1, box["x"] + 5, box["y"] + box["h"] / 2) == {"file": "main.tex", "line": 3}


def test_unknown_file_gives_nothing(built):
    assert synctex.forward(built, ".build/main.pdf", "nope.tex", 1) == []


def test_api_requires_a_build(settings, make_zip):
    api = Api(settings)
    api.import_zip(str(make_zip({"main.tex": MAIN.replace("\\input{chapters/capítol}", "")})))
    with pytest.raises(UserError):
        api.synctex_forward("main.tex", 3)
    api.compile()
    assert api.synctex_forward("main.tex", 3)[0]["page"] == 1
    with pytest.raises(UserError):
        api.synctex_forward("../outside.tex", 1)
