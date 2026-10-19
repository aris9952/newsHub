# -*- coding: utf-8 -*-
"""
Resilient network fetching, SSL certificate management, anti-403 fallback,
and URL normalization module for NewsHub for NVDA.

Uses Python standard library (`urllib.request`, `http.cookiejar`, `ssl`, `gzip`, `zlib`, `subprocess`)
and bundles a complete CA certificate store (`certs/cacert.pem`) so the add-on works reliably
on clean Windows machines that only have NVDA installed (without standalone Python).
"""

import gzip
import http.cookiejar
import os
import re
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from typing import Dict, Optional, Set, Tuple

try:
	import addonHandler
	addonHandler.initTranslation()
except Exception:
	def _(s: str) -> str:
		return s

# Standard modern browser User-Agent without custom bot suffix to avoid WAF 403 blocks
DEFAULT_USER_AGENT = (
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
	"AppleWebKit/537.36 (KHTML, like Gecko) "
	"Chrome/131.0.0.0 Safari/537.36"
)

MOBILE_FALLBACK_USER_AGENT = (
	"Mozilla/5.0 (Linux; Android 14; Pixel 8) "
	"AppleWebKit/537.36 (KHTML, like Gecko) "
	"Chrome/131.0.0.0 Mobile Safari/537.36"
)

# Path to bundled Mozilla CA certificate bundle inside the add-on package
BUNDLED_CACERT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs", "cacert.pem")

# Maximum response size (5 MB) to prevent out-of-memory errors on abnormal payloads
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
DEFAULT_TIMEOUT_SEC = 12

# Allowed domain suffixes for supported news portals and official RSS fallbacks
ALLOWED_DOMAIN_SUFFIXES: Tuple[str, ...] = (
	"kompas.com",
	"detik.com",
	"detik.net.id",
	"cnnindonesia.com",
	"cnbcindonesia.com",
	"tempo.co",
	"tmpo.co",
	"tstatic.net",
	"kompas.tv",
	"kgnow.com",
	"youtube.com",
	"youtu.be",
	"ytimg.com",
	"dailymotion.com",
	"news.google.com",
	"googleusercontent.com",
	"gstatic.com",
)

# Tracking and pagination query parameters that are safely stripped during canonical URL normalization
SAFE_STRIP_QUERY_PARAMS: Set[str] = {
	"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
	"source", "medium", "campaign", "fbclid", "gclid", "_ga", "_gl", "_t",
	" amp", "amp", "jx", "m", "tag_from", "nhd", "single",
}

# Permitted HTTP Content-Type prefixes for news HTML and RSS/XML feeds
ALLOWED_CONTENT_TYPES: Tuple[str, ...] = (
	"text/html",
	"application/xhtml+xml",
	"application/xml",
	"text/xml",
	"application/rss+xml",
	"application/atom+xml",
	"text/plain",
)

_rate_limit_lock = threading.Lock()
_last_request_timestamp = 0.0
MIN_REQUEST_INTERVAL_SEC = 0.40

# Persistent session cookie jar to preserve Cloudflare (__cf_bm, _cfuvid) and portal session cookies
_SESSION_COOKIE_JAR = http.cookiejar.CookieJar()
_CURL_COOKIE_FILE = os.path.join(tempfile.gettempdir(), "newshub_nvda_cookies.txt")


def _log_debug(msg: str) -> None:
	"""Log a debug message to NVDA logHandler when running inside NVDA."""
	try:
		from logHandler import log
		log.debug(f"NewsHub Network: {msg}")
	except Exception:
		pass


def _log_error(msg: str) -> None:
	"""Log an error message to NVDA logHandler when running inside NVDA."""
	try:
		from logHandler import log
		log.error(f"NewsHub Network: {msg}")
	except Exception:
		pass


