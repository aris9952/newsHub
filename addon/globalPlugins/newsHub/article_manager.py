# -*- coding: utf-8 -*-
"""
Article state, TTL cache, race-condition guard, and background worker manager for NewsHub for NVDA.
"""

import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from .detik_parser import (
	detect_detik_all_pages_url,
	parse_detik_article_html,
	parse_detik_rss_or_headlines,
)
from .formatter import calculate_reading_time_minutes
try:
	import addonHandler
	addonHandler.initTranslation()
except Exception:
	def _(s: str) -> str:
		return s
from .kompas_parser import (
	detect_kompas_all_pages_url,
	parse_kompas_article_html,
	parse_rss_or_Headline_feed,
)
from .models import Article, ArticleStatus, RubricConfig, SiteConfig
from .network import NewsHubNetworkError, fetch_html, normalize_canonical_url
from .portal_parsers import (
	TEMPO_RUBRIC_FALLBACK_FEEDS,
	detect_portal_all_pages_url,
	parse_cnbc_rss_or_headlines,
	parse_cnn_rss_or_headlines,
	parse_portal_article_html,
	parse_tempo_rss_or_headlines,
	parse_tempo_syndication_xml,
)


def _log_debug(msg: str) -> None:
	"""Log a debug message to the NVDA log handler when running inside NVDA."""
	try:
		from logHandler import log
		log.debug(f"NewsHub ArticleManager: {msg}")
	except Exception:
		pass



def _extract_stream_url_from_embed_html(embed_html: str) -> str:
	"""Extract a direct HTML5 video stream URL (.mp4, .webm, .m3u8) from a portal embed page."""
	if not embed_html:
		return ""
	import re as _re
	for m in _re.finditer(
		r"https?://[^\"\x27\s<>]+\.(?:mp4|webm)(?:\?[^\"\x27\s<>]*)?",
		embed_html,
		flags=_re.IGNORECASE,
	):
		candidate = m.group(0).replace("\\/", "/")
		if not any(bad in candidate.lower() for bad in ("ads", "preroll", "bumper", "banner")):
			return candidate
	for m_hls in _re.finditer(
		r"https?://[^\"\x27\s<>]+\.m3u8(?:\?[^\"\x27\s<>]*)?",
		embed_html,
		flags=_re.IGNORECASE,
	):
		candidate = m_hls.group(0).replace("\\/", "/")
		if not any(bad in candidate.lower() for bad in ("ads", "preroll", "bumper")):
			return candidate
	return ""


def _enrich_parsed_video_streams(parsed: dict, site_label: str) -> None:
	"""
	Resolve direct HTML5 `.mp4` / `.m3u8` stream URLs for portal video embed pages
	(such as 20Detik, CNN Indonesia TV, CNBC Indonesia TV, or Kompas video embeds)
	so the HTML article reader can render native `<video controls>` elements directly.
	"""
	videos = parsed.get("videos") or []
	blocks = parsed.get("content") or []
	if not videos and not any(b.get("type") == "video" for b in blocks):
		return

	stream_map = {}
	for v in videos[:3]:
		v_url = (v.get("url") or "").strip()
		v_stream = (v.get("stream_url") or "").strip()
		if v_stream or not v_url:
			if v_url and v_stream:
				stream_map[v_url.lower()] = v_stream
			continue
		low = v_url.lower()
		if any(ext in low for ext in (".mp4", ".webm", ".ogg", ".m3u8")):
			v["stream_url"] = v_url
			stream_map[low] = v_url
			continue
		if any(dom in low for dom in ("detik.com", "cnnindonesia.com", "cnbcindonesia.com", "kompas.com", "tempo.co")):
			try:
				embed_html = fetch_html(v_url, timeout=6, site_label=site_label)
				found_stream = _extract_stream_url_from_embed_html(embed_html)
				if found_stream:
					v["stream_url"] = found_stream
					stream_map[low] = found_stream
			except Exception as e:
				_log_debug(f"Video embed stream lookup notice for {v_url}: {e}")

	for b in blocks:
		if b.get("type") == "video":
			b_url = (b.get("url") or "").strip().lower()
			if b_url and not b.get("stream_url") and b_url in stream_map:
				b["stream_url"] = stream_map[b_url]


class _RubricCacheEntry:
	"""Session cache entry storing fetched articles and timestamp for a rubric."""
	__slots__ = ("articles", "fetched_at")

	def __init__(self, articles: List[Article], fetched_at: float):
		self.articles = list(articles)
		self.fetched_at = fetched_at


