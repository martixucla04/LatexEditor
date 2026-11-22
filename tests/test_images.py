import base64

import pytest

from app.errors import UserError
from app.images import figure_names, image_folders, save_image, slug
from app.project import Project

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20  # only the signature is checked
DOC = "\\documentclass{report}\n\\begin{document}\n\\label{fig:arquitectura-isospi}\n\\end{document}\n"


@pytest.fixture
def project(make_project):
    return Project(make_project({
        "main.tex": DOC,
        "Imagenes/Introduccio/a.png": PNG, "Imagenes/Introduccio/b.jpg": b"x",
        "Imagenes/BMU/isoSPI/c.jpeg": b"x", "Contenido/bmu.tex": "text",
    }))


def test_slug():
    assert slug("Arquitectura isoSPI (Font: \\cite{ltc6811})") == "arquitectura-isospi"
    assert slug("Cel·les a 25 °C") == "celles-a-25-c"
    assert slug("$x^2$") == "figura"


def test_folders_and_default(project):
    found = image_folders(project)
    assert found["folders"] == ["Imagenes/BMU/isoSPI", "Imagenes/Introduccio"]
    assert found["default"] == "Imagenes/Introduccio"  # most images
    text = "\\includegraphics[width=0.8\\textwidth]{Imagenes/BMU/isoSPI/c.jpeg}\n% \\includegraphics{x/y.png}\n"
    assert image_folders(project, text)["default"] == "Imagenes/BMU/isoSPI"  # last one in this file


def test_names_are_free(project):
    names = figure_names(project, "Imagenes/Introduccio", "Arquitectura isoSPI")
    assert names == {"file": "arquitectura-isospi.png", "label": "fig:arquitectura-isospib"}
    (project.root / "Imagenes/Introduccio/arquitectura-isospi.png").write_bytes(PNG)
    assert figure_names(project, "Imagenes/Introduccio", "Arquitectura isoSPI")["file"] == "arquitectura-isospi-2.png"


def test_save_image(project):
    data = base64.b64encode(PNG).decode()
    assert save_image(project, "Imagenes/Nova", "diagrama", "data:image/png;base64," + data) == "Imagenes/Nova/diagrama.png"
    assert save_image(project, "Imagenes/Nova", "diagrama.png", data) == "Imagenes/Nova/diagrama-2.png"
    assert (project.root / "Imagenes/Nova/diagrama.png").read_bytes() == PNG
    with pytest.raises(UserError, match="Only PNG"):
        save_image(project, "", "x.png", base64.b64encode(b"GIF89a").decode())
    with pytest.raises(UserError):
        save_image(project, "../outside", "x.png", data)
