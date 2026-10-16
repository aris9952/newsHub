# -*- coding: utf-8 -*-
"""
Resilient network fetching and URL normalization module for NewsHub for NVDA.

Uses only the Python standard library (`urllib.request`, `urllib.parse`, `urllib.error`, `socket`)
for full compatibility with NVDA's embedded Python runtime without external binary dependencies.
"""

import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Set, Tuple

from .i18n import tr

# Honest and standard User-Agent string identifying the add-on
DEFAULT_USER_AGENT = (
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
	"AppleWebKit/537.36 (KHTML, like Gecko) "
	"Chrome/124.0.0.0 Safari/537.36 NewsHubForNVDA/1.0"
)

# Maximum response size limit (5 MB) to prevent excessive memory consumption on abnormal pages
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
DEFAULT_TIMEOUT_SEC = 10

# Allowed domain suffixes for Kompas.com and its official rubric subdomains
ALLOWED_DOMAIN_SUFFIXES: Tuple[str, ...] = (
	"kompas.com",
)

# Tracking query parameters that are safe to strip during canonical URL normalization
SAFE_STRIP_QUERY_PARAMS: Set[str] = {
	"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
	"source", "medium", "campaign", "fbclid", "gclid", "_ga", "_gl", "_t",
	" amp", "amp", "jx", "m",
}

# Allowed HTTP Content-Type prefixes for news HTML pages and RSS/XML feeds
ALLOWED_CONTENT_TYPES: Tuple[str, ...] = (
	"text/html",
	"application/xhtml+xml",
	"application/xml",
	"text/xml",
	"application/rss+xml",
	"text/plain",
)

_rate_limit_lock = threading.Lock()
_last_request_timestamp = 0.0
MIN_REQUEST_INTERVAL_SEC = 0.35


def _log_debug(msg: str) -> None:
	try:
		from logHandler import log
		log.debug(f"NewsHub Network: {msg}")
	except Exception:
		pass


def _log_error(msg: str) -> None:
	try:
		from logHandler import log
		log.error(f"NewsHub Network: {msg}")
	except Exception:
		pass


class NewsHubNetworkError(Exception):
	"""Base exception for network errors with screen-reader-friendly localized messages."""
	def __init__(self, user_message: str, technical_detail: str = "", status_code: int = 0):
		super().__init__(user_message)
		self.user_message = user_message
		self.technical_detail = technical_detail
		self.status_code = status_code


class URLValidationError(NewsHubNetworkError):
	"""Raised when a URL is malformed or outside the permitted news domains."""


class DNSOrConnectionError(NewsHubNetworkError):
	"""Raised on DNS resolution failure, network disconnection, or connection timeout."""


class HTTPStatusError(NewsHubNetworkError):
	"""Raised on HTTP status errors (403, 404, 429, 5xx)."""


class InvalidContentTypeError(NewsHubNetworkError):
	"""Raised when the HTTP response Content-Type is not valid HTML or XML."""


class ResponseTooLargeError(NewsHubNetworkError):
	"""Raised when the HTTP response body exceeds the safe byte threshold."""


def validate_url(url: str, allowed_suffixes: Tuple[str, ...] = ALLOWED_DOMAIN_SUFFIXES) -> urllib.parse.ParseResult:
	"""Validate URL scheme and domain prior to making any network request."""
	if not url or not isinstance(url, str):
		raise URLValidationError(tr("err_url_empty"))

	cleaned = url.strip()
	parsed = urllib.parse.urlparse(cleaned)
	if parsed.scheme.lower() not in ("http", "https"):
		raise URLValidationError(
			tr("err_url_scheme"),
			technical_detail=f"Invalid scheme: {parsed.scheme}",
		)

	hostname = (parsed.hostname or "").lower().strip(".")
	if not hostname:
		raise URLValidationError(tr("err_url_no_domain"))

	if allowed_suffixes:
		domain_ok = any(
			hostname == suffix or hostname.endswith("." + suffix)
			for suffix in allowed_suffixes
		)
		if not domain_ok:
			raise URLValidationError(
				tr("err_url_domain_blocked", hostname=hostname),
				technical_detail=f"Blocked hostname: {hostname}",
			)

	return parsed


def normalize_canonical_url(url: str, keep_page_param: bool = False) -> str:
	"""
	Normalize an article URL into a canonical form suitable for safe deduplication:
	- Upgrades http to https for kompas.com.
	- Strips URL fragments (#...).
	- Strips tracking query parameters (utm_*, source, fbclid, etc.) while preserving article path identity.
	- Removes duplicate slashes or trailing slashes on `/read/` article paths.
	"""
	if not url or not isinstance(url, str):
		return ""
	raw = url.strip()
	if raw.startswith("//"):
		raw = "https:" + raw

	try:
		parsed = urllib.parse.urlparse(raw)
	except Exception:
		return raw.split("?")[0].split("#")[0]

	scheme = "https" if parsed.scheme.lower() in ("http", "https") else parsed.scheme.lower()
	netloc = (parsed.netloc or "").lower()
	path = re.sub(r"/{2,}", "/", parsed.path or "/")
	if "/read/" in path and path.endswith("/") and len(path) > 6:
		path = path.rstrip("/")

	query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
	filtered_pairs = []
	for k, v in query_pairs:
		k_low = k.strip().lower()
		if k_low in SAFE_STRIP_QUERY_PARAMS or k_low.startswith("utm_"):
			continue
		if k_low == "page" and not keep_page_param:
			continue
		filtered_pairs.append((k, v))

	new_query = urllib.parse.urlencode(filtered_pairs, doseq=True)
	return urllib.parse.urlunparse((scheme, netloc, path, "", new_query, ""))


