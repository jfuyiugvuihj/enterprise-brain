import pandas as pd


class TestRowLevelFiltering:
    def test_filters_rows_by_department(self):
        from app.common.rbac import filter_dataframe_rows

        df = pd.DataFrame(
            {
                "name": ["a", "b", "c"],
                "department": ["sales", "hr", ""],
                "value": [1, 2, 3],
            }
        )

        filtered = filter_dataframe_rows(df, role="staff", department="sales")

        assert list(filtered["name"]) == ["a", "c"]


class TestImNotifications:
    def test_build_im_payload(self):
        from app.common.notifications import build_im_payload

        payload = build_im_payload("日报", "完成 3 项任务", source="scheduler", severity="info")

        assert payload["title"] == "日报"
        assert payload["source"] == "scheduler"
        assert payload["severity"] == "info"


class TestDocumentVersions:
    def test_selects_next_version(self):
        from app.documents.catalog import next_document_version

        rows = [
            {"filename": "policy.docx", "version": 1},
            {"filename": "policy.docx", "version": 2},
        ]

        assert next_document_version(rows, "policy.docx") == 3


class TestSsoIdentity:
    def test_extracts_user_claims(self):
        from app.common.sso import extract_sso_identity

        headers = {
            "X-SSO-User": "alice",
            "X-SSO-Role": "manager",
            "X-SSO-Department": "sales",
            "X-SSO-Display-Name": "Alice",
        }

        identity = extract_sso_identity(headers)

        assert identity["username"] == "alice"
        assert identity["role"] == "manager"
        assert identity["department"] == "sales"


class TestProfileContext:
    def test_formats_tailored_context(self):
        from app.memory.profile import compose_profile_context

        text = compose_profile_context(
            {"department": "sales", "position": "经理", "preferences": ["简洁", "图表优先"]}
        )

        assert "sales" in text
        assert "经理" in text
        assert "简洁" in text
