# -*- coding: utf-8 -*-
"""
DOM-tree and JSON-LD parsers for CNN Indonesia, CNBC Indonesia, and Tempo.co.

Supports:
- CNN Indonesia (cnnindonesia.com): all 8 rubrics, Transmedia timestamp-ID URLs,
  multi-page (?page=all) detection, and full article extraction.
- CNBC Indonesia (cnbcindonesia.com): all 7 rubrics, Transmedia timestamp-ID URLs,
  multi-page (?page=all) detection, and full article extraction.
- Tempo.co (tempo.co): all 11 rubrics, modern slug-ID URLs (tempo.co/<channel>/<slug>-<id>),
  classic /read/<id>/<slug> URLs, interactive /play and /newsletter items,
  multi-page (?page=all) detection, and full article extraction with JSON-LD fallback.
"""

import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Set, Tuple

from .kompas_parser import _DOMBuilder, _DOMNode, _iter_nodes, EXCLUDED_TAGS, _extract_inline_media_blocks_from_node, extract_article_media_from_dom
from .models import Article, ArticleStatus, ContentBlock
from .network import normalize_canonical_url


# URL regex patterns for CNN Indonesia, CNBC Indonesia, and Tempo.co
CNN_ARTICLE_URL_RE = re.compile(
	r"^https?://(?:[a-z0-9\-]+\.)?cnnindonesia\.com/[a-z0-9\-_]+/\d{14}-\d+-\d+/[a-z0-9\-_]+",
	re.IGNORECASE,
)

CNBC_ARTICLE_URL_RE = re.compile(
	r"^https?://(?:[a-z0-9\-]+\.)?cnbcindonesia\.com/[a-z0-9\-_]+/\d{14}-\d+-\d+/[a-z0-9\-_]+",
	re.IGNORECASE,
)

TEMPO_MODERN_URL_RE = re.compile(
	r"^https?://(?:[a-z0-9\-]+\.)?tempo\.co/[a-z0-9\-_]+/[a-z0-9\-_]+-\d+/?$",
	re.IGNORECASE,
)

TEMPO_CLASSIC_READ_URL_RE = re.compile(
	r"^https?://(?:[a-z0-9\-]+\.)?tempo\.co/read/\d+/[a-z0-9\-_]+",
	re.IGNORECASE,
)

TEMPO_SPECIAL_PATH_URL_RE = re.compile(
	r"^https?://(?:[a-z0-9\-]+\.)?tempo\.co/(?:play|newsletter|cekfakta|info-tempo|investigasi|wawancara|tokoh)/[a-z0-9\-_/]{4,}",
	re.IGNORECASE,
)

PORTAL_EXCLUDED_ATTR_SUBSTRINGS: Tuple[str, ...] = (
	"ads-", "iklan", "banner", "billboard", " sky-",
	"linksisip", "baca-juga", "bacajuga", "lihat-juga", "pilihan-editor",
	"paradetail", "sisip", "related", "terkait", "rekomendasi",
	"terpopuler", "most-popular", "trending",
	"share", "social", "komentar", "comment", "tags", "tag-", "topik",
	"navbar", "menu", "header", "footer", "sidebar", "widget", "breadcrumb",
	"watchlist", "market-data",
)

PORTAL_NOISE_PHRASES: Tuple[str, ...] = (
	"baca juga:",
	"baca juga :",
	"baca:",
	"lihat juga:",
	"pilihan editor:",
	"simak video",
	"lihat foto",
	"selanjutnya",
	"halaman selanjutnya",
	"next article",
	"url telah tercopy",
	"tulis komentar anda",
	"scroll to continue with content",
	"scroll ke bawah untuk lanjut membaca",
	"close ad",
	"download aplikasi cnbc indonesia",
	"download apps",
	"trans media, cnn name, logo",
	"cnbc indonesia, a transmedia company",
	"pedoman media siber",
	"tentang kami | redaksi",
	"ikuti berita tempo",
	"[gambas:",
)

PORTAL_NAV_EXACT_ITEMS = frozenset([
	"home", "beranda", "indeks", "index", "terpopuler", "most popular",
	"berita terbaru", "latest news", "top articles", "lihat semua", "show more",
	"login", "register", "masuk", "daftar", "keluar", "logout",
	"nasional", "internasional", "ekonomi", "olahraga", "teknologi",
	"otomotif", "hiburan", "gaya hidup", "fokus", "kolom", "infografis",
	"foto", "video", "tv", "market", "my money", "news", "tech", "lifestyle",
	"sharia", "entrepreneur", "cuap cuap cuan", "research", "opinion",
	"permainan baru", "politik", "hukum", "lingkungan", "wawancara",
	"investigasi", "cek fakta", "tokoh", "newsletter", "info tempo",
])


