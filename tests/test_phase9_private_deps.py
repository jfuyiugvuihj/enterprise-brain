import importlib
import sys


class TestOptionalPsycopgImports:
    def test_chat_and_alerts_import_without_psycopg(self, monkeypatch):
        import app.api.v1.chat as chat_module
        import app.api.v1.alerts as alerts_module

        monkeypatch.setitem(sys.modules, "psycopg", None)
        monkeypatch.setitem(sys.modules, "psycopg.rows", None)

        importlib.reload(chat_module)
        importlib.reload(alerts_module)
