import re
import time
from typing import Callable, Optional, Sequence
import requests

_PHONE = re.compile(r"\+?\d[\d\s\-]{7,}\d")

class GatewayError(Exception):
    retryable = False
class GatewayUnavailable(GatewayError):
    retryable = True
class GatewayTimeout(GatewayUnavailable):
    pass
class GatewayServerError(GatewayError):
    retryable = True
class GatewayAuthError(GatewayError):
    pass
class GatewayRejected(GatewayError):
    pass

class SMSGateClient:
    def __init__(self, base_url, username, password, *, timeout=8.0, messages_path="/messages", session=None):
        self._base = base_url.rstrip("/")
        self._auth = (username, password)
        self._timeout = timeout
        self._path = "/" + messages_path.strip("/")
        self._session = session or requests.Session()
        self._password = password

    def _safe(self, text):
        text = text.replace(self._password, "***") if self._password else text
        return _PHONE.sub("[number]", text)[:200]

    def _request(self, method, path, **kw):
        try:
            resp = self._session.request(method, self._base + path, auth=self._auth, timeout=self._timeout, **kw)
        except requests.Timeout:
            raise GatewayTimeout(f"Gateway did not answer within {self._timeout:g}s") from None
        except requests.ConnectionError:
            raise GatewayUnavailable("Cannot connect to the gateway (phone offline, app stopped, wrong/changed IP, or different network)") from None
        except requests.RequestException as exc:
            raise GatewayUnavailable(f"Gateway request failed ({type(exc).__name__})") from None
        code = resp.status_code
        if code in (401, 403):
            raise GatewayAuthError(f"Gateway rejected the credentials (HTTP {code})")
        if code >= 500:
            raise GatewayServerError(f"Gateway error HTTP {code}: {self._safe(resp.text)}")
        if code >= 400:
            raise GatewayRejected(f"Gateway refused the request (HTTP {code}): {self._safe(resp.text)}")
        try:
            return resp.json()
        except ValueError:
            raise GatewayRejected("Gateway returned a non-JSON response") from None

    def health(self):
        return self._request("GET", "/health")

    def send(self, text, phone_numbers: Sequence[str], *, message_id=None, ttl=900, priority=100):
        payload = {"textMessage": {"text": text}, "phoneNumbers": list(phone_numbers),
                   "ttl": ttl, "priority": priority, "withDeliveryReport": True}
        if message_id:
            payload["id"] = message_id
        return self._request("POST", self._path, json=payload)

    def get_status(self, gateway_message_id):
        return self._request("GET", f"{self._path}/{gateway_message_id}")

def call_with_retries(fn, *, max_retries, backoff, sleep=time.sleep, on_attempt=None):
    attempt = 0
    while True:
        attempt += 1
        if on_attempt:
            on_attempt(attempt)
        try:
            return fn(), attempt
        except GatewayError as exc:
            if not exc.retryable or attempt > max_retries:
                exc.attempts = attempt
                raise
            sleep(backoff * (2 ** (attempt - 1)))