def is_valid_cnn_article_url(url: str) -> bool:
	"""Verify whether a URL points to a valid CNN Indonesia news article."""
	if not url:
		return False
	cleaned = url.strip().split("?")[0].split("#")[0]
	return bool(CNN_ARTICLE_URL_RE.match(cleaned))


def is_valid_cnbc_article_url(url: str) -> bool:
	"""Verify whether a URL points to a valid CNBC Indonesia news article."""
	if not url:
		return False
	cleaned = url.strip().split("?")[0].split("#")[0]
	return bool(CNBC_ARTICLE_URL_RE.match(cleaned))


def is_valid_tempo_article_url(url: str) -> bool:
	"""Verify whether a URL points to a valid Tempo.co article or special rubric edition."""
	if not url:
		return False
	cleaned = url.strip().split("?")[0].split("#")[0]
	try:
		parsed = urllib.parse.urlparse(cleaned)
		path_low = (parsed.path or "").lower().rstrip("/")
		# Reject tag, index, author, search, or bare channel root paths
		if any(
			seg in path_low
			for seg in ("/tag/", "/indeks", "/index", "/search", "/penulis/", "/author/", "/login", "/register")
		):
			return False
	except Exception:
		return False

	if TEMPO_MODERN_URL_RE.match(cleaned) or TEMPO_CLASSIC_READ_URL_RE.match(cleaned):
		return True
	if TEMPO_SPECIAL_PATH_URL_RE.match(cleaned):
		return True
	return False


def _is_portal_noise_text(text: str) -> bool:
	"""Check whether text is boilerplate, ad label, or navigation menu clutter."""
	if not text:
		return True
	low = " ".join(text.lower().split()).strip()
	if low in PORTAL_NAV_EXACT_ITEMS:
		return True
	for phrase in PORTAL_NOISE_PHRASES:
		if phrase in low:
			return True
	if low.startswith("[gambas:") and low.endswith("]"):
		return True
	return False


def _is_portal_inline_related_node(node: _DOMNode) -> bool:
	"""Detect inline related-article widgets ('linksisip')."""
	cls_id = (" ".join(node.classes) + " " + node.id).lower()
	if any(k in cls_id for k in ("linksisip", "baca-juga", "bacajuga", "lihat-juga", "pilihan-editor", "paradetail")):
		return True
	if node.tag in ("table", "div", "p", "span", "strong", "blockquote"):
		txt = node.get_text().lower()
		if (
			txt.startswith("baca juga:")
			or txt.startswith("baca juga :")
			or txt.startswith("baca:")
			or txt.startswith("lihat juga:")
			or txt.startswith("pilihan editor:")
			or txt.startswith("[gambas:")
		):
			return True
	return False


def _is_portal_excluded_node(node: _DOMNode) -> bool:
	"""Check whether a DOM node is an excluded widget, ad, tag list, or sidebar."""
	if node.tag in EXCLUDED_TAGS:
		return True
	cls_lower = " ".join(node.classes).lower()
	id_lower = node.id.lower()
	combined = f"{cls_lower} {id_lower}"
	for sub in PORTAL_EXCLUDED_ATTR_SUBSTRINGS:
		if sub in combined:
			return True
	return False


def _find_portal_enclosing_card(a_node: _DOMNode) -> Optional[_DOMNode]:
	"""Locate the nearest enclosing article card container (article, li, or card div)."""
	curr = a_node.parent
	depth = 0
	while curr is not None and depth < 6:
		if curr.tag in ("article", "li") or (
			curr.tag == "div"
			and any(
				k in " ".join(curr.classes).lower()
				for k in ("list", "media", "card", "box", "item", "nhl", "content")
			)
		):
			return curr
		curr = curr.parent
		depth += 1
	return None


def _extract_portal_card_metadata(card_node: Optional[_DOMNode], default_category: str) -> Tuple[str, str, str, str]:
	"""Extract (category, published_at, summary, author) from a rubric listing card."""
	category = default_category
	published_at = ""
	summary = ""
	author = ""
	if card_node is None:
		return category, published_at, summary, author

	for node in _iter_nodes(card_node):
		cls_joined = " ".join(node.classes).lower()
		if not category or category == default_category:
			if any(k in cls_joined for k in ("sub-judul", "subtitle", "kanal", "category", "label")):
				txt = node.get_text()
				if txt and len(txt) < 40 and not _is_portal_noise_text(txt):
					category = txt
		if (
			node.tag == "time"
			or any(k in cls_joined for k in ("date", "time", "ago"))
			or (node.tag == "span" and node.attrs.get("title"))
		):
			title_attr = (node.attrs.get("title") or "").strip()
			if title_attr and len(title_attr) < 65:
				published_at = title_attr
			elif not published_at:
				txt = node.get_text()
				if txt and len(txt) < 65 and not _is_portal_noise_text(txt):
					published_at = txt
		if not summary:
			if any(k in cls_joined for k in ("desc", "lead", "summary", " synopsis", " ringkasan")):
				txt = node.get_text()
				if txt and len(txt) > 20 and not _is_portal_noise_text(txt):
					summary = txt
	return category, published_at, summary, author


