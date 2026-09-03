from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_home_executes_without_error(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'app.sqlite'}"
    monkeypatch.setenv("FINANCE_DATABASE_URL", database_url)

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(app_path).run(timeout=10)

    assert not app.exception
    assert app.metric[0].value == "0"
    assert int(app.metric[1].value) > 0
