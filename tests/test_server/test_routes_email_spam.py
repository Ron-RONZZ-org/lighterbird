"""Tests for POST /api/v1/email/spam/report REST endpoint.

Covers all three report types (spam, fraud, ham) and error cases.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


def _make_mock_email_svc():
    """Build a mock email service with all dependencies for spam reporting."""
    svc = MagicMock()

    # ── messages.get ─────────────────────────────────────────────────
    svc.messages.get.return_value = {
        "uuid": "msg-001",
        "account_email": "user@test.com",
        "subject": "Test subject",
        "body": "Test body",
        "from_addr": "spammer@evil.com",
        "html_body": "",
    }

    # ── spam_detect ──────────────────────────────────────────────────
    trainer = MagicMock()
    classifier = MagicMock()
    classifier.classify.return_value = {"is_spam": True, "score": 0.95}
    svc.spam_detect = MagicMock()
    svc.spam_detect.trainer = trainer
    svc.spam_detect.classifier = classifier

    # ── phishing ─────────────────────────────────────────────────────
    svc.phishing = MagicMock()

    # ── db ───────────────────────────────────────────────────────────
    svc.db = MagicMock()

    return svc


class TestReportSpamEndpoint:
    """Tests for POST /api/v1/email/spam/report."""

    def _client(self, **overrides):
        """Create a TestClient with dependency overrides."""
        app = create_app()
        app.dependency_overrides.update(overrides)
        return TestClient(app)

    # ── spam type ────────────────────────────────────────────────────

    def test_report_spam_success(self):
        """POST with type=spam trains Bayesian and flags message."""
        mock_svc = _make_mock_email_svc()

        client = self._client()
        from lighterbird.server.deps import get_email_service
        client.app.dependency_overrides[get_email_service] = lambda: mock_svc

        resp = client.post(
            "/api/v1/email/spam/report",
            json={"uuid": "msg-001", "type": "spam"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["type"] == "spam"
        assert data["uuid"] == "msg-001"

        # Verify Bayesian training was called
        mock_svc.spam_detect.trainer.report.assert_called_once_with(
            "Test subject", "Test body", "user@test.com", is_spam=True,
        )
        mock_svc.spam_detect.trainer.log_feedback.assert_called_once_with(
            "msg-001", "user@test.com", "spam",
        )
        # Verify message flags updated
        mock_svc.db.execute.assert_any_call(
            "UPDATE messages SET is_spam = 1, spam_reported = 1 WHERE uuid = ?",
            ("msg-001",),
        )
        # Verify classifier was run
        mock_svc.spam_detect.classifier.classify.assert_called_once_with(
            "Test subject", "Test body", "user@test.com",
        )

    def test_report_spam_updates_score(self):
        """spam type stores classifier score when returned."""
        mock_svc = _make_mock_email_svc()
        mock_svc.spam_detect.classifier.classify.return_value = {
            "is_spam": True, "score": 0.87,
        }

        from lighterbird.server.deps import get_email_service
        client = self._client()
        client.app.dependency_overrides[get_email_service] = lambda: mock_svc

        resp = client.post(
            "/api/v1/email/spam/report",
            json={"uuid": "msg-001", "type": "spam"},
        )
        assert resp.status_code == 200

        # Score should be written to DB
        score_call = ("UPDATE messages SET spam_score = ? WHERE uuid = ?", ("msg-001",))
        found_score = any(
            args[0].startswith("UPDATE messages SET spam_score")
            for args, _ in mock_svc.db.execute.call_args_list
        )
        assert found_score, "spam_score UPDATE not found in executed queries"

    # ── fraud type ───────────────────────────────────────────────────

    def test_report_fraud_success(self):
        """POST with type=fraud adds to watchlist and marks as phishing."""
        mock_svc = _make_mock_email_svc()

        from lighterbird.server.deps import get_email_service
        client = self._client()
        client.app.dependency_overrides[get_email_service] = lambda: mock_svc

        resp = client.post(
            "/api/v1/email/spam/report",
            json={"uuid": "msg-001", "type": "fraud"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["type"] == "fraud"

        # Verify phishing watchlist was updated
        mock_svc.phishing.report_fraudulent.assert_called_once()
        call_kwargs = mock_svc.phishing.report_fraudulent.call_args[1]
        assert call_kwargs["from_addr"] == "spammer@evil.com"
        assert call_kwargs["message_uuid"] == "msg-001"
        assert call_kwargs["account_email"] == "user@test.com"

        # Verify message is marked as phishing and deleted
        mock_svc.db.execute.assert_any_call(
            "UPDATE messages SET phishing_detected = 1, "
            "is_deleted = 1 WHERE uuid = ?",
            ("msg-001",),
        )

    def test_report_fraud_does_not_train_bayesian(self):
        """Fraud reports should NOT call the Bayesian trainer."""
        mock_svc = _make_mock_email_svc()

        from lighterbird.server.deps import get_email_service
        client = self._client()
        client.app.dependency_overrides[get_email_service] = lambda: mock_svc

        resp = client.post(
            "/api/v1/email/spam/report",
            json={"uuid": "msg-001", "type": "fraud"},
        )
        assert resp.status_code == 200

        # Trainer should NOT have been called
        mock_svc.spam_detect.trainer.report.assert_not_called()
        mock_svc.spam_detect.classifier.classify.assert_not_called()

    # ── ham type ─────────────────────────────────────────────────────

    def test_report_ham_success(self):
        """POST with type=ham trains Bayesian as NOT spam and clears flags."""
        mock_svc = _make_mock_email_svc()

        from lighterbird.server.deps import get_email_service
        client = self._client()
        client.app.dependency_overrides[get_email_service] = lambda: mock_svc

        resp = client.post(
            "/api/v1/email/spam/report",
            json={"uuid": "msg-001", "type": "ham"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["type"] == "ham"

        # Verify Bayesian training as ham
        mock_svc.spam_detect.trainer.report.assert_called_once_with(
            "Test subject", "Test body", "user@test.com", is_spam=False,
        )
        mock_svc.spam_detect.trainer.log_feedback.assert_called_once_with(
            "msg-001", "user@test.com", "ham",
        )
        # Verify spam flags cleared, ham flag set
        mock_svc.db.execute.assert_any_call(
            "UPDATE messages SET is_spam = 0, spam_reported = 0, "
            "ham_reported = 1 WHERE uuid = ?",
            ("msg-001",),
        )

    # ── Error cases ──────────────────────────────────────────────────

    def test_invalid_type_returns_400(self):
        """Unknown report type returns 400."""
        from lighterbird.server.deps import get_email_service
        client = self._client()
        client.app.dependency_overrides[get_email_service] = lambda: MagicMock()

        resp = client.post(
            "/api/v1/email/spam/report",
            json={"uuid": "msg-001", "type": "unknown"},
        )
        assert resp.status_code == 400
        assert "Invalid report type" in resp.json()["detail"]

    def test_message_not_found_returns_404(self):
        """Non-existent UUID returns 404."""
        mock_svc = _make_mock_email_svc()
        mock_svc.messages.get.return_value = None  # message not found

        from lighterbird.server.deps import get_email_service
        client = self._client()
        client.app.dependency_overrides[get_email_service] = lambda: mock_svc

        resp = client.post(
            "/api/v1/email/spam/report",
            json={"uuid": "nonexistent", "type": "spam"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_missing_uuid_returns_422(self):
        """Missing uuid field returns 422."""
        from lighterbird.server.deps import get_email_service
        client = self._client()
        client.app.dependency_overrides[get_email_service] = lambda: MagicMock()

        resp = client.post(
            "/api/v1/email/spam/report",
            json={"type": "spam"},  # no uuid
        )
        assert resp.status_code == 422

    def test_extra_fields_returns_422(self):
        """Extra fields in request body return 422 (model_config extra=forbid)."""
        from lighterbird.server.deps import get_email_service
        client = self._client()
        client.app.dependency_overrides[get_email_service] = lambda: MagicMock()

        resp = client.post(
            "/api/v1/email/spam/report",
            json={"uuid": "msg-001", "type": "spam", "extra": "field"},
        )
        assert resp.status_code == 422

    # ── messages.get called correctly ────────────────────────────────

    def test_calls_messages_get(self):
        """The endpoint calls email_svc.messages.get() with the given UUID."""
        mock_svc = _make_mock_email_svc()

        from lighterbird.server.deps import get_email_service
        client = self._client()
        client.app.dependency_overrides[get_email_service] = lambda: mock_svc

        resp = client.post(
            "/api/v1/email/spam/report",
            json={"uuid": "msg-001", "type": "spam"},
        )
        assert resp.status_code == 200

        # Verify messages.get() was called — this is the method that
        # previously had the AttributeError bug (was .get_message)
        mock_svc.messages.get.assert_called_once_with("msg-001")

    # ── Edge cases ───────────────────────────────────────────────────

    def test_spam_with_empty_subject_and_body(self):
        """Spam report works with empty subject/body (edge case)."""
        mock_svc = _make_mock_email_svc()
        mock_svc.messages.get.return_value = {
            "uuid": "msg-002",
            "account_email": "user@test.com",
            "subject": None,
            "body": "",
            "from_addr": "spammer@evil.com",
            "html_body": "",
        }

        from lighterbird.server.deps import get_email_service
        client = self._client()
        client.app.dependency_overrides[get_email_service] = lambda: mock_svc

        resp = client.post(
            "/api/v1/email/spam/report",
            json={"uuid": "msg-002", "type": "spam"},
        )
        assert resp.status_code == 200

        # Should pass empty strings to trainer
        mock_svc.spam_detect.trainer.report.assert_called_once_with(
            "", "", "user@test.com", is_spam=True,
        )