def _clean_headline_title(raw_title: str, rubric_name: str = "") -> str:
	"""Clean category/date prefixes or suffixes that sometimes attach to anchor text on CNN/CNBC cards."""
	if not raw_title:
		return ""
	cleaned = " ".join(raw_title.split()).strip()
	# Strip trailing relative time like "Market 22 menit yang lalu" or leading "VIDEO" / "FOTO" badges if duplicated
	cleaned = re.sub(
		r"\s+(?:Market|My Money|News|Tech|Lifestyle|Sharia|Entrepreneur|Nasional|Internasional|Ekonomi|Olahraga|Teknologi|Otomotif|Hiburan|Gaya Hidup)\s+\d+\s+(?:menit|jam|hari)\s+yang\s+lalu.*$",
		"",
		cleaned,
		flags=re.IGNORECASE,
	).strip()
	return cleaned


def _parse_generic_rss_xml(
	xml_string: str,
	source_id: str,
	rubric_id: str,
	rubric_name: str,
	url_validator,
	max_articles: int = 40,
) -> List[Article]:
	"""Extract articles from an RSS 2.0 XML feed when provided."""
	articles: List[Article] = []
	seen_canonical: Set[str] = set()
	try:
		root = ET.fromstring(xml_string)
		for item in root.iter("item"):
			title = (item.findtext("title") or "").strip()
			link = (item.findtext("link") or "").strip()
			pub_date = (item.findtext("pubDate") or "").strip()
			desc_raw = (item.findtext("description") or "").strip()
			desc_clean = re.sub(r"<[^>]+>", " ", html.unescape(desc_raw))
			desc_clean = " ".join(desc_clean.split()).strip()

			if not title or not link or not url_validator(link):
				continue
			canonical = normalize_canonical_url(link)
			if not canonical or canonical in seen_canonical:
				continue
			seen_canonical.add(canonical)

			articles.append(
				Article(
					source_id=source_id,
					rubric_id=rubric_id,
					title=title,
					url=link,
					canonical_url=canonical,
					published_at=pub_date,
					summary=desc_clean,
					category_label=rubric_name,
					content_status=ArticleStatus.HEADLINE_LOADED,
				)
			)
			if len(articles) >= max_articles:
				break
	except Exception:
		return []
	return articles


def _parse_portal_rubric_headlines(
	html_string: str,
	source_id: str,
	rubric_id: str,
	rubric_name: str,
	base_url: str,
	url_validator,
	max_articles: int = 40,
) -> List[Article]:
	"""
	Extract headlines from a CNN Indonesia, CNBC Indonesia, or Tempo.co rubric HTML page.
	Also parses JSON-LD ItemList if present in SSR pages.
	"""
	builder = _DOMBuilder()
	builder.feed(html_string or "")
	root = builder.root

	candidates_by_canonical: Dict[str, Dict[str, Any]] = {}
	ordered_canonicals: List[str] = []

	for node in _iter_nodes(root):
		if node.tag in ("nav", "footer", "header"):
			continue
		if node.tag == "a":
			href_raw = (node.attrs.get("href") or "").strip()
			if not href_raw or href_raw.startswith("#") or href_raw.lower().startswith("javascript:"):
				continue
			full_url = urllib.parse.urljoin(base_url, href_raw)
			if not url_validator(full_url):
				continue

			parent_ptr = node.parent
			in_chrome = False
			while parent_ptr is not None:
				if parent_ptr.tag in ("nav", "footer"):
					in_chrome = True
					break
				parent_ptr = parent_ptr.parent
			if in_chrome:
				continue

			# Prefer heading text inside the anchor (h1/h2/h3/h4) if present to avoid image caption clutter
			heading_text = ""
			for sub in _iter_nodes(node):
				if sub.tag in ("h1", "h2", "h3", "h4") or "title" in " ".join(sub.classes).lower():
					ht = sub.get_text()
					if ht and len(ht) >= 12:
						heading_text = ht
						break

			link_title = heading_text or node.get_text() or (node.attrs.get("title") or "").strip()
			link_title = _clean_headline_title(link_title, rubric_name)
			if not link_title or len(link_title) < 12 or _is_portal_noise_text(link_title):
				continue

			canonical = normalize_canonical_url(full_url)
			if not canonical:
				continue

			card = _find_portal_enclosing_card(node)
			cat, pub_at, summary, author = _extract_portal_card_metadata(card, rubric_name)

			if canonical not in candidates_by_canonical:
				candidates_by_canonical[canonical] = {
					"title": link_title,
					"url": full_url.split("#")[0],
					"canonical_url": canonical,
					"category": cat or rubric_name,
					"published_at": pub_at,
					"summary": summary,
					"author": author,
				}
				ordered_canonicals.append(canonical)
			else:
				existing = candidates_by_canonical[canonical]
				if heading_text and len(heading_text) >= 12:
					existing["title"] = heading_text
				elif len(link_title) > len(existing["title"]) and len(link_title) < 180:
					existing["title"] = link_title
				if pub_at and not existing["published_at"]:
					existing["published_at"] = pub_at
				if summary and not existing["summary"]:
					existing["summary"] = summary
				if author and not existing["author"]:
					existing["author"] = author

	articles: List[Article] = []
	for canonical in ordered_canonicals:
		item = candidates_by_canonical[canonical]
		if len(item["title"]) < 12:
			continue
		articles.append(
			Article(
				source_id=source_id,
				rubric_id=rubric_id,
				title=item["title"],
				url=item["url"],
				canonical_url=item["canonical_url"],
				published_at=item["published_at"],
				author=item["author"],
				summary=item["summary"],
				category_label=item["category"],
				content_status=ArticleStatus.HEADLINE_LOADED,
			)
		)
		if len(articles) >= max_articles:
			break

	return articles