def _detect_charset(headers, raw_bytes: bytes) -> str:
	"""Detect character encoding from HTTP headers or HTML meta tags."""
	if headers is not None:
		try:
			charset = headers.get_content_charset()
			if charset:
				return charset.strip()
		except Exception:
			pass
		content_type = headers.get("Content-Type", "")
		match = re.search(r"charset=([\w\-]+)", content_type, re.IGNORECASE)
		if match:
			return match.group(1).strip()

	head_sample = raw_bytes[:2048].decode("ascii", errors="ignore")
	meta_match = re.search(r'charset=["\']?([\w\-]+)', head_sample, re.IGNORECASE)
	if meta_match:
		return meta_match.group(1).strip()

	return "utf-8"


def _respect_polite_rate_limit() -> None:
	"""Enforce a polite delay between consecutive HTTP requests to avoid overloading news servers."""
	global _last_request_timestamp
	with _rate_limit_lock:
		now = time.monotonic()
		elapsed = now - _last_request_timestamp
		if elapsed < MIN_REQUEST_INTERVAL_SEC:
			time.sleep(MIN_REQUEST_INTERVAL_SEC - elapsed)
		_last_request_timestamp = time.monotonic()


def fetch_html(
	target_url: str,
	timeout: int = DEFAULT_TIMEOUT_SEC,
	max_bytes: int = MAX_RESPONSE_BYTES,
	site_label: str = "Kompas.com",
) -> str:
	"""Fetch an HTML/XML document from `target_url` with full validation and granular error handling."""
	validate_url(target_url)
	_respect_polite_rate_limit()

	headers = {
		"User-Agent": DEFAULT_USER_AGENT,
		"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
		"Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
		"Cache-Control": "no-cache",
	}

	req = urllib.request.Request(target_url, headers=headers, method="GET")
	try:
		with urllib.request.urlopen(req, timeout=timeout) as resp:
			status_code = getattr(resp, "status", 200) or 200
			resp_headers = getattr(resp, "headers", None)

			if resp_headers is not None:
				content_type = (resp_headers.get("Content-Type") or "").lower()
				if content_type and not any(ct in content_type for ct in ALLOWED_CONTENT_TYPES):
					raise InvalidContentTypeError(
						tr("err_invalid_content_type", site_label=site_label),
						technical_detail=f"Unsupported Content-Type: {content_type}",
						status_code=status_code,
					)

				content_length = resp_headers.get("Content-Length")
				if content_length:
					try:
						if int(content_length) > max_bytes:
							raise ResponseTooLargeError(
								tr("err_response_too_large", site_label=site_label),
								technical_detail=f"Content-Length {content_length} > {max_bytes}",
							)
					except ValueError:
						pass

			# Read response stream in chunks while enforcing the maximum byte limit
			chunks = []
			bytes_read = 0
			chunk_size = 65536
			while True:
				chunk = resp.read(chunk_size)
				if not chunk:
					break
				bytes_read += len(chunk)
				if bytes_read > max_bytes:
					raise ResponseTooLargeError(
						tr("err_response_stream_too_large", site_label=site_label),
						technical_detail=f"Stream exceeded {max_bytes} bytes",
					)
				chunks.append(chunk)

			raw_bytes = b"".join(chunks)
			charset = _detect_charset(resp_headers, raw_bytes)
			try:
				text = raw_bytes.decode(charset, errors="replace")
			except LookupError:
				text = raw_bytes.decode("utf-8", errors="replace")

			if not text or len(text.strip()) < 100:
				raise NewsHubNetworkError(
					tr("err_empty_response", site_label=site_label),
					technical_detail=f"Response length too short ({len(text)} chars)",
				)
			return text

	except NewsHubNetworkError:
		raise
	except urllib.error.HTTPError as e:
		code = e.code
		_log_error(f"HTTPError {code} for URL {target_url}: {e.reason}")
		if code == 403:
			msg = tr("err_http_403", site_label=site_label)
		elif code == 404:
			msg = tr("err_http_404", site_label=site_label)
		elif code == 429:
			msg = tr("err_http_429", site_label=site_label)
		elif 500 <= code < 600:
			msg = tr("err_http_5xx", site_label=site_label, code=code)
		else:
			msg = tr("err_http_other", site_label=site_label, code=code)
		raise HTTPStatusError(msg, technical_detail=str(e), status_code=code) from e

	except urllib.error.URLError as e:
		reason = e.reason
		_log_error(f"URLError for URL {target_url}: {reason}")
		if isinstance(reason, socket.timeout) or "timed out" in str(reason).lower():
			msg = tr("err_timeout", site_label=site_label)
		elif isinstance(reason, socket.gaierror) or "getaddrinfo" in str(reason).lower() or "name or service not known" in str(reason).lower():
			msg = tr("err_dns", site_label=site_label)
		elif isinstance(reason, ssl.SSLError):
			msg = tr("err_ssl", site_label=site_label)
		else:
			msg = tr("err_connection_generic", site_label=site_label)
		raise DNSOrConnectionError(msg, technical_detail=str(e)) from e

	except socket.timeout as e:
		_log_error(f"Socket timeout for URL {target_url}: {e}")
		raise DNSOrConnectionError(
			tr("err_read_timeout", site_label=site_label),
			technical_detail=str(e),
		) from e

	except Exception as e:
		_log_error(f"Unexpected network error for URL {target_url}: {e}")
		raise NewsHubNetworkError(
			tr("err_unexpected_network", site_label=site_label),
			technical_detail=str(e),
		) from e
