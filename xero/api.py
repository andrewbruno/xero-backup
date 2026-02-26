"""Xero API HTTP client with rate limiting, pagination, and retry logic."""

import logging
import time

import requests

from xero import auth

logger = logging.getLogger(__name__)

BASE_URL = "https://api.xero.com/api.xro/2.0"


class RateLimiter:
    """Enforces Xero's rate limits: 60/min per tenant, 5000/day per tenant."""

    def __init__(self):
        self.call_timestamps: list[float] = []
        self.day_call_count = 0
        self.min_remaining: int | None = None
        self.day_remaining: int | None = None

    def wait_if_needed(self):
        """Block until it's safe to make another API call."""
        now = time.time()

        # Use server-reported remaining if available
        if self.min_remaining is not None and self.min_remaining <= 2:
            wait = 5
            logger.debug("Rate limit buffer: waiting %ds (min_remaining=%d)", wait, self.min_remaining)
            time.sleep(wait)
            return

        # Local tracking: keep only calls from last 60 seconds
        self.call_timestamps = [t for t in self.call_timestamps if now - t < 60]

        if len(self.call_timestamps) >= 58:
            oldest = self.call_timestamps[0]
            wait = 60 - (now - oldest) + 0.5
            if wait > 0:
                logger.debug("Rate limit: waiting %.1fs (local tracking)", wait)
                time.sleep(wait)

        # Daily limit warning
        if self.day_remaining is not None and self.day_remaining < 100:
            logger.warning("Daily API limit nearly exhausted: %d calls remaining", self.day_remaining)

    def record_call(self, response_headers: dict):
        """Update counters from response headers."""
        self.call_timestamps.append(time.time())
        self.day_call_count += 1

        min_rem = response_headers.get("X-MinLimit-Remaining")
        if min_rem is not None:
            self.min_remaining = int(min_rem)

        day_rem = response_headers.get("X-DayLimit-Remaining")
        if day_rem is not None:
            self.day_remaining = int(day_rem)


class XeroClient:
    """HTTP client for Xero API with rate limiting, pagination, and retries."""

    MAX_RETRIES = 3

    def __init__(self, session: requests.Session, tenant_id: str,
                 rate_limiter: RateLimiter, tokens: dict):
        self.session = session
        self.tenant_id = tenant_id
        self.rate_limiter = rate_limiter
        self.tokens = tokens
        self.total_api_calls = 0

    def _ensure_token_valid(self):
        """Refresh OAuth token if it's about to expire."""
        updated = auth.refresh_if_needed(self.tokens)
        if updated is not self.tokens:
            self.tokens = updated
            self.session.headers.update({
                "Authorization": f"Bearer {updated['access_token']}",
            })

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        """Make a rate-limited GET request. Handles 429 retries and token refresh."""
        self.rate_limiter.wait_if_needed()
        self._ensure_token_valid()

        url = f"{BASE_URL}/{endpoint}"
        headers = {
            "xero-tenant-id": self.tenant_id,
            "Accept": "application/json",
        }

        for attempt in range(self.MAX_RETRIES):
            response = self.session.get(url, headers=headers, params=params)
            self.rate_limiter.record_call(response.headers)
            self.total_api_calls += 1

            if response.status_code == 200:
                return response.json()

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning("Rate limited (429). Waiting %ds...", retry_after)
                time.sleep(retry_after)
                continue

            if response.status_code == 401 and attempt == 0:
                logger.info("Got 401, refreshing token...")
                self.tokens = auth._refresh_token(self.tokens["refresh_token"])
                self.session.headers.update({
                    "Authorization": f"Bearer {self.tokens['access_token']}",
                })
                continue

            if response.status_code in (500, 502, 503) and attempt < self.MAX_RETRIES - 1:
                wait = 2 ** attempt
                logger.warning("Server error %d. Retrying in %ds...", response.status_code, wait)
                time.sleep(wait)
                continue

            if response.status_code == 404:
                logger.debug("Endpoint not found: %s", endpoint)
                return {}

            response.raise_for_status()

        raise RuntimeError(f"Failed after {self.MAX_RETRIES} retries: {url}")

    def get_binary(self, endpoint: str) -> bytes:
        """Download binary content (for attachments)."""
        self.rate_limiter.wait_if_needed()
        self._ensure_token_valid()

        url = f"{BASE_URL}/{endpoint}"
        headers = {
            "xero-tenant-id": self.tenant_id,
        }

        for attempt in range(self.MAX_RETRIES):
            response = self.session.get(url, headers=headers)
            self.rate_limiter.record_call(response.headers)
            self.total_api_calls += 1

            if response.status_code == 200:
                return response.content

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning("Rate limited (429). Waiting %ds...", retry_after)
                time.sleep(retry_after)
                continue

            if response.status_code in (500, 502, 503) and attempt < self.MAX_RETRIES - 1:
                wait = 2 ** attempt
                logger.warning("Server error %d. Retrying in %ds...", response.status_code, wait)
                time.sleep(wait)
                continue

            response.raise_for_status()

        raise RuntimeError(f"Failed after {self.MAX_RETRIES} retries: {url}")

    def fetch_all_pages(self, endpoint: str, response_key: str,
                        paginated: bool = True) -> list:
        """Fetch all pages of a paginated endpoint."""
        all_records = []

        if not paginated:
            data = self.get(endpoint)
            records = data.get(response_key, [])
            all_records.extend(records)
            logger.info("  %d records", len(records))
            return all_records

        page = 1
        first_record_id = None
        while True:
            data = self.get(endpoint, params={"page": page})
            records = data.get(response_key, [])
            if not records:
                break

            # Detect endpoints that ignore pagination (return same data every page)
            if records and page == 1:
                # Capture an identifier from the first record of page 1
                first_record_id = str(records[0]) if records else None
            elif records and page > 1 and first_record_id:
                if str(records[0]) == first_record_id:
                    logger.warning(
                        "  Endpoint %s ignores pagination "
                        "(page %d returned same data as page 1). "
                        "Using page 1 data only.", endpoint, page
                    )
                    break

            all_records.extend(records)
            logger.info("  Page %d: %d records (total: %d)", page, len(records), len(all_records))

            # Xero standard page size is 100; fewer means last page
            if len(records) < 100:
                break

            page += 1

        return all_records