def parse_cnn_rss_or_headlines(
	raw_text: str,
	source_id: str = "cnn_indonesia",
	rubric_id: str = "cnn_nasional",
	rubric_name: str = "Nasional",
	base_url: str = "https://www.cnnindonesia.com/nasional",
	max_articles: int = 40,
) -> List[Article]:
	"""Extract article list from CNN Indonesia rubric HTML or RSS feed."""
	stripped = (raw_text or "").lstrip()
	if stripped.startswith("<?xml") or stripped.startswith("<rss") or stripped.startswith("<feed"):
		res = _parse_generic_rss_xml(stripped, source_id, rubric_id, rubric_name, is_valid_cnn_article_url, max_articles)
		if res:
			return res
	return _parse_portal_rubric_headlines(
		raw_text, source_id, rubric_id, rubric_name, base_url, is_valid_cnn_article_url, max_articles
	)


def parse_cnbc_rss_or_headlines(
	raw_text: str,
	source_id: str = "cnbc_indonesia",
	rubric_id: str = "cnbc_market",
	rubric_name: str = "Market",
	base_url: str = "https://www.cnbcindonesia.com/market",
	max_articles: int = 40,
) -> List[Article]:
	"""Extract article list from CNBC Indonesia rubric HTML or RSS feed."""
	stripped = (raw_text or "").lstrip()
	if stripped.startswith("<?xml") or stripped.startswith("<rss") or stripped.startswith("<feed"):
		res = _parse_generic_rss_xml(stripped, source_id, rubric_id, rubric_name, is_valid_cnbc_article_url, max_articles)
		if res:
			return res
	return _parse_portal_rubric_headlines(
		raw_text, source_id, rubric_id, rubric_name, base_url, is_valid_cnbc_article_url, max_articles
	)


def parse_tempo_rss_or_headlines(
	raw_text: str,
	source_id: str = "tempo",
	rubric_id: str = "tempo_politik",
	rubric_name: str = "Politik",
	base_url: str = "https://www.tempo.co/politik",
	max_articles: int = 40,
) -> List[Article]:
	"""Extract article list from Tempo.co rubric HTML or RSS feed."""
	stripped = (raw_text or "").lstrip()
	if stripped.startswith("<?xml") or stripped.startswith("<rss") or stripped.startswith("<feed"):
		res = _parse_generic_rss_xml(stripped, source_id, rubric_id, rubric_name, is_valid_tempo_article_url, max_articles)
		if res:
			return res
	return _parse_portal_rubric_headlines(
		raw_text, source_id, rubric_id, rubric_name, base_url, is_valid_tempo_article_url, max_articles
	)


def detect_portal_all_pages_url(html_string: str, current_url: str) -> Optional[str]:
	"""
	Inspect a CNN Indonesia, CNBC Indonesia, or Tempo.co article DOM for a verified
	full-page link (?page=all or ?single=1).
	"""
	if not html_string or not current_url:
		return None
	low_url = current_url.lower()
	if "page=all" in low_url or "single=1" in low_url:
		return None

	builder = _DOMBuilder()
	builder.feed(html_string)
	root = builder.root

	for node in _iter_nodes(root):
		if node.tag == "a":
			href = (node.attrs.get("href") or "").strip()
			if not href:
				continue
			href_low = href.lower()
			txt_low = node.get_text().lower()
			if ("page=all" in href_low or "single=1" in href_low) and (
				"semua halaman" in txt_low
				or "tampilkan semua" in txt_low
				or "show all" in txt_low
				or "halaman" in txt_low
				or "detail" in " ".join(node.classes).lower()
			):
				return urllib.parse.urljoin(current_url, href)
	return None


