# -*- coding: utf-8 -*-
"""
Configuration and user preferences manager for NewsHub for NVDA.

Uses the official NVDA configuration system (`config.conf["newsHub"]`) under the unique
namespace `"newsHub"`, with fault-tolerant fallback storage when legacy configuration
values are malformed or when running in standalone unit test environments.
"""

import json
import os
from typing import Any, Dict
from .sources import get_default_site, get_site_by_id

CONFIG_SECTION = "newsHub"

# NVDA configobj schema specification for the "newsHub" namespace
NEWSHUB_CONFIG_SPEC: Dict[str, str] = {
	"language": 'string(default="id")',
	"last_site_id": 'string(default="kompas")',
	"last_rubric_id": 'string(default="news")',
	"color_theme": 'string(default="light")',
	"font_scale": "integer(default=100, min=85, max=150)",
	"font_family": 'string(default="sans_serif")',
	"paragraph_spacing": 'string(default="normal")',
	"auto_refresh_enabled": "boolean(default=True)",
	"auto_refresh_interval_sec": "integer(default=60, min=30, max=600)",
	"max_articles": "integer(default=40, min=10, max=100)",
	"cache_ttl_sec": "integer(default=180, min=30, max=1800)",
}

DEFAULT_PREFERENCES: Dict[str, Any] = {
	"language": "id",                # 'id' (Bahasa Indonesia) | 'en' (English)
	"last_site_id": "kompas",
	"last_rubric_id": "news",
	"color_theme": "light",          # 'light' | 'dark' | 'high_contrast'
	"font_scale": 100,               # 85 .. 150 (%)
	"font_family": "sans_serif",     # 'sans_serif' | 'serif'
	"paragraph_spacing": "normal",   # 'normal' | 'wide'
	"auto_refresh_enabled": True,
	"auto_refresh_interval_sec": 60, # 60 seconds (1 minute)
	"max_articles": 40,
	"cache_ttl_sec": 180,
}

VALID_LANGUAGES = ("id", "en")
VALID_THEMES = ("light", "dark", "high_contrast")
VALID_FONT_FAMILIES = ("sans_serif", "serif")
VALID_PARAGRAPH_SPACINGS = ("normal", "wide")
VALID_FONT_SCALES = (85, 90, 95, 100, 110, 120, 130, 140, 150)

# Color palettes designed with high contrast ratios for screen-reader and low-vision users
THEME_PALETTES: Dict[str, Dict[str, Any]] = {
	"light": {
		"label": "Light",
		"dialog_bg": (245, 247, 250),
		"panel_bg": (255, 255, 255),
		"text_fg": (20, 24, 31),
		"control_bg": (255, 255, 255),
		"control_fg": (20, 24, 31),
		"status_bg": (232, 238, 245),
		"status_fg": (15, 41, 66),
	},
	"dark": {
		"label": "Dark",
		"dialog_bg": (28, 32, 38),
		"panel_bg": (22, 25, 30),
		"text_fg": (235, 239, 245),
		"control_bg": (38, 43, 51),
		"control_fg": (235, 239, 245),
		"status_bg": (34, 45, 60),
		"status_fg": (210, 228, 255),
	},
	"high_contrast": {
		"label": "High Contrast",
		"dialog_bg": (0, 0, 0),
		"panel_bg": (0, 0, 0),
		"text_fg": (255, 255, 0),
		"control_bg": (0, 0, 0),
		"control_fg": (255, 255, 255),
		"status_bg": (0, 0, 0),
		"status_fg": (0, 255, 255),
	},
}


def _log_warning(msg: str) -> None:
	try:
		from logHandler import log
		log.warning(f"NewsHub Config: {msg}")
	except Exception:
		pass