class NewsHubNetworkError(Exception):
	"""Base network exception carrying a screen-reader-friendly user message."""
	def __init__(self, user_message: str, technical_detail: str = "", status_code: int = 0):
		super().__init__(user_message)
		self.user_message = user_message
		self.technical_detail = technical_detail
		self.status_code = status_code


class URLValidationError(NewsHubNetworkError):
	"""Raised when a URL is malformed or outside the allowed news domains."""


class DNSOrConnectionError(NewsHubNetworkError):
	"""Raised on DNS failure, network disconnection, or socket timeout."""


class HTTPStatusError(NewsHubNetworkError):
	"""Raised on HTTP status errors (403, 404, 429, 5xx)."""


class InvalidContentTypeError(NewsHubNetworkError):
	"""Raised when the response Content-Type is not valid HTML or XML."""


class ResponseTooLargeError(NewsHubNetworkError):
	"""Raised when the response body exceeds the safe size limit."""


def validate_url(url: str, allowed_suffixes: Tuple[str, ...] = ALLOWED_DOMAIN_SUFFIXES) -> urllib.parse.ParseResult:
	"""
	Validate the URL scheme and hostname before performing any network request.
	"""
	if not url or not isinstance(url, str):
		raise URLValidationError(_('The news URL is empty or invalid.'))

	cleaned = url.strip()
	parsed = urllib.parse.urlparse(cleaned)
	if parsed.scheme.lower() not in ("http", "https"):
		raise URLValidationError(
			_('Unsupported URL scheme. Only HTTP and HTTPS are allowed.'),
			technical_detail=f"Invalid scheme: {parsed.scheme}",
		)

	hostname = (parsed.hostname or "").lower().strip(".")
	if not hostname:
		raise URLValidationError(_('Domain name was not found in the news URL.'))

	if allowed_suffixes:
		domain_ok = any(
			hostname == suffix or hostname.endswith("." + suffix)
			for suffix in allowed_suffixes
		)
		if not domain_ok:
			raise URLValidationError(
				_("Domain '{host}' is outside the allowed news source domains.").format(host=hostname),
				technical_detail=f"Blocked hostname: {hostname}",
			)

	return parsed