def _clean_portal_paragraph_text(text: str) -> str:
	"""Strip inline widgets ('[Gambas:...]') from paragraph text."""
	if not text:
		return ""
	cleaned = " ".join(text.split()).strip()
	cleaned = re.sub(r"\[Gambas:[^\]]*\]", "", cleaned, flags=re.IGNORECASE).strip()
	cleaned = re.sub(
		r"^(?:Baca\s+juga|Lihat\s+juga|Pilihan\s+Editor|Baca)\s*:\s*.*$",
		"",
		cleaned,
		flags=re.IGNORECASE,
	).strip()
	return cleaned


def _extract_portal_table_block(table_node: _DOMNode) -> Optional[Dict[str, Any]]:
	"""Extract a genuine data table while skipping inline 'linksisip' related-link tables."""
	if _is_portal_inline_related_node(table_node):
		return None

	headers: List[str] = []
	rows: List[List[str]] = []
	for tr in _iter_nodes(table_node):
		if tr.tag != "tr":
			continue
		th_cells: List[str] = []
		td_cells: List[str] = []
		for cell in tr.children:
			if not isinstance(cell, _DOMNode):
				continue
			if cell.tag == "th":
				th_cells.append(cell.get_text())
			elif cell.tag == "td":
				td_cells.append(cell.get_text())
		if th_cells and not headers and not td_cells:
			headers = th_cells
		elif th_cells and td_cells:
			rows.append(th_cells + td_cells)
		elif td_cells:
			if not headers and len(rows) == 0 and all(len(c) < 50 for c in td_cells):
				headers = td_cells
			else:
				rows.append(td_cells)

	if not headers and not rows:
		return None
	if headers and not rows:
		return None
	return ContentBlock(block_type="table", headers=headers, rows=rows).to_dict()


def _extract_portal_blocks_from_container(container_node: _DOMNode, blocks: List[Dict[str, Any]], page_url: str = "") -> None:
	"""Recursively extract structured ContentBlocks from a CNN, CNBC, or Tempo article container."""
	direct_text_parts: List[str] = []

	def _flush_direct_text() -> None:
		if not direct_text_parts:
			return
		raw = " ".join("".join(direct_text_parts).split()).strip()
		direct_text_parts.clear()
		cleaned = _clean_portal_paragraph_text(raw)
		if cleaned and len(cleaned) >= 3 and not _is_portal_noise_text(cleaned):
			blocks.append(ContentBlock(block_type="p", text=cleaned).to_dict())

	for child in container_node.children:
		if isinstance(child, str):
			if child.strip():
				direct_text_parts.append(child)
			continue

		if not isinstance(child, _DOMNode):
			continue

		if child.tag == "br":
			_flush_direct_text()
			continue

		if child.tag in ("strong", "b", "em", "i", "u", "span", "a", "small", "sup", "sub"):
			if not _is_portal_excluded_node(child) and not _is_portal_inline_related_node(child):
				txt = child.get_text()
				if txt:
					direct_text_parts.append(f" {txt} ")
			continue

		_flush_direct_text()

		if _is_portal_inline_related_node(child):
			continue
		if _extract_inline_media_blocks_from_node(child, blocks, page_url):
			continue
		if _is_portal_excluded_node(child):
			continue

		t = child.tag
		if t in ("h2", "h3", "h4"):
			text = _clean_portal_paragraph_text(child.get_text())
			if text and not _is_portal_noise_text(text):
				blocks.append(ContentBlock(block_type=t, text=text).to_dict())

		elif t == "blockquote":
			text = _clean_portal_paragraph_text(child.get_text())
			if text and not _is_portal_noise_text(text):
				blocks.append(ContentBlock(block_type="blockquote", text=text).to_dict())

		elif t in ("ul", "ol"):
			items: List[str] = []
			for li in child.children:
				if isinstance(li, _DOMNode) and li.tag == "li" and not _is_portal_excluded_node(li):
					it_txt = _clean_portal_paragraph_text(li.get_text())
					if it_txt and not _is_portal_noise_text(it_txt):
						items.append(it_txt)
			if items:
				blocks.append(ContentBlock(block_type=t, items=items).to_dict())

		elif t == "table":
			tbl_block = _extract_portal_table_block(child)
			if tbl_block:
				blocks.append(tbl_block)

		elif t in ("figure", "figcaption"):
			cap_text = _clean_portal_paragraph_text(child.get_text())
			if cap_text and len(cap_text) > 12 and not _is_portal_noise_text(cap_text):
				blocks.append(ContentBlock(block_type="caption", text=cap_text).to_dict())

		elif t == "p":
			text = _clean_portal_paragraph_text(child.get_text())
			if text and len(text) >= 3 and not _is_portal_noise_text(text):
				blocks.append(ContentBlock(block_type="p", text=text).to_dict())

		else:
			_extract_portal_blocks_from_container(child, blocks, page_url=page_url)

	_flush_direct_text()


