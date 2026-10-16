# -*- coding: utf-8 -*-
"""
Article state, TTL cache, race-condition guard, and background worker manager for NewsHub for NVDA.
"""

import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from .formatter import calculate_reading_time_minutes
from .i18n import tr
from .kompas_parser import (
	detect_kompas_all_pages_url,
	parse_kompas_article_html,
	parse_rss_or_Headline_feed,
)
from .models import Article, ArticleStatus, RubricConfig, SiteConfig
from .network import NewsHubNetworkError, fetch_html, normalize_canonical_url


def _log_debug(msg: str) -> None:
	try:
		from logHandler import log
		log.debug(f"NewsHub ArticleManager: {msg}")
	except Exception:
		pass


class _RubricCacheEntry:
	"""Cache entry storing the fetched article list and timestamp for a single rubric."""
	__slots__ = ("articles", "fetched_at")

	def __init__(self, articles: List[Article], fetched_at: float):
		self.articles = list(articles)
		self.fetched_at = fetched_at


class ArticleManager:
	"""
	Manage rubric headline fetching, full article content extraction, session caching with TTL,
	and request sequence tokens to prevent stale background responses from overwriting newer selections.
	"""
	def __init__(self, cache_ttl_sec: int = 180, max_articles: int = 40):
		self._lock = threading.RLock()
		self.cache_ttl_sec = max(30, int(cache_ttl_sec or 180))
		self.max_articles = max(10, int(max_articles or 40))

		# Headline list cache indexed by (site_id, rubric_id)
		self._rubric_cache: Dict[Tuple[str, str], _RubricCacheEntry] = {}
		# Individual article cache indexed by canonical_url so loaded content is reused across sessions
		self._article_cache: Dict[str, Article] = {}

		# Monotonically increasing sequence numbers to guard against race conditions
		self._rubric_request_seq: int = 0
		self._article_request_seq: int = 0
		self._bg_refresh_in_progress: bool = False
		self._shutting_down: bool = False

	def configure(self, cache_ttl_sec: int, max_articles: int) -> None:
		with self._lock:
			self.cache_ttl_sec = max(30, int(cache_ttl_sec or 180))
			self.max_articles = max(10, int(max_articles or 40))

	def shutdown(self) -> None:
		"""Mark the manager as shutting down so any in-flight background callbacks are ignored."""
		with self._lock:
			self._shutting_down = True
			self._rubric_request_seq += 1
			self._article_request_seq += 1

	def cleanup_expired_cache(self) -> None:
		"""Evict expired cache entries to keep memory usage bounded."""
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
		"""Return cached rubric articles if present and within TTL."""
		key = (site_id, rubric_id)
		with self._lock:
			entry = self._rubric_cache.get(key)
			if entry is None:
				return None
			if not allow_expired and (time.time() - entry.fetched_at) > self.cache_ttl_sec:
				return None
			return list(entry.articles)

	def cancel_pending_requests(self) -> None:
		"""Invalidate all in-flight rubric and article requests."""
		with self._lock:
			self._rubric_request_seq += 1
			self._article_request_seq += 1

	def fetch_rubric_articles_sync(
		self,
		site: SiteConfig,
		rubric: RubricConfig,
		force_refresh: bool = False,
	) -> List[Article]:
		"""Synchronously fetch the article list for a rubric (called from worker threads or tests)."""
		if not site.supported:
			raise NewsHubNetworkError(tr("site_not_supported_msg", site_name=site.name))
		if not rubric.supported:
			raise NewsHubNetworkError(tr("rubric_not_accessible"))

		if not force_refresh:
			cached = self.get_cached_rubric_articles(site.id, rubric.id, allow_expired=False)
			if cached is not None:
				return cached

		raw_html = fetch_html(rubric.url, site_label=site.name)
		discovered = parse_rss_or_Headline_feed(
			raw_text=raw_html,
			source_id=site.id,
			rubric_id=rubric.id,
			rubric_name=rubric.name,
			base_url=rubric.url,
			max_articles=self.max_articles,
		)

		if not discovered:
			raise NewsHubNetworkError(tr("err_rubric_empty", rubric_name=rubric.name))

		# Merge with previously cached full articles so already-loaded content is preserved
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
		Fetch rubric articles on a background daemon thread:
		- When `is_background_auto=True`, prevents overlapping background sync jobs.
		- Discards stale responses if the user has already switched rubrics or portals.
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
					tr("err_rubric_generic", rubric_name=rubric.name, site_name=site.name),
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
		Synchronously fetch and parse the full content of an article.
		If the article DOM contains a verified full-page link (`?page=all`), fetches the full page
		so multi-page articles are not truncated.
		"""
		canonical = article.canonical_url or normalize_canonical_url(article.url)
		if not force_reload:
			with self._lock:
				cached = self._article_cache.get(canonical)
				if cached is not None and cached.content_status == ArticleStatus.CONTENT_LOADED and cached.content:
					return cached

		raw_html = fetch_html(article.url, site_label=site.name)

		# Check if the article is multi-page and provides a verified ?page=all link in the DOM
		all_pages_url = detect_kompas_all_pages_url(raw_html, article.url)
		if all_pages_url:
			try:
				full_html = fetch_html(all_pages_url, site_label=site.name)
				if full_html and len(full_html) > 500:
					raw_html = full_html
			except Exception as e:
				_log_debug(f"Failed to fetch full-page URL {all_pages_url}, falling back to page 1: {e}")

		parsed = parse_kompas_article_html(
			raw_html,
			url=article.url,
			default_category=article.category_label,
		)
		status = parsed.get("content_status", ArticleStatus.CONTENT_LOADED)
		if status == ArticleStatus.CONTENT_FAILED and not article.summary:
			raise NewsHubNetworkError(tr("err_article_empty"))

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
		Fetch full article content on a background thread with race-condition protection.
		If the user selects another article while this request is in flight, the earlier response
		will not overwrite the newly selected article's view.
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
				msg = tr("err_article_generic", site_name=site.name)
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
