from app.settings import Settings


def test_preferences_defaults_and_updates(settings, tmp_path):
    assert settings.preferences() == {
        "theme": "system", "font_size": 14, "word_wrap": True, "reopen_last": True,
        "workspace": str(tmp_path / "workspace"),
    }
    new_ws = tmp_path / "Documents" / "Recerca"
    prefs = settings.update_preferences({"theme": "dark", "font_size": 16, "word_wrap": False,
                                         "reopen_last": False, "workspace": str(new_ws)})
    assert prefs == {"theme": "dark", "font_size": 16, "word_wrap": False, "reopen_last": False,
                     "workspace": str(new_ws)}
    assert new_ws.is_dir()
    # persisted
    assert Settings(settings.path).preferences()["theme"] == "dark"


def test_invalid_preferences_are_ignored(settings):
    prefs = settings.update_preferences({"theme": "purple", "font_size": 99, "word_wrap": "yes", "unknown": 1})
    assert (prefs["theme"], prefs["font_size"], prefs["word_wrap"]) == ("system", 14, True)