def _extract_json_ld_article_metadata(html_string: str) -> Dict[str, str]:
	"""
	Extract structured article metadata (headline, datePublished, author, description, articleBody)
	from <script type="application/ld+json"> blocks when available.
	"""
	result: Dict[str, str] = {}
	if not html_string:
		return result

	script_matches = re.findall(
		r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
		html_string,
		flags=re.IGNORECASE | re.DOTALL,
	)
	for raw_json in script_matches:
		try:
			data = json.loads(raw_json.strip())
		except Exception:
			continue

		items = data if isinstance(data, list) else [data]
		for obj in items:
			if not isinstance(obj, dict):
				continue
			graph = obj.get("@graph")
			if isinstance(graph, list):
				items.extend(g for g in graph if isinstance(g, dict))

			atype = str(obj.get("@type") or "").lower()
			if any(k in atype for k in ("newsarticle", "article", "reportagenewsarticle", "webpage")):
				if not result.get("title") and obj.get("headline"):
					result["title"] = html.unescape(str(obj["headline"])).strip()
				if not result.get("published_at") and obj.get("datePublished"):
					result["published_at"] = str(obj["datePublished"]).strip()
				if not result.get("description") and obj.get("description"):
					result["description"] = html.unescape(str(obj["description"])).strip()
				if not result.get("articleBody") and obj.get("articleBody"):
					result["articleBody"] = html.unescape(str(obj["articleBody"])).strip()
				if not result.get("author") and obj.get("author"):
					au = obj["author"]
					if isinstance(au, dict) and au.get("name"):
						result["author"] = str(au["name"]).strip()
					elif isinstance(au, list):
						names = [str(a.get("name", "")).strip() for a in au if isinstance(a, dict) and a.get("name")]
						if names:
							result["author"] = ", ".join(names)
					elif isinstance(au, str):
						result["author"] = au.strip()
	return result


