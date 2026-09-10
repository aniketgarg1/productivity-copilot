"""Google credential serialisation and refresh."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.db.models import GoogleToken
from app.tools.google_calendar import (
    _refresh_and_persist,
    creds_from_json,
    ensure_fresh_token,
)
from app.tools.google_oauth import creds_to_json
from tests.conftest import TEST_EMAIL, google_token_json


class _FakeCreds:
    """Minimal stand-in for google.oauth2.credentials.Credentials."""

    def __init__(self, expiry):
        self.token = "new-access-token"
        self.refresh_token = "test-refresh-token"
        self.token_uri = "https://oauth2.googleapis.com/token"
        self.client_id = "cid"
        self.client_secret = "cs"
        self.scopes = ["openid"]
        self.expiry = expiry


class TestExpiryRoundTrip:
    def test_expiry_is_serialised(self):
        """Regression: expiry was dropped, so `expired` was always False."""
        expiry = datetime(2030, 1, 1, 12, 0, 0)
        payload = creds_to_json(_FakeCreds(expiry))
        assert "expiry" in payload
        assert "2030-01-01" in payload

    def test_a_past_expiry_marks_credentials_expired(self):
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        assert creds_from_json(google_token_json(past)).expired is True

    def test_a_future_expiry_does_not(self):
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        assert creds_from_json(google_token_json(future)).expired is False

    def test_an_unparseable_expiry_is_ignored_not_fatal(self):
        import json

        raw = json.loads(google_token_json())
        raw["expiry"] = "definitely-not-a-date"
        creds = creds_from_json(json.dumps(raw))
        assert creds.expiry is None

    def test_missing_expiry_is_tolerated(self):
        creds = creds_from_json(google_token_json(None))
        assert creds.expiry is None


class TestRefresh:
    def test_expired_credentials_are_refreshed(self):
        past = datetime.now(timezone.utc) - timedelta(hours=2)

        with patch("app.tools.google_calendar.Credentials.refresh") as refresh:
            creds, refreshed = _refresh_and_persist(google_token_json(past))

        assert refreshed is True
        refresh.assert_called_once()

    def test_valid_credentials_are_left_alone(self):
        future = datetime.now(timezone.utc) + timedelta(hours=2)

        with patch("app.tools.google_calendar.Credentials.refresh") as refresh:
            creds, refreshed = _refresh_and_persist(google_token_json(future))

        assert refreshed is False
        refresh.assert_not_called()

    def test_legacy_rows_without_expiry_are_refreshed_once(self):
        """Rows written before expiry was stored must self-heal, not 401 forever."""
        with patch("app.tools.google_calendar.Credentials.refresh") as refresh:
            _, refreshed = _refresh_and_persist(google_token_json(None))

        assert refreshed is True
        refresh.assert_called_once()


class TestEnsureFreshToken:
    def test_a_refreshed_token_is_written_back_to_the_db(self, db):
        """Regression: refreshes were discarded, so every call re-refreshed."""
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        row = GoogleToken(email=TEST_EMAIL, token_json=google_token_json(past))
        db.add(row)
        db.commit()

        original = row.token_json

        def fake_refresh(self, request):
            self.token = "refreshed-access-token"
            self.expiry = datetime.utcnow() + timedelta(hours=1)

        with patch("app.tools.google_calendar.Credentials.refresh", fake_refresh):
            returned = ensure_fresh_token(db, row)

        assert returned != original
        assert "refreshed-access-token" in returned

        db.expire_all()
        persisted = db.query(GoogleToken).filter(GoogleToken.email == TEST_EMAIL).first()
        assert "refreshed-access-token" in persisted.token_json

    def test_a_valid_token_is_returned_unchanged(self, db):
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        row = GoogleToken(email=TEST_EMAIL, token_json=google_token_json(future))
        db.add(row)
        db.commit()

        with patch("app.tools.google_calendar.Credentials.refresh") as refresh:
            returned = ensure_fresh_token(db, row)

        refresh.assert_not_called()
        assert returned == row.token_json
