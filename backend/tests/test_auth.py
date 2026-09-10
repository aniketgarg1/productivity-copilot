"""Session cookie auth and the Google OAuth handshake."""

from itsdangerous import URLSafeSerializer

from app.api.deps import OAUTH_STATE_COOKIE, USER_COOKIE, oauth_state_serializer
from app.db.models import GoogleToken
from tests.conftest import TEST_EMAIL, google_token_json

PROTECTED = [
    ("get", "/tasks"),
    ("get", "/analytics"),
    ("get", "/calls/history"),
    ("post", "/calls/trigger"),
    ("get", "/calendar/test-create-event"),
]


class TestProtectedRoutes:
    def test_all_require_a_session(self, client):
        for method, path in PROTECTED:
            resp = getattr(client, method)(path)
            assert resp.status_code == 401, f"{method.upper()} {path} returned {resp.status_code}"

    def test_a_forged_cookie_is_rejected(self, client):
        forged = URLSafeSerializer("attacker-secret", salt="pc-user-session").dumps(
            {"email": "attacker@evil.test"}
        )
        client.cookies.set(USER_COOKIE, forged)
        resp = client.get("/tasks")
        assert resp.status_code == 401
        assert "Invalid session" in resp.json()["detail"]

    def test_a_cookie_signed_with_the_wrong_salt_is_rejected(self, client):
        from app.core.config import settings

        wrong_salt = URLSafeSerializer(settings.SESSION_SECRET, salt="not-the-right-salt").dumps(
            {"email": TEST_EMAIL}
        )
        client.cookies.set(USER_COOKIE, wrong_salt)
        assert client.get("/tasks").status_code == 401

    def test_a_valid_cookie_is_accepted(self, auth_client, connected_user):
        assert auth_client.get("/tasks").status_code == 200


class TestCallTriggerAuthorization:
    def test_trigger_cannot_target_another_user(self, auth_client, db):
        """Regression: /calls/trigger/{email} let anyone call anyone's phone."""
        from app.db.models import UserProfile

        db.add(UserProfile(email="victim@example.com", phone="+15551234567"))
        db.commit()

        # The email-in-path form must no longer exist at all.
        assert auth_client.post("/calls/trigger/victim@example.com").status_code == 404


class TestGoogleOAuth:
    def test_login_sets_state_cookie_and_redirects_to_google(self, client):
        resp = client.get("/auth/google/login", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("https://accounts.google.com/")
        assert OAUTH_STATE_COOKIE in resp.cookies

    def test_start_returns_a_url_and_sets_the_cookie(self, client):
        resp = client.get("/auth/google/start")

        assert resp.status_code == 200
        assert resp.json()["auth_url"].startswith("https://accounts.google.com/")
        assert OAUTH_STATE_COOKIE in resp.cookies

    def test_callback_without_the_state_cookie_is_rejected(self, client):
        resp = client.get("/auth/google/callback?code=x&state=y", follow_redirects=False)
        assert resp.status_code == 400
        assert "oauth_state" in resp.json()["detail"]

    def test_callback_rejects_a_tampered_state(self, client):
        client.cookies.set(
            OAUTH_STATE_COOKIE, oauth_state_serializer().dumps({"state": "the-real-state"})
        )
        resp = client.get(
            "/auth/google/callback?code=x&state=tampered", follow_redirects=False
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "State mismatch"

    def test_callback_surfaces_a_google_error(self, client):
        resp = client.get("/auth/google/callback?error=access_denied", follow_redirects=False)
        assert resp.status_code == 400
        assert "access_denied" in resp.json()["detail"]

    def test_status_reports_connection(self, auth_client, db):
        assert auth_client.get("/auth/google/status").json() == {
            "connected": False,
            "email": None,
        }

        db.add(GoogleToken(email=TEST_EMAIL, token_json=google_token_json()))
        db.commit()

        assert auth_client.get("/auth/google/status").json() == {
            "connected": True,
            "email": TEST_EMAIL,
        }


class TestTwilioWebhooks:
    def test_webhooks_reject_unsigned_requests(self, client, monkeypatch):
        """Regression: the /calls/* webhooks accepted anything."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "a-test-auth-token")

        for path in ("/calls/twiml/1", "/calls/respond/1", "/calls/status/1"):
            resp = client.post(path, data={"CallSid": "CA123"})
            assert resp.status_code == 403, f"{path} accepted an unsigned request"
            assert resp.json()["detail"] == "Invalid Twilio signature"

    def test_a_correctly_signed_request_passes_validation(self, client, monkeypatch):
        from twilio.request_validator import RequestValidator

        from app.core.config import settings

        token = "a-test-auth-token"
        monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", token)

        url = "http://testserver/calls/status/1"
        params = {"CallStatus": "completed", "CallSid": "CA123"}
        signature = RequestValidator(token).compute_signature(url, params)

        resp = client.post(
            "/calls/status/1", data=params, headers={"X-Twilio-Signature": signature}
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