class ArticleManager:
	"""
	Manage rubric article list fetching, full article content extraction,
	session TTL caching, and stale request cancellation (race-condition guard).
	"""
	def __init__(self, cache_ttl_sec: int = 180, max_articles: int = 40):
		self._lock = threading.RLock()
		self.cache_ttl_sec = max(30, int(cache_ttl_sec or 180))
		self.max_articles = max(10, int(max_articles or 40))

		# Cache article lists keyed by (site_id, rubric_id)
		self._rubric_cache: Dict[Tuple[str, str], _RubricCacheEntry] = {}
		# Cache individual articles keyed by canonical_url to avoid re-downloading loaded content
		self._article_cache: Dict[str, Article] = {}

		# Request sequence tokens to prevent stale background responses from overwriting newer selections
		self._rubric_request_seq: int = 0
		self._article_request_seq: int = 0
		self._bg_refresh_in_progress: bool = False
		self._shutting_down: bool = False

	def configure(self, cache_ttl_sec: int, max_articles: int) -> None:
		"""Update cache TTL and maximum article count settings dynamically."""
		with self._lock:
			self.cache_ttl_sec = max(30, int(cache_ttl_sec or 180))
			self.max_articles = max(10, int(max_articles or 40))

	def shutdown(self) -> None:
		"""Mark the manager as shutting down so in-flight background callbacks are ignored."""
		with self._lock:
			self._shutting_down = True
			self._rubric_request_seq += 1
			self._article_request_seq += 1

	def cleanup_expired_cache(self) -> None:
		"""Evict expired rubric and article cache entries to keep memory usage bounded."""
		now = time.time()
		article_max_age = max(self.cache_ttl_sec * 4, 900)
		with self._lock:
			expired_rubrics = [
				k for k, v in self._rubric_cache.items()
				if (now - v.fetched_at) > article_max_age
			]
			for k in expired_rubrics:
				del self._rubric_cache[k]

			expired_articles = [
				url for url, art in self._article_cache.items()
				if (now - art.fetched_at) > article_max_age
			]
			for url in expired_articles:
				del self._article_cache[url]

	def get_cached_rubric_articles(
		self,
		site_id: str,
		rubric_id: str,
		allow_expired: bool = False,
	) -> Optional[List[Article]]:
		"""Return the cached list of articles for a rubric if present and valid."""
		key = (site_id, rubric_id)
		with self._lock:
			entry = self._rubric_cache.get(key)
			if entry is None:
				return None
			if not allow_expired and (time.time() - entry.fetched_at) > self.cache_ttl_sec:
				return None
			return list(entry.articles)

	def cancel_pending_requests(self) -> None:
		"""Invalidate all in-flight rubric and article background requests."""
		with self._lock:
			self._rubric_request_seq += 1
			self._article_request_seq += 1

	def fetch_rubric_articles_sync(
		self,
		site: SiteConfig,
		rubric: RubricConfig,
		force_refresh: bool = False,
	) -> List[Article]:
		"""
		Fetch and parse the article list for a rubric synchronously (called from worker thread or unit tests).
		Dispatches to the appropriate site parser (`kompas_dom`, `detik_dom`, `cnn_dom`, `cnbc_dom`, or `tempo_dom`).
		"""
		if not site.supported:
			raise NewsHubNetworkError(_('{site} is not supported in this version.').format(site=site.name))
		if not rubric.supported:
			raise NewsHubNetworkError(_('This rubric cannot be accessed at this time.'))

		if not force_refresh:
			cached = self.get_cached_rubric_articles(site.id, rubric.id, allow_expired=False)
			if cached is not None:
				return cached

		parser_key = (rubric.parser_id or site.parser_id or "kompas_dom").lower()
		is_tempo_rubric = parser_key == "tempo_dom" or site.id == "tempo"
		raw_html = ""
		try:
			raw_html = fetch_html(rubric.url, site_label=site.name)
		except NewsHubNetworkError:
			if not is_tempo_rubric:
				raise
			raw_html = ""

		if parser_key == "detik_dom" or site.id == "detik":
			discovered = parse_detik_rss_or_headlines(
				raw_text=raw_html,
				source_id=site.id,
				rubric_id=rubric.id,
				rubric_name=rubric.name,
				base_url=rubric.url,
				max_articles=self.max_articles,
			)
		elif parser_key == "cnn_dom" or site.id == "cnn_indonesia":
			discovered = parse_cnn_rss_or_headlines(
				raw_text=raw_html,
				source_id=site.id,
				rubric_id=rubric.id,
				rubric_name=rubric.name,
				base_url=rubric.url,
				max_articles=self.max_articles,
			)
		elif parser_key == "cnbc_dom" or site.id == "cnbc_indonesia":
			discovered = parse_cnbc_rss_or_headlines(
				raw_text=raw_html,
				source_id=site.id,
				rubric_id=rubric.id,
				rubric_name=rubric.name,
				base_url=rubric.url,
				max_articles=self.max_articles,
			)
		elif parser_key == "tempo_dom" or site.id == "tempo":
			discovered = []
			if raw_html:
				discovered = parse_tempo_rss_or_headlines(
					raw_text=raw_html,
					source_id=site.id,
					rubric_id=rubric.id,
					rubric_name=rubric.name,
					base_url=rubric.url,
					max_articles=self.max_articles,
				)
			if not discovered:
				fallback_urls = TEMPO_RUBRIC_FALLBACK_FEEDS.get(
					rubric.id,
					[f"https://news.google.com/rss/search?q=site:tempo.co&hl=id&gl=ID&ceid=ID:id"],
				)
				for fb_url in fallback_urls:
					try:
						fb_xml = fetch_html(fb_url, site_label=site.name)
						discovered = parse_tempo_syndication_xml(
							xml_string=fb_xml,
							source_id=site.id,
							rubric_id=rubric.id,
							rubric_name=rubric.name,
							max_articles=self.max_articles,
						)
						if discovered:
							break
					except Exception as e:
						_log_debug(f"Tempo fallback feed {fb_url} failed: {e}")
		else:
			discovered = parse_rss_or_Headline_feed(
				raw_text=raw_html,
				source_id=site.id,
				rubric_id=rubric.id,
				rubric_name=rubric.name,
				base_url=rubric.url,
				max_articles=self.max_articles,
			)

		if not discovered:
			raise NewsHubNetworkError(_('No news articles were found in the {rubric_name} rubric. The page structure may have changed or the rubric is currently empty.').format(rubric=rubric.name, rubric_name=rubric.name))

		# Merge with previously loaded article cache entries so full content is preserved
		merged: List[Article] = []
		with self._lock:
			for art in discovered:
				existing = self._article_cache.get(art.canonical_url)
				if existing is not None and existing.content_status in (
					ArticleStatus.CONTENT_LOADED,
					ArticleStatus.CONTENT_PARTIAL,
				):
					existing.rubric_id = rubric.id
					if not existing.category_label:
						existing.category_label = art.category_label
					merged.append(existing)
				else:
					self._article_cache[art.canonical_url] = art
					merged.append(art)

			self._rubric_cache[(site.id, rubric.id)] = _RubricCacheEntry(merged, time.time())

		self.cleanup_expired_cache()
		return merged

	def fetch_rubric_articles_async(
		self,
		site: SiteConfig,
		rubric: RubricConfig,
		force_refresh: bool,
		is_background_auto: bool,
		on_success: Callable[[List[Article], bool], None],
		on_error: Callable[[str, bool], None],
	) -> int:
		"""
		Fetch rubric articles on a background daemon thread safely.
		- Prevents overlapping background auto-refresh workers.
		- Ignores stale responses if the user switched rubrics or sites while loading.
		"""
		with self._lock:
			if self._shutting_down:
				return -1
			if is_background_auto:
				if self._bg_refresh_in_progress:
					return -1
				self._bg_refresh_in_progress = True
				req_id = self._rubric_request_seq
			else:
				self._rubric_request_seq += 1
				req_id = self._rubric_request_seq

		def _worker():
			try:
				articles = self.fetch_rubric_articles_sync(site, rubric, force_refresh=force_refresh)
				with self._lock:
					if self._shutting_down or req_id != self._rubric_request_seq:
						return
				on_success(articles, is_background_auto)
			except NewsHubNetworkError as e:
				with self._lock:
					if self._shutting_down or req_id != self._rubric_request_seq:
						return
				on_error(e.user_message, is_background_auto)
			except Exception:
				with self._lock:
					if self._shutting_down or req_id != self._rubric_request_seq:
						return
				on_error(
					_('Failed to load news list for {rubric} from {site}. Please check your internet connection and try again.').format(rubric=rubric.name, site=site.name),
					is_background_auto,
				)
			finally:
				if is_background_auto:
					with self._lock:
						self._bg_refresh_in_progress = False

		t = threading.Thread(
			target=_worker,
			name=f"NewsHub-RubricWorker-{rubric.id}-{req_id}",
			daemon=True,
		)
		t.start()
		return req_id

	def fetch_article_content_sync(
		self,
		site: SiteConfig,
		article: Article,
		force_reload: bool = False,
	) -> Article:
		"""
		Fetch and parse the full content of an article synchronously.
		If a verified full-page link (`?page=all` or `?single=1`) is detected in the DOM,
		fetches the complete article page automatically.
		"""
		canonical = article.canonical_url or normalize_canonical_url(article.url)
		if not force_reload:
			with self._lock:
				cached = self._article_cache.get(canonical)
				if cached is not None and cached.content_status == ArticleStatus.CONTENT_LOADED and cached.content:
					return cached

				# If the article URL is a Google News RSS syndication redirect and already has summary blocks,
		# try fetching or fall back gracefully to its syndication summary
		if "news.google.com" in article.url.lower():
			if article.summary or article.content:
				from .models import ContentBlock
				if not article.content and article.summary:
					article.content = [ContentBlock(block_type="p", text=article.summary).to_dict()]
				article.content_status = ArticleStatus.CONTENT_PARTIAL
				article.reading_time_minutes = max(1, calculate_reading_time_minutes(article.content, article.summary))
				with self._lock:
					self._article_cache[canonical] = article
				return article
		try:
			raw_html = fetch_html(article.url, site_label=site.name)
		except NewsHubNetworkError as net_err:
			# If Cloudflare challenges a Tempo.co article page with HTTP 403, try syndication snippet fallback
			if getattr(net_err, "status_code", 0) == 403 and (site.id == "tempo" or "tempo.co" in article.url.lower()):
				if not article.summary and article.title:
					import urllib.parse as _up
					q = _up.quote(f"{article.title} site:tempo.co")
					fb_q_url = f"https://news.google.com/rss/search?q={q}&hl=id&gl=ID&ceid=ID:id"
					try:
						fb_xml = fetch_html(fb_q_url, site_label=site.name)
						fb_items = parse_tempo_syndication_xml(
							xml_string=fb_xml,
							source_id=site.id,
							rubric_id=article.rubric_id,
							rubric_name=article.category_label or "Tempo.co",
							max_articles=3,
						)
						if fb_items and fb_items[0].summary:
							article.summary = fb_items[0].summary
							if not article.published_at and fb_items[0].published_at:
								article.published_at = fb_items[0].published_at
					except Exception:
						pass
				if article.summary or article.content:
					from .models import ContentBlock
					if not article.content and article.summary:
						article.content = [ContentBlock(block_type="p", text=article.summary).to_dict()]
					article.content_status = ArticleStatus.CONTENT_PARTIAL
					article.reading_time_minutes = max(1, calculate_reading_time_minutes(article.content, article.summary))
					with self._lock:
						self._article_cache[canonical] = article
					return article
			raise
		is_detik = site.id == "detik" or site.parser_id == "detik_dom" or "detik.com" in article.url.lower()
		is_cnn = site.id == "cnn_indonesia" or site.parser_id == "cnn_dom" or "cnnindonesia.com" in article.url.lower()
		is_cnbc = site.id == "cnbc_indonesia" or site.parser_id == "cnbc_dom" or "cnbcindonesia.com" in article.url.lower()
		is_tempo = site.id == "tempo" or site.parser_id == "tempo_dom" or "tempo.co" in article.url.lower()

		# Check if the article is paginated and exposes a verified full-page link in the DOM
		if is_detik:
			all_pages_url = detect_detik_all_pages_url(raw_html, article.url)
		elif is_cnn or is_cnbc or is_tempo:
			all_pages_url = detect_portal_all_pages_url(raw_html, article.url)
		else:
			all_pages_url = detect_kompas_all_pages_url(raw_html, article.url)

		if all_pages_url:
			try:
				full_html = fetch_html(all_pages_url, site_label=site.name)
				if full_html and len(full_html) > 500:
					raw_html = full_html
			except Exception as e:
				_log_debug(f"Failed to fetch full-page URL {all_pages_url}, falling back to page 1: {e}")

		if is_detik:
			parsed = parse_detik_article_html(
				raw_html,
				url=article.url,
				default_category=article.category_label,
			)
		elif is_cnn:
			parsed = parse_portal_article_html(
				raw_html,
				url=article.url,
				default_category=article.category_label,
				portal_label="CNN Indonesia",
			)
		elif is_cnbc:
			parsed = parse_portal_article_html(
				raw_html,
				url=article.url,
				default_category=article.category_label,
				portal_label="CNBC Indonesia",
			)
		elif is_tempo:
			parsed = parse_portal_article_html(
				raw_html,
				url=article.url,
				default_category=article.category_label,
				portal_label="Tempo.co",
			)
		else:
			parsed = parse_kompas_article_html(
				raw_html,
				url=article.url,
				default_category=article.category_label,
			)

		_enrich_parsed_video_streams(parsed, site.name)
		status = parsed.get("content_status", ArticleStatus.CONTENT_LOADED)
		if status == ArticleStatus.CONTENT_FAILED and not article.summary:
			raise NewsHubNetworkError(_('Article content could not be found on this page. The page structure may differ or it may be multimedia-only content.'))

		reading_time = calculate_reading_time_minutes(parsed.get("content") or [], parsed.get("summary") or article.summary)
		with self._lock:
			article.update_from_FullParse(parsed, status=status, reading_time=reading_time)
			self._article_cache[canonical] = article

		return article

	def fetch_article_content_async(
		self,
		site: SiteConfig,
		article: Article,
		force_reload: bool,
		on_success: Callable[[Article], None],
		on_error: Callable[[Article, str], None],
	) -> int:
		"""
		Fetch full article content on a background daemon thread with race-condition protection.
		If the user selects another article while this request is in flight, the stale result is discarded.
		"""
		with self._lock:
			if self._shutting_down:
				return -1
			self._article_request_seq += 1
			req_id = self._article_request_seq
			target_article_id = article.id

		def _worker():
			try:
				updated = self.fetch_article_content_sync(site, article, force_reload=force_reload)
				with self._lock:
					if self._shutting_down or req_id != self._article_request_seq or updated.id != target_article_id:
						return
				on_success(updated)
			except NewsHubNetworkError as e:
				with self._lock:
					article.content_status = (
						ArticleStatus.CONTENT_PARTIAL if article.summary else ArticleStatus.CONTENT_FAILED
					)
					article.error_message = e.user_message
					if self._shutting_down or req_id != self._article_request_seq or article.id != target_article_id:
						return
				on_error(article, e.user_message)
			except Exception:
				msg = _('Failed to load article content from {site}. Please check your internet connection and try again.').format(site=site.name)
				with self._lock:
					article.content_status = (
						ArticleStatus.CONTENT_PARTIAL if article.summary else ArticleStatus.CONTENT_FAILED
					)
					article.error_message = msg
					if self._shutting_down or req_id != self._article_request_seq or article.id != target_article_id:
						return
				on_error(article, msg)

		t = threading.Thread(
			target=_worker,
			name=f"NewsHub-ArticleWorker-{article.id}-{req_id}",
			daemon=True,
		)
		t.start()
		return req_id


	def _search_single_site_sync(self, site: SiteConfig, query: str, per_site_limit: int = 12) -> List[Article]:
		"""
		Search a single news portal for articles matching `query` using:
		1. Cached session articles matching all query tokens.
		2. Native portal search and tag pages (`detik.com/search/searchall`, `cnbcindonesia.com/search`,
		   `cnnindonesia.com/search`, `kompas.com/tag/<slug>`, `tempo.co/tag/<slug>`).
		3. Google News RSS site-scoped search (`site:<domain>`) as a resilient fallback.
		"""
		import re as _re
		import urllib.parse as _up

		cleaned_q = " ".join((query or "").split()).strip()
		if not cleaned_q or not site.supported:
			return []

		q_tokens = [t.lower() for t in _re.split(r"\s+", cleaned_q) if len(t) >= 2]
		if not q_tokens:
			q_tokens = [cleaned_q.lower()]

		encoded_q = _up.quote_plus(cleaned_q)
		tag_slug = _re.sub(r"[^a-z0-9]+", "-", cleaned_q.lower()).strip("-")

		results: List[Article] = []
		seen_canonicals = set()

		def _add_candidate(art: Article) -> None:
			canon = art.canonical_url or normalize_canonical_url(art.url)
			if not canon or canon in seen_canonicals:
				return
			seen_canonicals.add(canon)
			art.source_id = site.id
			if not art.category_label or site.name.lower() not in art.category_label.lower():
				art.category_label = f"{site.name} ({art.category_label})" if art.category_label else site.name
			results.append(art)

		# 1. Check in-memory rubric/article cache for immediate keyword matches
		with self._lock:
			for (s_id, _r_id), entry in list(self._rubric_cache.items()):
				if s_id != site.id:
					continue
				for art in entry.articles:
					haystack = f"{art.title} {art.summary} {art.category_label}".lower()
					if all(tok in haystack for tok in q_tokens):
						_add_candidate(art)

		# 2. Query native portal search & tag endpoints
		native_urls: List[str] = []
		domain = "kompas.com"
		if site.id == "kompas":
			domain = "kompas.com"
			if tag_slug:
				native_urls.append(f"https://www.kompas.com/tag/{tag_slug}")
			native_urls.append(f"https://search.kompas.com/search?q={encoded_q}")
		elif site.id == "detik":
			domain = "detik.com"
			native_urls.append(f"https://www.detik.com/search/searchall?query={encoded_q}")
			if tag_slug:
				native_urls.append(f"https://www.detik.com/tag/{tag_slug}")
		elif site.id == "cnn_indonesia":
			domain = "cnnindonesia.com"
			native_urls.append(f"https://www.cnnindonesia.com/search/?query={encoded_q}")
			if tag_slug:
				native_urls.append(f"https://www.cnnindonesia.com/tag/{tag_slug}")
		elif site.id == "cnbc_indonesia":
			domain = "cnbcindonesia.com"
			native_urls.append(f"https://www.cnbcindonesia.com/search?query={encoded_q}")
			if tag_slug:
				native_urls.append(f"https://www.cnbcindonesia.com/tag/{tag_slug}")
		elif site.id == "tempo":
			domain = "tempo.co"
			if tag_slug:
				native_urls.append(f"https://www.tempo.co/tag/{tag_slug}")
			native_urls.append(f"https://www.tempo.co/search?q={encoded_q}")

		for nat_url in native_urls:
			if len(results) >= per_site_limit:
				break
			try:
				raw_html = fetch_html(nat_url, timeout=8, site_label=site.name)
				if not raw_html:
					continue
				if site.id == "detik":
					parsed_list = parse_detik_rss_or_headlines(
						raw_text=raw_html,
						source_id=site.id,
						rubric_id="search",
						rubric_name=site.name,
						base_url=site.base_url,
						max_articles=per_site_limit,
					)
				elif site.id == "cnn_indonesia":
					parsed_list = parse_cnn_rss_or_headlines(
						raw_text=raw_html,
						source_id=site.id,
						rubric_id="search",
						rubric_name=site.name,
						base_url=site.base_url,
						max_articles=per_site_limit,
					)
				elif site.id == "cnbc_indonesia":
					parsed_list = parse_cnbc_rss_or_headlines(
						raw_text=raw_html,
						source_id=site.id,
						rubric_id="search",
						rubric_name=site.name,
						base_url=site.base_url,
						max_articles=per_site_limit,
					)
				elif site.id == "tempo":
					parsed_list = parse_tempo_rss_or_headlines(
						raw_text=raw_html,
						source_id=site.id,
						rubric_id="search",
						rubric_name=site.name,
						base_url=site.base_url,
						max_articles=per_site_limit,
					)
				else:
					parsed_list = parse_rss_or_Headline_feed(
						raw_text=raw_html,
						source_id=site.id,
						rubric_id="search",
						rubric_name=site.name,
						base_url=site.base_url,
						max_articles=per_site_limit,
					)
				for item in parsed_list:
					_add_candidate(item)
					if len(results) >= per_site_limit:
						break
			except Exception as e:
				_log_debug(f"Native search endpoint {nat_url} notice: {e}")

		# 3. Fallback / supplement via Google News RSS site-scoped search
		if len(results) < 3:
			rss_q = _up.quote(f"{cleaned_q} site:{domain}")
			gnews_url = f"https://news.google.com/rss/search?q={rss_q}&hl=id&gl=ID&ceid=ID:id"
			try:
				rss_xml = fetch_html(gnews_url, timeout=8, site_label=site.name)
				rss_items = parse_tempo_syndication_xml(
					xml_string=rss_xml,
					source_id=site.id,
					rubric_id="search",
					rubric_name=site.name,
					max_articles=per_site_limit,
				)
				for item in rss_items:
					# Clean trailing " - Kompas.com", " - detikNews", etc. from RSS title
					item.title = _re.sub(
						r"\s*[\-–]\s*(?:Kompas\.com|detik[a-zA-Z]*|CNN Indonesia|CNBC Indonesia|Tempo\.co)\s*$",
						"",
						item.title,
						flags=_re.IGNORECASE,
					).strip()
					_add_candidate(item)
					if len(results) >= per_site_limit:
						break
			except Exception as e:
				_log_debug(f"RSS search fallback {gnews_url} notice: {e}")

		return results[:per_site_limit]

	def search_articles_across_sites_sync(
		self,
		query: str,
		sites: List[SiteConfig],
	) -> List[Article]:
		"""
		Search for articles matching `query` across all available news sites concurrently.
		Interleaves results from all portals and stores them in `_article_cache`.
		"""
		from concurrent.futures import ThreadPoolExecutor

		cleaned_q = " ".join((query or "").split()).strip()
		if not cleaned_q:
			raise NewsHubNetworkError(_("Please enter a search keyword first."))

		supported_sites = [s for s in sites if s.supported]
		if not supported_sites:
			raise NewsHubNetworkError(_("No supported news portals are available for search."))

		per_site_limit = max(6, int(self.max_articles // max(1, len(supported_sites))))
		site_results_map: Dict[str, List[Article]] = {}

		with ThreadPoolExecutor(max_workers=len(supported_sites)) as executor:
			future_map = {
				executor.submit(self._search_single_site_sync, s, cleaned_q, per_site_limit): s
				for s in supported_sites
			}
			for fut, s in future_map.items():
				try:
					site_results_map[s.id] = fut.result(timeout=18)
				except Exception as e:
					_log_debug(f"Search worker for {s.name} failed: {e}")
					site_results_map[s.id] = []

		# Interleave results round-robin across portals so all portals are represented near the top
		combined: List[Article] = []
		seen_canon = set()
		max_len = max((len(v) for v in site_results_map.values()), default=0)

		for idx in range(max_len):
			for s in supported_sites:
				s_list = site_results_map.get(s.id) or []
				if idx < len(s_list):
					art = s_list[idx]
					canon = art.canonical_url or normalize_canonical_url(art.url)
					if canon and canon not in seen_canon:
						seen_canon.add(canon)
						combined.append(art)
						if len(combined) >= self.max_articles:
							break
			if len(combined) >= self.max_articles:
				break

		if not combined:
			raise NewsHubNetworkError(
				_('No news articles found for keyword "{query}" across any news portal.').format(query=cleaned_q)
			)

		with self._lock:
			for art in combined:
				existing = self._article_cache.get(art.canonical_url)
				if existing is not None and existing.content_status in (
					ArticleStatus.CONTENT_LOADED,
					ArticleStatus.CONTENT_PARTIAL,
				):
					art.content = list(existing.content)
					art.photos = list(existing.photos)
					art.videos = list(existing.videos)
					art.content_status = existing.content_status
					art.reading_time_minutes = existing.reading_time_minutes
				else:
					self._article_cache[art.canonical_url] = art

		return combined

	def search_articles_across_sites_async(
		self,
		query: str,
		sites: List[SiteConfig],
		on_success: Callable[[str, List[Article]], None],
		on_error: Callable[[str, str], None],
	) -> int:
		"""Run cross-portal keyword search on a background thread with race-condition protection."""
		with self._lock:
			if self._shutting_down:
				return -1
			self._rubric_request_seq += 1
			req_id = self._rubric_request_seq

		def _worker():
			try:
				found = self.search_articles_across_sites_sync(query=query, sites=sites)
				with self._lock:
					if self._shutting_down or req_id != self._rubric_request_seq:
						return
				on_success(query, found)
			except NewsHubNetworkError as e:
				with self._lock:
					if self._shutting_down or req_id != self._rubric_request_seq:
						return
				on_error(query, e.user_message)
			except Exception:
				with self._lock:
					if self._shutting_down or req_id != self._rubric_request_seq:
						return
				on_error(
					query,
					_('Failed to search news for "{query}". Please check your internet connection and try again.').format(query=query),
				)

		t = threading.Thread(
			target=_worker,
			name=f"NewsHub-SearchWorker-{req_id}",
			daemon=True,
		)
		t.start()
		return req_id