def normalize_canonical_url(url: str, keep_page_param: bool = False) -> str:
	"""
	Normalize an article URL into a canonical form suitable for safe deduplication.
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
	if ("/read/" in path or "/d-" in path or "/berita/" in path) and path.endswith("/") and len(path) > 6:
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


def _build_ssl_context(verify: bool = True) -> ssl.SSLContext:
	"""
	Build an SSLContext that loads both the Windows system store and our bundled
	`certs/cacert.pem` file. When `verify=False`, builds an unverified context
	as a fallback for servers that omit intermediate CA certificates.
	"""
	if not verify:
		ctx = ssl._create_unverified_context()
		ctx.check_hostname = False
		ctx.verify_mode = ssl.CERT_NONE
		return ctx

	ctx = ssl.create_default_context()
	try:
		ctx.load_default_certs()
	except Exception:
		pass

	if os.path.isfile(BUNDLED_CACERT_PATH):
		try:
			ctx.load_verify_locations(cafile=BUNDLED_CACERT_PATH)
		except Exception as e:
			_log_debug(f"Failed to load bundled cacert.pem: {e}")

	return ctx


def _build_browser_headers(target_url: str, user_agent: str = DEFAULT_USER_AGENT) -> Dict[str, str]:
	"""Build standard modern browser HTTP headers including Referer and Sec-Fetch metadata."""
	parsed = urllib.parse.urlparse(target_url)
	origin = f"{parsed.scheme}://{parsed.netloc}/" if parsed.scheme and parsed.netloc else "https://www.google.com/"
	return {
		"User-Agent": user_agent,
		"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
		"Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
		"Accept-Encoding": "gzip, deflate",
		"Referer": origin,
		"Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
		"Sec-Ch-Ua-Mobile": "?0",
		"Sec-Ch-Ua-Platform": '"Windows"',
		"Sec-Fetch-Dest": "document",
		"Sec-Fetch-Mode": "navigate",
		"Sec-Fetch-Site": "same-origin",
		"Sec-Fetch-User": "?1",
		"Upgrade-Insecure-Requests": "1",
		"Cache-Control": "max-age=0",
	}


def _decompress_body(raw_bytes: bytes, content_encoding: str) -> bytes:
	"""Decompress gzip or deflate HTTP response bodies transparently."""
	enc = (content_encoding or "").lower().strip()
	if not raw_bytes:
		return raw_bytes
	try:
		if "gzip" in enc or raw_bytes[:2] == b"\x1f\x8b":
			return gzip.decompress(raw_bytes)
		if "deflate" in enc:
			try:
				return zlib.decompress(raw_bytes)
			except zlib.error:
				return zlib.decompress(raw_bytes, -zlib.MAX_WBITS)
	except Exception as e:
		_log_debug(f"Decompression fallback notice: {e}")
	return raw_bytes


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
	"""Enforce a polite delay between network requests to avoid rate-limiting."""
	global _last_request_timestamp
	with _rate_limit_lock:
		now = time.monotonic()
		elapsed = now - _last_request_timestamp
		if elapsed < MIN_REQUEST_INTERVAL_SEC:
			time.sleep(MIN_REQUEST_INTERVAL_SEC - elapsed)
		_last_request_timestamp = time.monotonic()


def _is_ssl_verification_error(exc: BaseException) -> bool:
	"""Return True if an exception was caused by an SSL certificate verification error."""
	if isinstance(exc, ssl.SSLError):
		return True
	if isinstance(exc, urllib.error.URLError) and isinstance(getattr(exc, "reason", None), ssl.SSLError):
		return True
	msg = str(exc).lower()
	return any(
		k in msg
		for k in (
			"certificate_verify_failed",
			"certificate verify failed",
			"unable to get local issuer certificate",
			"self signed certificate",
			"ssl:",
		)
	)


def _fetch_via_windows_curl(target_url: str, timeout: int = DEFAULT_TIMEOUT_SEC) -> Optional[str]:
	"""
	Fallback fetcher using Windows built-in `curl.exe` (which uses Windows Schannel TLS
	rather than OpenSSL, bypassing JA3 TLS fingerprint 403 blocks and using Windows certs).
	Executes silently with CREATE_NO_WINDOW so no console flashes on screen.
	"""
	curl_candidates = []
	sys_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
	win_curl = os.path.join(sys_root, "System32", "curl.exe")
	if os.path.isfile(win_curl):
		curl_candidates.append(win_curl)
	curl_candidates.append("curl")

	parsed = urllib.parse.urlparse(target_url)
	referer = f"{parsed.scheme}://{parsed.netloc}/" if parsed.scheme and parsed.netloc else "https://www.google.com/"
	creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0

	for curl_bin in curl_candidates:
		for insecure_flag in ([], ["-k"]):
			cmd = [
				curl_bin,
				"-s",
				"-L",
				"--compressed",
				"--max-time", str(max(5, int(timeout))),
				"-b", _CURL_COOKIE_FILE,
				"-c", _CURL_COOKIE_FILE,
				"-A", DEFAULT_USER_AGENT,
				"-e", referer,
				"-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
				"-H", "Accept-Language: id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
				"-H", 'Sec-Ch-Ua: "Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
				"-H", "Sec-Ch-Ua-Mobile: ?0",
				"-H", 'Sec-Ch-Ua-Platform: "Windows"',
				"-H", "Sec-Fetch-Dest: document",
				"-H", "Sec-Fetch-Mode: navigate",
				"-H", "Sec-Fetch-Site: same-origin",
				"-H", "Upgrade-Insecure-Requests: 1",
			] + insecure_flag + [target_url]
			try:
				proc = subprocess.run(
					cmd,
					stdout=subprocess.PIPE,
					stderr=subprocess.PIPE,
					timeout=timeout + 3,
					creationflags=creation_flags,
				)
				if proc.returncode == 0 and proc.stdout and len(proc.stdout) > 200:
					text = proc.stdout.decode("utf-8", errors="replace")
					# Ensure it is not a Cloudflare challenge page
					low_sample = text[:2048].lower()
					if "<title>just a moment..." not in low_sample and "cf-browser-verification" not in low_sample:
						_log_debug(f"Successfully fetched {target_url} via curl fallback.")
						return text
			except Exception as e:
				_log_debug(f"curl fallback attempt failed for {target_url}: {e}")
				break
	return None


def _fetch_via_urllib_once(
	target_url: str,
	timeout: int,
	max_bytes: int,
	site_label: str,
	verify_ssl: bool = True,
	user_agent: str = DEFAULT_USER_AGENT,
) -> str:
	"""Perform a single HTTP GET request via urllib with CookieJar, custom SSLContext, and gzip decoding."""
	ssl_ctx = _build_ssl_context(verify=verify_ssl)
	opener = urllib.request.build_opener(
		urllib.request.HTTPCookieProcessor(_SESSION_COOKIE_JAR),
		urllib.request.HTTPSHandler(context=ssl_ctx),
	)
	headers = _build_browser_headers(target_url, user_agent=user_agent)
	req = urllib.request.Request(target_url, headers=headers, method="GET")

	with opener.open(req, timeout=timeout) as resp:
		status_code = getattr(resp, "status", 200) or 200
		resp_headers = getattr(resp, "headers", None)
		content_encoding = ""

		if resp_headers is not None:
			content_type = (resp_headers.get("Content-Type") or "").lower()
			content_encoding = resp_headers.get("Content-Encoding") or ""
			if content_type and not any(ct in content_type for ct in ALLOWED_CONTENT_TYPES):
				raise InvalidContentTypeError(
					_('Response from {site} is not a supported text/HTML news page.').format(site=site_label, site_label=site_label),
					technical_detail=f"Unsupported Content-Type: {content_type}",
					status_code=status_code,
				)

			content_length = resp_headers.get("Content-Length")
			if content_length:
				try:
					if int(content_length) > max_bytes:
						raise ResponseTooLargeError(
							_('Page size from {site} is too large to load safely.').format(site=site_label, site_label=site_label),
							technical_detail=f"Content-Length {content_length} > {max_bytes}",
						)
				except ValueError:
					pass

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
					_('Response size from {site} exceeded the safe limit (5 MB).').format(site=site_label, site_label=site_label),
					technical_detail=f"Stream exceeded {max_bytes} bytes",
				)
			chunks.append(chunk)

		raw_bytes = _decompress_body(b"".join(chunks), content_encoding)
		charset = _detect_charset(resp_headers, raw_bytes)
		try:
			text = raw_bytes.decode(charset, errors="replace")
		except LookupError:
			text = raw_bytes.decode("utf-8", errors="replace")

		if not text or len(text.strip()) < 80:
			raise NewsHubNetworkError(
				_('Page from {site} returned an empty or incomplete response.').format(site=site_label, site_label=site_label),
				technical_detail=f"Response length too short ({len(text)} chars)",
			)
		return text


def fetch_html(
	target_url: str,
	timeout: int = DEFAULT_TIMEOUT_SEC,
	max_bytes: int = MAX_RESPONSE_BYTES,
	site_label: str = "Kompas.com",
) -> str:
	"""
	Fetch an HTML or XML document from `target_url` with full validation,
	bundled CA certificate verification + automatic unverified SSL retry,
	and Windows `curl.exe` Schannel anti-403 fallback.
	"""
	validate_url(target_url)
	_respect_polite_rate_limit()

	try:
		return _fetch_via_urllib_once(
			target_url=target_url,
			timeout=timeout,
			max_bytes=max_bytes,
			site_label=site_label,
			verify_ssl=True,
			user_agent=DEFAULT_USER_AGENT,
		)
	except (InvalidContentTypeError, ResponseTooLargeError, URLValidationError):
		raise
	except Exception as first_exc:
		# 1. If SSL verification failed (e.g. missing intermediate CA on news.kompas.com),
		# immediately retry with an unverified SSL context so the user is never blocked.
		if _is_ssl_verification_error(first_exc):
			_log_debug(f"SSL verification failed for {target_url} ({first_exc}); retrying with unverified SSL context.")
			try:
				return _fetch_via_urllib_once(
					target_url=target_url,
					timeout=timeout,
					max_bytes=max_bytes,
					site_label=site_label,
					verify_ssl=False,
					user_agent=DEFAULT_USER_AGENT,
				)
			except Exception as second_exc:
				first_exc = second_exc

		# 2. If HTTP 403 / 503 or persistent SSL error occurred (e.g. Cloudflare WAF on tempo.co),
		# try mobile User-Agent with unverified SSL context, then Windows native curl.exe (Schannel TLS).
		is_http_403_or_503 = (
			isinstance(first_exc, urllib.error.HTTPError) and first_exc.code in (403, 503)
		)
		if is_http_403_or_503 or _is_ssl_verification_error(first_exc):
			curl_text = _fetch_via_windows_curl(target_url, timeout=timeout)
			if curl_text:
				return curl_text

			try:
				return _fetch_via_urllib_once(
					target_url=target_url,
					timeout=timeout,
					max_bytes=max_bytes,
					site_label=site_label,
					verify_ssl=False,
					user_agent=MOBILE_FALLBACK_USER_AGENT,
				)
			except Exception:
				pass

		# Raise appropriate localized error if all attempts failed
		if isinstance(first_exc, NewsHubNetworkError):
			raise first_exc
		if isinstance(first_exc, urllib.error.HTTPError):
			code = first_exc.code
			_log_error(f"HTTPError {code} for URL {target_url}: {first_exc.reason}")
			if code == 403:
				msg = _('Access to {site_label} was denied by the server (HTTP 403). This rubric or article may be restricted.').format(site=site_label, site_label=site_label)
			elif code == 404:
				msg = _('The requested page or rubric on {site_label} was not found (HTTP 404).').format(site=site_label, site_label=site_label)
			elif code == 429:
				msg = _('Too many requests to {site_label} (HTTP 429). Please wait a moment and try again.').format(site=site_label, site_label=site_label)
			elif 500 <= code < 600:
				msg = _('{site_label} server is currently experiencing issues (HTTP {code}). Please try again later.').format(site=site_label, site_label=site_label, code=code)
			else:
				msg = _('Failed to load page from {site_label} (HTTP status {code}).').format(site=site_label, site_label=site_label, code=code)
			raise HTTPStatusError(msg, technical_detail=str(first_exc), status_code=code) from first_exc

		if isinstance(first_exc, urllib.error.URLError):
			reason = first_exc.reason
			_log_error(f"URLError for URL {target_url}: {reason}")
			if isinstance(reason, socket.timeout) or "timed out" in str(reason).lower():
				msg = _('Connection to {site} timed out. Please check your internet connection and try again.').format(site=site_label, site_label=site_label)
			elif isinstance(reason, socket.gaierror) or "getaddrinfo" in str(reason).lower() or "name or service not known" in str(reason).lower():
				msg = _('Failed to reach {site_label} (DNS error or no network). Please check your internet connection and try again.').format(site=site_label, site_label=site_label)
			elif isinstance(reason, ssl.SSLError):
				msg = _('Failed to verify a secure connection (SSL/TLS) to {site_label}.').format(site=site_label, site_label=site_label)
			else:
				msg = _('Failed to connect to {site}. Please check your internet connection and try again.').format(site=site_label, site_label=site_label)
			raise DNSOrConnectionError(msg, technical_detail=str(first_exc)) from first_exc

		if isinstance(first_exc, socket.timeout):
			_log_error(f"Socket timeout for URL {target_url}: {first_exc}")
			raise DNSOrConnectionError(
				_('Reading data from {site} timed out. Please check your internet connection and try again.').format(site=site_label, site_label=site_label),
				technical_detail=str(first_exc),
			) from first_exc

		_log_error(f"Unexpected network error for URL {target_url}: {first_exc}")
		raise NewsHubNetworkError(
			_('An error occurred while contacting {site}. Please check your internet connection and try again.').format(site=site_label, site_label=site_label),
			technical_detail=str(first_exc),
		) from first_exc


def fetch_binary(
	target_url: str,
	timeout: int = DEFAULT_TIMEOUT_SEC,
	max_bytes: int = 10 * 1024 * 1024,
	site_label: str = "Media",
) -> Tuple[bytes, str]:
	"""
	Fetch binary media content (such as article photos) from `target_url` with
	bundled CA certificate verification, unverified SSL retry, and Windows curl fallback.
	Returns `(raw_bytes, content_type)`.
	"""
	validate_url(target_url)
	_respect_polite_rate_limit()

	def _try_urllib(verify_ssl: bool, ua: str) -> Tuple[bytes, str]:
		ssl_ctx = _build_ssl_context(verify=verify_ssl)
		opener = urllib.request.build_opener(
			urllib.request.HTTPCookieProcessor(_SESSION_COOKIE_JAR),
			urllib.request.HTTPSHandler(context=ssl_ctx),
		)
		headers = _build_browser_headers(target_url, user_agent=ua)
		headers["Accept"] = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
		req = urllib.request.Request(target_url, headers=headers, method="GET")
		with opener.open(req, timeout=timeout) as resp:
			resp_headers = getattr(resp, "headers", None)
			content_type = "image/jpeg"
			content_encoding = ""
			if resp_headers is not None:
				content_type = (resp_headers.get("Content-Type") or "image/jpeg").split(";")[0].strip().lower()
				content_encoding = resp_headers.get("Content-Encoding") or ""
			chunks = []
			bytes_read = 0
			while True:
				chunk = resp.read(65536)
				if not chunk:
					break
				bytes_read += len(chunk)
				if bytes_read > max_bytes:
					raise ResponseTooLargeError(
						_('Response size from {site} exceeded the safe limit (5 MB).').format(site=site_label, site_label=site_label)
					)
				chunks.append(chunk)
			raw = _decompress_body(b"".join(chunks), content_encoding)
			if not raw:
				raise NewsHubNetworkError(
					_('Page from {site} returned an empty or incomplete response.').format(site=site_label, site_label=site_label)
				)
			return raw, content_type

	try:
		return _try_urllib(verify_ssl=True, ua=DEFAULT_USER_AGENT)
	except Exception as first_exc:
		try:
			return _try_urllib(verify_ssl=False, ua=DEFAULT_USER_AGENT)
		except Exception:
			pass

		# Fallback to Windows curl.exe for binary download
		curl_candidates = []
		sys_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
		win_curl = os.path.join(sys_root, "System32", "curl.exe")
		if os.path.isfile(win_curl):
			curl_candidates.append(win_curl)
		curl_candidates.append("curl")
		creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
		for curl_bin in curl_candidates:
			try:
				proc = subprocess.run(
					[curl_bin, "-s", "-L", "-k", "--max-time", str(max(5, int(timeout))), "-A", DEFAULT_USER_AGENT, target_url],
					stdout=subprocess.PIPE,
					stderr=subprocess.PIPE,
					timeout=timeout + 3,
					creationflags=creation_flags,
				)
				if proc.returncode == 0 and proc.stdout and len(proc.stdout) > 64:
					return proc.stdout, "image/jpeg"
			except Exception:
				break

		raise NewsHubNetworkError(
			_('An error occurred while contacting {site}. Please check your internet connection and try again.').format(site=site_label, site_label=site_label),
			technical_detail=str(first_exc),
		) from first_exc