def parse_portal_article_html(
	html_string: str,
	url: str,
	default_category: str = "",
	portal_label: str = "CNN Indonesia",
) -> Dict[str, Any]:
	"""
	Parse a full article page from CNN Indonesia, CNBC Indonesia, or Tempo.co into structured
	metadata and NVDA-ready ContentBlocks.
	"""
	builder = _DOMBuilder()
	builder.feed(html_string or "")
	root = builder.root

	ld_meta = _extract_json_ld_article_metadata(html_string)

	title = ld_meta.get("title", "")
	published_at = ld_meta.get("published_at", "")
	category = default_category or ""
	author = ld_meta.get("author", "")
	editor = ""
	summary_deck = ""
	main_caption = ""
	source_credit = ""
	meta_description = ld_meta.get("description", "")

	content_containers: List[_DOMNode] = []

	for node in _iter_nodes(root):
		if node.tag == "meta":
			meta_name = (node.attrs.get("name") or node.attrs.get("property") or "").lower()
			meta_content = (node.attrs.get("content") or "").strip()
			if not meta_content:
				continue
			if meta_name in ("author", "dtk:author", "content_author") and not author:
				author = html.unescape(meta_content).strip()
			elif meta_name in ("dtk:publishdate", "publishdate", "article:published_time", "content_publisheddate") and not published_at:
				published_at = html.unescape(meta_content).strip()
			elif meta_name in ("dtk:kanal", "article:section", "content_category") and not category:
				category = html.unescape(meta_content).strip()
			elif meta_name in ("description", "og:description") and not meta_description:
				meta_description = html.unescape(meta_content).strip()
			elif meta_name == "og:title" and not title:
				title = html.unescape(meta_content).strip()

		if node.tag == "h1":
			t_txt = node.get_text()
			if t_txt and len(t_txt) >= 10:
				title = t_txt

		cls_joined = " ".join(node.classes).lower()

		# Author & date DOM nodes
		if any(k in cls_joined for k in ("detail__author", "detail_author", "author", "penulis", "reporter")):
			au_txt = node.get_text()
			if au_txt and len(au_txt) < 100 and not _is_portal_noise_text(au_txt):
				author = au_txt

		if any(k in cls_joined for k in ("detail__date", "detail_date", "date", "tanggal")) or node.tag == "time":
			dt_txt = node.get_text()
			if dt_txt and 5 < len(dt_txt) < 80 and not _is_portal_noise_text(dt_txt):
				published_at = dt_txt

		# Main image caption
		if not main_caption and (
			any(k in cls_joined for k in ("detail__media-caption", "media_caption", "photo-caption", "caption"))
			or node.tag == "figcaption"
		):
			cap_txt = _clean_portal_paragraph_text(node.get_text())
			if cap_txt and len(cap_txt) > 12 and not _is_portal_noise_text(cap_txt):
				main_caption = cap_txt

		# Primary body containers across CNN Indonesia, CNBC Indonesia, and Tempo.co
		if (
			any(
				c in node.classes
				for c in (
					"detail-text",
					"detail_text",
					"detail__body-text",
					"itp_bodycontent",
					"detail-in",
					"detail-konten",
					"content-detail",
					"article-content",
				)
			)
			or node.id in ("detikdetailtext", "isi", "article-body")
		):
			content_containers.append(node)

	blocks: List[Dict[str, Any]] = []
	if main_caption:
		blocks.append(ContentBlock(block_type="caption", text=main_caption).to_dict())

	if content_containers:
		for container in content_containers:
			_extract_portal_blocks_from_container(container, blocks, page_url=url)
	else:
		# Fallback to <article> or <main> DOM subtree
		for node in _iter_nodes(root):
			if node.tag in ("article", "main"):
				_extract_portal_blocks_from_container(node, blocks, page_url=url)
				if blocks:
					break

	# Fallback to JSON-LD articleBody if DOM container had no paragraphs (e.g. heavy SSR/hydration page)
	substantive_blocks = [
		b for b in blocks
		if b.get("type") in ("p", "ul", "ol", "table", "blockquote")
	]
	if not substantive_blocks and ld_meta.get("articleBody"):
		raw_body = ld_meta["articleBody"]
		for para in re.split(r"\n+|\r\n+", raw_body):
			cleaned_p = _clean_portal_paragraph_text(para)
			if cleaned_p and len(cleaned_p) >= 10 and not _is_portal_noise_text(cleaned_p):
				blocks.append(ContentBlock(block_type="p", text=cleaned_p).to_dict())

	# Deduplicate consecutive identical blocks
	deduped_blocks: List[Dict[str, Any]] = []
	for b in blocks:
		if deduped_blocks and deduped_blocks[-1] == b:
			continue
		deduped_blocks.append(b)
	blocks = deduped_blocks

	substantive_blocks = [
		b for b in blocks
		if b.get("type") in ("p", "ul", "ol", "table", "blockquote")
	]

	if not summary_deck:
		if substantive_blocks and substantive_blocks[0].get("text"):
			summary_deck = substantive_blocks[0]["text"]
		elif meta_description and not _is_portal_noise_text(meta_description):
			summary_deck = meta_description

	if len(substantive_blocks) >= 2 or (
		len(substantive_blocks) == 1 and len(substantive_blocks[0].get("text", "")) >= 100
	):
		status = ArticleStatus.CONTENT_LOADED
	elif len(substantive_blocks) == 1 or summary_deck:
		status = ArticleStatus.CONTENT_PARTIAL
		if not substantive_blocks and summary_deck:
			blocks.append(ContentBlock(block_type="p", text=summary_deck).to_dict())
	else:
		status = ArticleStatus.CONTENT_FAILED

	# Extract trailing editor initials credit (e.g. "(arj/arj)" )
	if blocks and blocks[-1].get("type") == "p":
		last_txt = blocks[-1].get("text", "")
		m_cred = re.search(r"\(([a-z0-9]{2,6}/[a-z0-9]{2,6})\)\s*$", last_txt.strip(), re.IGNORECASE)
		if m_cred:
			source_credit = f"({m_cred.group(1)})"
			if not editor:
				editor = m_cred.group(1)

	photos, videos = extract_article_media_from_dom(
		root=root,
		content_containers=content_containers,
		html_string=html_string,
		page_url=url,
		main_caption=main_caption,
		default_title=title,
	)
	if (photos or videos) and status == ArticleStatus.CONTENT_FAILED:
		status = ArticleStatus.CONTENT_LOADED

	return {
		"title": title,
		"category": category or default_category or portal_label,
		"published_at": published_at,
		"author": author,
		"editor": editor,
		"url": url,
		"canonical_url": normalize_canonical_url(url),
		"summary": summary_deck,
		"source_credit": source_credit,
		"content": blocks,
		"photos": photos,
		"videos": videos,
		"content_status": status,
	}