class ConfigManager:
	"""Manage reading, validating, and persisting user preferences."""
	def __init__(self, fallback_path: str = ""):
		self._memory_store: Dict[str, Any] = dict(DEFAULT_PREFERENCES)
		self._fallback_path = fallback_path
		self._nvda_config_available = False
		self.init_config()

	def init_config(self) -> None:
		"""
		Register the configuration specification under `config.conf.spec["newsHub"]`
		without modifying any global NVDA settings outside the add-on's namespace.
		"""
		try:
			import config
			if hasattr(config, "conf") and config.conf is not None:
				if CONFIG_SECTION not in config.conf.spec:
					config.conf.spec[CONFIG_SECTION] = dict(NEWSHUB_CONFIG_SPEC)
				else:
					for key, spec_val in NEWSHUB_CONFIG_SPEC.items():
						if key not in config.conf.spec[CONFIG_SECTION]:
							config.conf.spec[CONFIG_SECTION][key] = spec_val
				self._nvda_config_available = True
		except Exception as e:
			_log_warning(f"NVDA config module is not active in this environment ({e}); using local fallback storage.")
			self._nvda_config_available = False

		if not self._nvda_config_available and self._fallback_path and os.path.isfile(self._fallback_path):
			try:
				with open(self._fallback_path, "r", encoding="utf-8") as f:
					loaded = json.load(f)
				if isinstance(loaded, dict):
					self._memory_store.update(loaded)
			except Exception as e:
				_log_warning(f"Failed to load fallback configuration file: {e}")

		self._sanitize_all()

	def _get_raw(self, key: str) -> Any:
		if self._nvda_config_available:
			try:
				import config
				section = config.conf[CONFIG_SECTION]
				return section.get(key, DEFAULT_PREFERENCES[key])
			except Exception as e:
				_log_warning(f"Failed to read key '{key}' from NVDA config: {e}")
		return self._memory_store.get(key, DEFAULT_PREFERENCES.get(key))

	def _set_raw(self, key: str, value: Any) -> None:
		self._memory_store[key] = value
		if self._nvda_config_available:
			try:
				import config
				config.conf[CONFIG_SECTION][key] = value
			except Exception as e:
				_log_warning(f"Failed to write key '{key}' to NVDA config: {e}")
		elif self._fallback_path:
			try:
				os.makedirs(os.path.dirname(self._fallback_path), exist_ok=True)
				with open(self._fallback_path, "w", encoding="utf-8") as f:
					json.dump(self._memory_store, f, ensure_ascii=False, indent=2)
			except Exception as e:
				_log_warning(f"Failed to write fallback configuration file: {e}")

	def _sanitize_all(self) -> None:
		"""Ensure all configuration values are valid and safe against corrupted legacy data."""
		for key in DEFAULT_PREFERENCES:
			val = self.get(key)
			self._set_raw(key, val)

	def get(self, key: str) -> Any:
		"""Retrieve a validated configuration value with safe defaults."""
		raw = self._get_raw(key)

		if key == "language":
			lang = str(raw or "id").strip().lower()
			return lang if lang in VALID_LANGUAGES else "id"

		if key == "last_site_id":
			site_id = str(raw or "kompas").strip().lower()
			if not get_site_by_id(site_id):
				return DEFAULT_PREFERENCES["last_site_id"]
			return site_id

		if key == "last_rubric_id":
			rubric_id = str(raw or "news").strip().lower()
			site = get_site_by_id(self.get("last_site_id")) or get_default_site()
			if site.supported and site.get_rubric_by_id(rubric_id) is None:
				return site.rubrics[0].id if site.rubrics else "news"
			return rubric_id

		if key == "color_theme":
			theme = str(raw or "light").strip().lower()
			return theme if theme in VALID_THEMES else "light"

		if key == "font_scale":
			try:
				scale = int(raw)
				return max(85, min(150, scale))
			except (ValueError, TypeError):
				return 100

		if key == "font_family":
			fam = str(raw or "sans_serif").strip().lower()
			return fam if fam in VALID_FONT_FAMILIES else "sans_serif"

		if key == "paragraph_spacing":
			sp = str(raw or "normal").strip().lower()
			return sp if sp in VALID_PARAGRAPH_SPACINGS else "normal"

		if key == "auto_refresh_enabled":
			if isinstance(raw, bool):
				return raw
			if isinstance(raw, str):
				return raw.strip().lower() in ("true", "1", "yes", "ya")
			return bool(raw)

		if key == "auto_refresh_interval_sec":
			try:
				sec = int(raw)
				return max(30, min(600, sec))
			except (ValueError, TypeError):
				return 60

		if key == "max_articles":
			try:
				cnt = int(raw)
				return max(10, min(100, cnt))
			except (ValueError, TypeError):
				return 40

		if key == "cache_ttl_sec":
			try:
				ttl = int(raw)
				return max(30, min(1800, ttl))
			except (ValueError, TypeError):
				return 180

		return raw

	def set(self, key: str, value: Any) -> None:
		"""Validate and persist a single configuration value."""
		self._set_raw(key, value)
		validated = self.get(key)
		self._set_raw(key, validated)

	def update_preferences(self, updates: Dict[str, Any]) -> None:
		"""Safely update multiple configuration preferences at once."""
		for k, v in updates.items():
			if k in DEFAULT_PREFERENCES:
				self.set(k, v)


# Singleton instance shared across all add-on modules
config_manager = ConfigManager()
