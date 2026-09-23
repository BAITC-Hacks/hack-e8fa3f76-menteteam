def test_demo_review_persists_after_rerun(tmp_path, monkeypatch):
    monkeypatch.setenv("ALEM_DATA_DIR", str(tmp_path))
    import settings
    monkeypatch.setattr(settings, "DATA", tmp_path)
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=15).run()
    assert not app.exception
    demo = next(button for button in app.button if button.label == "Открыть демонстрацию")
    demo.click().run()
    assert not app.exception
    assert any("Демо" in heading.value for heading in app.subheader)
    task_title = next(field for field in app.text_input if field.label == "Поручение")
    task_title.set_value("Исправленное поручение")
    save = next(button for button in app.button if button.label == "Сохранить поручение")
    save.click().run()
    assert not app.exception
    app.run()
    assert any(field.value == "Исправленное поручение" for field in app.text_input)
    from adapters.repository import SQLiteMeetings
    assert SQLiteMeetings(tmp_path / "meetings.sqlite3").list()[0].tasks[0].title == "Исправленное поручение"


def test_server_hf_token_is_not_sent_to_browser(tmp_path, monkeypatch):
    import settings
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(settings, "DATA", tmp_path)
    monkeypatch.setenv("HF_TOKEN", "test-private-server-credential")
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=15).run()
    assert not app.exception
    assert all(field.value != "test-private-server-credential" for field in app.text_input)
