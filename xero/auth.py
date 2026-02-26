"""OAuth 2.0 authentication for Xero API."""

import base64
import http.server
import json
import logging
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"
CONNECTIONS_URL = "https://api.xero.com/connections"
REDIRECT_URI = "http://localhost:8484/callback"
SCOPES = " ".join([
    "offline_access",
    "openid",
    "profile",
    "accounting.transactions.read",
    "accounting.contacts.read",
    "accounting.settings.read",
    "accounting.attachments.read",
    "accounting.reports.read",
])
TOKEN_FILE = ".xero_tokens.json"


class _OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handles the OAuth redirect and extracts the authorization code."""

    auth_code = None
    auth_state = None
    error = None

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        _OAuthCallbackHandler.auth_code = params.get("code", [None])[0]
        _OAuthCallbackHandler.auth_state = params.get("state", [None])[0]
        _OAuthCallbackHandler.error = params.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

        if _OAuthCallbackHandler.error:
            self.wfile.write(
                b"<html><body><h2>Authorization failed.</h2>"
                b"<p>You can close this tab.</p></body></html>"
            )
        else:
            self.wfile.write(
                b"<html><body><h2>Authorization successful!</h2>"
                b"<p>You can close this tab and return to the terminal.</p></body></html>"
            )

    def log_message(self, format, *args):
        pass  # Suppress server access logs


def _save_tokens(tokens: dict):
    """Save tokens to disk with computed expiry timestamp."""
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 1800)
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    logger.debug("Tokens saved to %s", TOKEN_FILE)


def _load_tokens() -> dict | None:
    """Load tokens from disk. Returns None if file doesn't exist."""
    path = Path(TOKEN_FILE)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load tokens: %s", e)
        return None


def _is_token_valid(tokens: dict) -> bool:
    """Check if the access token is still valid (with 60s buffer)."""
    expires_at = tokens.get("expires_at", 0)
    return time.time() < (expires_at - 60)


def _get_client_credentials() -> tuple[str, str]:
    """Get client ID and secret from environment variables."""
    client_id = os.environ.get("XERO_CLIENT_ID", "").strip()
    client_secret = os.environ.get("XERO_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError(
            "XERO_CLIENT_ID and XERO_CLIENT_SECRET must be set in .env file. "
            "Copy .env.example to .env and fill in your credentials."
        )
    return client_id, client_secret


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    """Build Basic auth header value for token endpoint."""
    credentials = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def _exchange_code(code: str) -> dict:
    """Exchange authorization code for tokens."""
    client_id, client_secret = _get_client_credentials()

    response = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": _basic_auth_header(client_id, client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Token exchange failed ({response.status_code}): {response.text}"
        )

    tokens = response.json()
    _save_tokens(tokens)
    return tokens


def _refresh_token(refresh_token: str) -> dict:
    """Refresh an expired access token."""
    client_id, client_secret = _get_client_credentials()

    response = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": _basic_auth_header(client_id, client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )

    if response.status_code != 200:
        # Refresh token may be expired (60 day lifetime)
        if response.status_code == 400:
            # Delete stale token file so next run starts fresh
            Path(TOKEN_FILE).unlink(missing_ok=True)
            raise RuntimeError(
                "Refresh token expired. Please re-run to authorize again."
            )
        raise RuntimeError(
            f"Token refresh failed ({response.status_code}): {response.text}"
        )

    tokens = response.json()
    _save_tokens(tokens)
    logger.info("Access token refreshed successfully")
    return tokens


def _start_auth_flow() -> dict:
    """Run the full OAuth 2.0 authorization code flow."""
    client_id, _ = _get_client_credentials()
    state = secrets.token_urlsafe(32)

    # Reset handler state
    _OAuthCallbackHandler.auth_code = None
    _OAuthCallbackHandler.auth_state = None
    _OAuthCallbackHandler.error = None

    # Start local callback server
    server = http.server.HTTPServer(("localhost", 8484), _OAuthCallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Build authorization URL
    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
    })
    auth_url = f"{AUTHORIZE_URL}?{params}"

    print("\nOpening browser for Xero authorization...")
    print(f"If the browser doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for the callback
    print("Waiting for authorization...")
    while _OAuthCallbackHandler.auth_code is None and _OAuthCallbackHandler.error is None:
        time.sleep(0.5)

    server.shutdown()

    if _OAuthCallbackHandler.error:
        raise RuntimeError(
            f"Authorization failed: {_OAuthCallbackHandler.error}"
        )

    # Verify state parameter
    if _OAuthCallbackHandler.auth_state != state:
        raise RuntimeError("OAuth state mismatch - possible CSRF attack")

    print("Authorization received. Exchanging code for tokens...")
    return _exchange_code(_OAuthCallbackHandler.auth_code)


def get_authenticated_session() -> tuple[requests.Session, dict]:
    """
    Get an authenticated requests.Session with a valid Bearer token.

    Returns (session, tokens) tuple. The tokens dict is also saved to disk.
    Handles the full flow: load saved tokens -> refresh if expired -> full auth if needed.
    """
    tokens = _load_tokens()

    if tokens:
        if _is_token_valid(tokens):
            logger.info("Using saved access token")
        else:
            logger.info("Access token expired, refreshing...")
            tokens = _refresh_token(tokens["refresh_token"])
    else:
        tokens = _start_auth_flow()

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {tokens['access_token']}",
    })

    return session, tokens


def get_tenant_id(session: requests.Session) -> str:
    """
    Get the Xero tenant ID (organisation ID) for API calls.

    If multiple tenants are connected, selects the first one.
    """
    response = session.get(CONNECTIONS_URL)
    response.raise_for_status()

    connections = response.json()
    if not connections:
        raise RuntimeError(
            "No Xero organisations connected to this app. "
            "Please authorize the app with at least one organisation."
        )

    if len(connections) > 1:
        print("\nMultiple organisations found:")
        for i, conn in enumerate(connections):
            print(f"  [{i + 1}] {conn['tenantName']} ({conn['tenantId']})")
        print(f"\nUsing: {connections[0]['tenantName']}")

    tenant = connections[0]
    logger.info("Tenant: %s (%s)", tenant["tenantName"], tenant["tenantId"])
    return tenant["tenantId"]


def refresh_if_needed(tokens: dict) -> dict:
    """Check and refresh tokens if expired. Returns updated tokens."""
    if _is_token_valid(tokens):
        return tokens
    logger.info("Access token expired, refreshing...")
    return _refresh_token(tokens["refresh_token"])