# Official Tempo RSS and Google News RSS fallback mapping when Cloudflare challenges www.tempo.co
TEMPO_RUBRIC_FALLBACK_FEEDS: Dict[str, List[str]] = {
	"tempo_play": [
		"https://rss.tempo.co/nasional",
		"https://news.google.com/rss/search?q=site:tempo.co&hl=id&gl=ID&ceid=ID:id",
	],
	"tempo_politik": [
		"https://rss.tempo.co/nasional",
		"https://news.google.com/rss/search?q=site:tempo.co/politik&hl=id&gl=ID&ceid=ID:id",
	],
	"tempo_hukum": [
		"https://rss.tempo.co/nasional",
		"https://news.google.com/rss/search?q=site:tempo.co/hukum&hl=id&gl=ID&ceid=ID:id",
	],
	"tempo_ekonomi": [
		"https://rss.tempo.co/bisnis",
		"https://news.google.com/rss/search?q=site:tempo.co/ekonomi&hl=id&gl=ID&ceid=ID:id",
	],
	"tempo_lingkungan": [
		"https://rss.tempo.co/tekno",
		"https://news.google.com/rss/search?q=site:tempo.co/lingkungan&hl=id&gl=ID&ceid=ID:id",
	],
	"tempo_wawancara": [
		"https://rss.tempo.co/nasional",
		"https://news.google.com/rss/search?q=site:tempo.co/wawancara&hl=id&gl=ID&ceid=ID:id",
	],
	"tempo_investigasi": [
		"https://rss.tempo.co/nasional",
		"https://news.google.com/rss/search?q=site:tempo.co/investigasi&hl=id&gl=ID&ceid=ID:id",
	],
	"tempo_cekfakta": [
		"https://rss.tempo.co/nasional",
		"https://news.google.com/rss/search?q=site:tempo.co/cekfakta&hl=id&gl=ID&ceid=ID:id",
	],
	"tempo_tokoh": [
		"https://rss.tempo.co/nasional",
		"https://news.google.com/rss/search?q=site:tempo.co/tokoh&hl=id&gl=ID&ceid=ID:id",
	],
	"tempo_newsletter": [
		"https://rss.tempo.co/nasional",
		"https://news.google.com/rss/search?q=site:tempo.co&hl=id&gl=ID&ceid=ID:id",
	],
	"tempo_info_tempo": [
		"https://rss.tempo.co/event",
		"https://news.google.com/rss/search?q=site:tempo.co/info-tempo&hl=id&gl=ID&ceid=ID:id",
	],
}


def parse_tempo_syndication_xml(
	xml_string: str,
	source_id: str,
	rubric_id: str,
	rubric_name: str,
	max_articles: int = 40,
) -> List[Article]:
	"""
	Parse Tempo RSS or Google News RSS feed for Tempo.co when Cloudflare blocks direct HTML access.
	Extracts title, link, pubDate, description, and builds initial content blocks from description
	so the user can read the article summary even if the full article page is challenged.
	"""
	articles: List[Article] = []
	seen_canonical: Set[str] = set()
	try:
		root = ET.fromstring((xml_string or "").lstrip())
		for item in root.iter("item"):
			title = (item.findtext("title") or "").strip()
			# Remove trailing " - Tempo.co" from Google News RSS titles
			title = re.sub(r"\s*[\-–]\s*Tempo\.co\s*$", "", title, flags=re.IGNORECASE).strip()
			link = (item.findtext("link") or "").strip()
			pub_date = (item.findtext("pubDate") or "").strip()
			desc_raw = (item.findtext("description") or "").strip()
			desc_clean = re.sub(r"<[^>]+>", " ", html.unescape(desc_raw))
			desc_clean = " ".join(desc_clean.split()).strip()
			desc_clean = re.sub(r"\s+Tempo\.co\s*$", "", desc_clean, flags=re.IGNORECASE).strip()

			if not title or not link:
				continue
			canonical = normalize_canonical_url(link)
			if not canonical or canonical in seen_canonical:
				continue
			seen_canonical.add(canonical)

			initial_blocks = []
			if desc_clean and len(desc_clean) >= 15 and desc_clean.lower() != title.lower():
				initial_blocks.append(ContentBlock(block_type="p", text=desc_clean).to_dict())

			articles.append(
				Article(
					source_id=source_id,
					rubric_id=rubric_id,
					title=title,
					url=link,
					canonical_url=canonical,
					published_at=pub_date,
					summary=desc_clean if desc_clean.lower() != title.lower() else "",
					content=initial_blocks,
					category_label=rubric_name,
					content_status=ArticleStatus.HEADLINE_LOADED,
				)
			)
			if len(articles) >= max_articles:
				break
	except Exception:
		return []
	return articles
