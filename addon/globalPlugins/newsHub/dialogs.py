# -*- coding: utf-8 -*-
"""
Accessible wxPython desktop user interface and NVDA Settings panel for NewsHub for NVDA.

Provides:
- `NewsHubSettingsPanel`: Official NVDA Settings category panel integrated into
  `NVDA Preferences -> Settings -> NewsHub for NVDA` with language selection ('id' / 'en'),
  visual theme, typography, and background auto-refresh settings.
- `AccessibilitySettingsDialog`: Standalone settings dialog accessible directly from the
  dashboard or Preferences menu.
- `NewsHubDashboardDialog`: Main news reader dashboard following a 12-step logical tab order,
  full bilingual UI ('id' and 'en'), `wx.CallAfter` thread safety, non-intrusive 1-minute
  background auto-refresh, and standard NVDA screen reader announcements.
"""

import time
import webbrowser
from typing import Callable, List, Optional

try:
	import wx
except ImportError:
	wx = None  # Allows importing the module in headless unit test environments

try:
	import gui
	from gui import guiHelper
	from gui.settingsDialogs import SettingsPanel
except ImportError:
	gui = None
	guiHelper = None
	SettingsPanel = object

from .article_manager import ArticleManager
from .config_manager import (
	THEME_PALETTES,
	VALID_FONT_SCALES,
	VALID_LANGUAGES,
	config_manager,
)
from .formatter import (
	format_article_for_reading,
	format_article_selection_announcement,
)
from .i18n import SUPPORTED_LANGUAGES, tr
from .models import Article, ArticleStatus, RubricConfig, SiteConfig
from .sources import get_all_sites, get_default_site


_last_announced_text: str = ""
_last_announced_time: float = 0.0
_settings_change_listeners: List[Callable[[], None]] = []


def register_settings_change_listener(callback: Callable[[], None]) -> None:
	"""Register a callback to be invoked on the GUI thread when settings are saved."""
	if callback not in _settings_change_listeners:
		_settings_change_listeners.append(callback)


def unregister_settings_change_listener(callback: Callable[[], None]) -> None:
	"""Unregister a previously registered settings change callback."""
	if callback in _settings_change_listeners:
		_settings_change_listeners.remove(callback)


def notify_settings_changed() -> None:
	"""Notify all active listeners that user preferences have been updated."""
	for callback in list(_settings_change_listeners):
		try:
			if wx is not None and not wx.IsMainThread():
				wx.CallAfter(callback)
			else:
				callback()
		except Exception:
			pass


def announce_nvda(message: str, allow_repeat_after_sec: float = 1.5) -> None:
	"""
	Safely announce a status message through NVDA (`ui.message`) on the main GUI thread
	while suppressing consecutive duplicate announcements within a short time window.
	"""
	global _last_announced_text, _last_announced_time
	if not message or not message.strip():
		return
	cleaned = " ".join(message.split()).strip()
	now = time.monotonic()
	if cleaned == _last_announced_text and (now - _last_announced_time) < allow_repeat_after_sec:
		return
	_last_announced_text = cleaned
	_last_announced_time = now

	def _speak():
		try:
			import ui
			ui.message(cleaned)
		except Exception:
			pass

	if wx is not None:
		try:
			if wx.IsMainThread():
				_speak()
			else:
				wx.CallAfter(_speak)
			return
		except Exception:
			pass
	_speak()


def _build_settings_choices():
	"""Build localized choice lists and key mappings for settings controls."""
	lang_keys = list(VALID_LANGUAGES)
	lang_labels = [SUPPORTED_LANGUAGES.get(k, k) for k in lang_keys]

	theme_keys = ["light", "dark", "high_contrast"]
	theme_labels = [
		tr("theme_light"),
		tr("theme_dark"),
		tr("theme_high_contrast"),
	]

	scale_values = list(VALID_FONT_SCALES)
	default_sfx = tr("default_suffix")
	scale_labels = [f"{s}%" + (default_sfx if s == 100 else "") for s in scale_values]

	family_keys = ["sans_serif", "serif"]
	family_labels = [tr("font_sans_serif"), tr("font_serif")]

	spacing_keys = ["normal", "wide"]
	spacing_labels = [tr("spacing_normal"), tr("spacing_wide")]

	interval_values = [30, 60, 120, 180, 300, 600]
	interval_labels = [
		tr("interval_30s"),
		tr("interval_60s"),
		tr("interval_120s"),
		tr("interval_180s"),
		tr("interval_300s"),
		tr("interval_600s"),
	]

	max_values = [20, 30, 40, 50, 75, 100]
	max_labels = [
		tr("max_articles_item", count=m, suffix=(default_sfx if m == 40 else ""))
		for m in max_values
	]

	return {
		"lang_keys": lang_keys,
		"lang_labels": lang_labels,
		"theme_keys": theme_keys,
		"theme_labels": theme_labels,
		"scale_values": scale_values,
		"scale_labels": scale_labels,
		"family_keys": family_keys,
		"family_labels": family_labels,
		"spacing_keys": spacing_keys,
		"spacing_labels": spacing_labels,
		"interval_values": interval_values,
		"interval_labels": interval_labels,
		"max_values": max_values,
		"max_labels": max_labels,
	}


if wx is not None and SettingsPanel is not object:

	class NewsHubSettingsPanel(SettingsPanel):
		"""
		Official NVDA Settings category panel registered under NVDA Preferences -> Settings.
		Allows configuring the add-on language (Indonesian or English), visual theme, font scale,
		font family, paragraph spacing, and background auto-refresh behavior.
		"""
		# Category title displayed in the NVDA Settings dialog list
		title = "NewsHub for NVDA"

		def makeSettings(self, settingsSizer: wx.Sizer) -> None:
			"""Populate the NVDA Settings panel controls using BoxSizerHelper."""
			meta = _build_settings_choices()
			self._lang_keys = meta["lang_keys"]
			self._theme_keys = meta["theme_keys"]
			self._scale_values = meta["scale_values"]
			self._family_keys = meta["family_keys"]
			self._spacing_keys = meta["spacing_keys"]
			self._interval_values = meta["interval_values"]
			self._max_values = meta["max_values"]

			s_helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

			# 1. Interface Language (Indonesian / English)
			self.choice_language = s_helper.addLabeledControl(
				tr("lbl_language"),
				wx.Choice,
				choices=meta["lang_labels"],
			)
			self.choice_language.SetName(tr("acc_language"))

			# 2. Display Color Theme
			self.choice_theme = s_helper.addLabeledControl(
				tr("lbl_theme"),
				wx.Choice,
				choices=meta["theme_labels"],
			)
			self.choice_theme.SetName(tr("acc_theme"))

			# 3. Font Size (85% - 150%)
			self.choice_scale = s_helper.addLabeledControl(
				tr("lbl_font_scale"),
				wx.Choice,
				choices=meta["scale_labels"],
			)
			self.choice_scale.SetName(tr("acc_font_scale"))

			# 4. Font Family (Sans-serif / Serif)
			self.choice_family = s_helper.addLabeledControl(
				tr("lbl_font_family"),
				wx.Choice,
				choices=meta["family_labels"],
			)
			self.choice_family.SetName(tr("acc_font_family"))

			# 5. Paragraph Spacing (Normal / Wide)
			self.choice_spacing = s_helper.addLabeledControl(
				tr("lbl_paragraph_spacing"),
				wx.Choice,
				choices=meta["spacing_labels"],
			)
			self.choice_spacing.SetName(tr("acc_paragraph_spacing"))

			# 6. Background Auto-Refresh Checkbox
			self.chk_auto_refresh = s_helper.addItem(
				wx.CheckBox(self, label=tr("chk_auto_refresh_label"))
			)
			self.chk_auto_refresh.SetName(tr("acc_chk_auto_refresh"))

			# 7. Auto-Refresh Interval
			self.choice_interval = s_helper.addLabeledControl(
				tr("lbl_refresh_interval"),
				wx.Choice,
				choices=meta["interval_labels"],
			)
			self.choice_interval.SetName(tr("acc_refresh_interval"))

			# 8. Maximum Articles per Rubric
			self.choice_max = s_helper.addLabeledControl(
				tr("lbl_max_articles"),
				wx.Choice,
				choices=meta["max_labels"],
			)
			self.choice_max.SetName(tr("acc_max_articles"))

			self._load_values()

		def _load_values(self) -> None:
			"""Load current configuration values into the panel controls."""
			lang = config_manager.get("language")
			self.choice_language.SetSelection(
				self._lang_keys.index(lang) if lang in self._lang_keys else 0
			)

			theme = config_manager.get("color_theme")
			self.choice_theme.SetSelection(
				self._theme_keys.index(theme) if theme in self._theme_keys else 0
			)

			scale = config_manager.get("font_scale")
			nearest_scale = min(self._scale_values, key=lambda x: abs(x - scale))
			self.choice_scale.SetSelection(self._scale_values.index(nearest_scale))

			family = config_manager.get("font_family")
			self.choice_family.SetSelection(
				self._family_keys.index(family) if family in self._family_keys else 0
			)

			spacing = config_manager.get("paragraph_spacing")
			self.choice_spacing.SetSelection(
				self._spacing_keys.index(spacing) if spacing in self._spacing_keys else 0
			)

			self.chk_auto_refresh.SetValue(bool(config_manager.get("auto_refresh_enabled")))

			interval = config_manager.get("auto_refresh_interval_sec")
			nearest_int = min(self._interval_values, key=lambda x: abs(x - interval))
			self.choice_interval.SetSelection(self._interval_values.index(nearest_int))

			max_art = config_manager.get("max_articles")
			nearest_max = min(self._max_values, key=lambda x: abs(x - max_art))
			self.choice_max.SetSelection(self._max_values.index(nearest_max))

		def onSave(self) -> None:
			"""Save updated preferences to NVDA configuration and notify any active dashboard."""
			updates = {
				"language": self._lang_keys[max(0, self.choice_language.GetSelection())],
				"color_theme": self._theme_keys[max(0, self.choice_theme.GetSelection())],
				"font_scale": self._scale_values[max(0, self.choice_scale.GetSelection())],
				"font_family": self._family_keys[max(0, self.choice_family.GetSelection())],
				"paragraph_spacing": self._spacing_keys[max(0, self.choice_spacing.GetSelection())],
				"auto_refresh_enabled": bool(self.chk_auto_refresh.GetValue()),
				"auto_refresh_interval_sec": self._interval_values[max(0, self.choice_interval.GetSelection())],
				"max_articles": self._max_values[max(0, self.choice_max.GetSelection())],
			}
			config_manager.update_preferences(updates)
			notify_settings_changed()

else:
	NewsHubSettingsPanel = None


if wx is not None:

	class AccessibilitySettingsDialog(wx.Dialog):
		"""
		Standalone Settings Dialog for NewsHub for NVDA (accessible from inside the dashboard
		or when opened directly from the menu). Includes interface language selection ('id' / 'en'),
		visual theme, typography, and auto-refresh settings.
		"""
		def __init__(self, parent: Optional[wx.Window]):
			super().__init__(
				parent,
				title=tr("settings_dialog_title"),
				style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
			)
			self.SetName(tr("acc_settings_dialog"))
			self._init_ui()
			self._load_current_values()
			self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

		def _init_ui(self) -> None:
			meta = _build_settings_choices()
			self._lang_keys = meta["lang_keys"]
			self._theme_keys = meta["theme_keys"]
			self._scale_values = meta["scale_values"]
			self._family_keys = meta["family_keys"]
			self._spacing_keys = meta["spacing_keys"]
			self._interval_values = meta["interval_values"]
			self._max_values = meta["max_values"]

			main_sizer = wx.BoxSizer(wx.VERTICAL)
			grid_sizer = wx.FlexGridSizer(rows=0, cols=2, vgap=10, hgap=12)
			grid_sizer.AddGrowableCol(1, 1)

			# 1. Interface Language
			lbl_lang = wx.StaticText(self, label=tr("lbl_language"))
			self.choice_language = wx.Choice(self, choices=meta["lang_labels"])
			self.choice_language.SetName(tr("acc_language"))
			grid_sizer.Add(lbl_lang, 0, wx.ALIGN_CENTER_VERTICAL)
			grid_sizer.Add(self.choice_language, 1, wx.EXPAND)

			# 2. Display Color Theme
			lbl_theme = wx.StaticText(self, label=tr("lbl_theme"))
			self.choice_theme = wx.Choice(self, choices=meta["theme_labels"])
			self.choice_theme.SetName(tr("acc_theme"))
			grid_sizer.Add(lbl_theme, 0, wx.ALIGN_CENTER_VERTICAL)
			grid_sizer.Add(self.choice_theme, 1, wx.EXPAND)

			# 3. Font Size (85% to 150%)
			lbl_scale = wx.StaticText(self, label=tr("lbl_font_scale"))
			self.choice_scale = wx.Choice(self, choices=meta["scale_labels"])
			self.choice_scale.SetName(tr("acc_font_scale"))
			grid_sizer.Add(lbl_scale, 0, wx.ALIGN_CENTER_VERTICAL)
			grid_sizer.Add(self.choice_scale, 1, wx.EXPAND)

			# 4. Font Family (Sans-serif or Serif)
			lbl_family = wx.StaticText(self, label=tr("lbl_font_family"))
			self.choice_family = wx.Choice(self, choices=meta["family_labels"])
			self.choice_family.SetName(tr("acc_font_family"))
			grid_sizer.Add(lbl_family, 0, wx.ALIGN_CENTER_VERTICAL)
			grid_sizer.Add(self.choice_family, 1, wx.EXPAND)

			# 5. Paragraph Spacing (Normal or Wide)
			lbl_spacing = wx.StaticText(self, label=tr("lbl_paragraph_spacing"))
			self.choice_spacing = wx.Choice(self, choices=meta["spacing_labels"])
			self.choice_spacing.SetName(tr("acc_paragraph_spacing"))
			grid_sizer.Add(lbl_spacing, 0, wx.ALIGN_CENTER_VERTICAL)
			grid_sizer.Add(self.choice_spacing, 1, wx.EXPAND)

			# 6. Background Auto-Refresh
			lbl_auto = wx.StaticText(self, label=tr("lbl_auto_refresh"))
			self.chk_auto_refresh = wx.CheckBox(self, label=tr("chk_auto_refresh_label"))
			self.chk_auto_refresh.SetName(tr("acc_chk_auto_refresh"))
			grid_sizer.Add(lbl_auto, 0, wx.ALIGN_CENTER_VERTICAL)
			grid_sizer.Add(self.chk_auto_refresh, 1, wx.EXPAND)

			# 7. Auto-Refresh Interval
			lbl_interval = wx.StaticText(self, label=tr("lbl_refresh_interval"))
			self.choice_interval = wx.Choice(self, choices=meta["interval_labels"])
			self.choice_interval.SetName(tr("acc_refresh_interval"))
			grid_sizer.Add(lbl_interval, 0, wx.ALIGN_CENTER_VERTICAL)
			grid_sizer.Add(self.choice_interval, 1, wx.EXPAND)

			# 8. Maximum Articles per Rubric
			lbl_max = wx.StaticText(self, label=tr("lbl_max_articles"))
			self.choice_max = wx.Choice(self, choices=meta["max_labels"])
			self.choice_max.SetName(tr("acc_max_articles"))
			grid_sizer.Add(lbl_max, 0, wx.ALIGN_CENTER_VERTICAL)
			grid_sizer.Add(self.choice_max, 1, wx.EXPAND)

			main_sizer.Add(grid_sizer, 1, wx.ALL | wx.EXPAND, 14)

			# Save & Cancel Buttons
			btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
			self.btn_save = wx.Button(self, wx.ID_OK, label=tr("btn_save_settings"))
			self.btn_save.SetName(tr("acc_btn_save_settings"))
			self.btn_save.SetDefault()

			self.btn_cancel = wx.Button(self, wx.ID_CANCEL, label=tr("btn_cancel"))
			self.btn_cancel.SetName(tr("acc_btn_cancel"))

			btn_sizer.AddStretchSpacer(1)
			btn_sizer.Add(self.btn_save, 0, wx.RIGHT, 8)
			btn_sizer.Add(self.btn_cancel, 0)
			main_sizer.Add(btn_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 14)

			self.SetSizerAndFit(main_sizer)
			self.CentreOnParent()
			self.Bind(wx.EVT_BUTTON, self._on_save, id=wx.ID_OK)

		def _load_current_values(self) -> None:
			lang = config_manager.get("language")
			self.choice_language.SetSelection(
				self._lang_keys.index(lang) if lang in self._lang_keys else 0
			)

			theme = config_manager.get("color_theme")
			self.choice_theme.SetSelection(
				self._theme_keys.index(theme) if theme in self._theme_keys else 0
			)

			scale = config_manager.get("font_scale")
			nearest_scale = min(self._scale_values, key=lambda x: abs(x - scale))
			self.choice_scale.SetSelection(self._scale_values.index(nearest_scale))

			family = config_manager.get("font_family")
			self.choice_family.SetSelection(
				self._family_keys.index(family) if family in self._family_keys else 0
			)

			spacing = config_manager.get("paragraph_spacing")
			self.choice_spacing.SetSelection(
				self._spacing_keys.index(spacing) if spacing in self._spacing_keys else 0
			)

			self.chk_auto_refresh.SetValue(bool(config_manager.get("auto_refresh_enabled")))

			interval = config_manager.get("auto_refresh_interval_sec")
			nearest_int = min(self._interval_values, key=lambda x: abs(x - interval))
			self.choice_interval.SetSelection(self._interval_values.index(nearest_int))

			max_art = config_manager.get("max_articles")
			nearest_max = min(self._max_values, key=lambda x: abs(x - max_art))
			self.choice_max.SetSelection(self._max_values.index(nearest_max))

		def _on_save(self, event: wx.CommandEvent) -> None:
			updates = {
				"language": self._lang_keys[max(0, self.choice_language.GetSelection())],
				"color_theme": self._theme_keys[max(0, self.choice_theme.GetSelection())],
				"font_scale": self._scale_values[max(0, self.choice_scale.GetSelection())],
				"font_family": self._family_keys[max(0, self.choice_family.GetSelection())],
				"paragraph_spacing": self._spacing_keys[max(0, self.choice_spacing.GetSelection())],
				"auto_refresh_enabled": bool(self.chk_auto_refresh.GetValue()),
				"auto_refresh_interval_sec": self._interval_values[max(0, self.choice_interval.GetSelection())],
				"max_articles": self._max_values[max(0, self.choice_max.GetSelection())],
			}
			config_manager.update_preferences(updates)
			notify_settings_changed()
			self.EndModal(wx.ID_OK)

		def _on_char_hook(self, event: wx.KeyEvent) -> None:
			if event.GetKeyCode() == wx.WXK_ESCAPE:
				self.EndModal(wx.ID_CANCEL)
				return
			event.Skip()


	class NewsHubDashboardDialog(wx.Dialog):
		"""
		Main NewsHub for NVDA dashboard dialog with a 12-step logical tab order,
		bilingual interface ('id' / 'en'), and full NVDA screen reader accessibility.
		"""
		def __init__(self, parent: Optional[wx.Window], article_manager: ArticleManager):
			super().__init__(
				parent,
				title=tr("dashboard_window_title"),
				style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX | wx.MINIMIZE_BOX,
				size=wx.Size(880, 680),
			)
			self.SetName(tr("dashboard_window_title"))
			self.article_manager = article_manager
			self._is_closing: bool = False

			self._sites: List[SiteConfig] = get_all_sites()
			self._active_site: SiteConfig = get_default_site()
			self._active_rubrics: List[RubricConfig] = []
			self._active_rubric: Optional[RubricConfig] = None
			self._articles: List[Article] = []
			self._current_article: Optional[Article] = None

			self._auto_refresh_timer = wx.Timer(self)
			self.Bind(wx.EVT_TIMER, self._on_auto_refresh_timer, self._auto_refresh_timer)

			self._build_ui()
			self._bind_events()
			self._apply_visual_preferences()
			self._restore_last_context_and_load()
			self._configure_auto_refresh_timer()
			register_settings_change_listener(self._on_external_settings_changed)

		def _build_ui(self) -> None:
			"""
			Build the dashboard layout following the 12-step logical tab order:
			1. Dashboard title banner.
			2. News portal selection.
			3. News rubric selection.
			4. Article headline selection.
			5. Loading status information.
			6. Full article content reading area.
			7. Previous and Next article navigation buttons.
			8. Refresh article list button.
			9. Reload current article button.
			10. Open original article in browser button (plus Back to Rubric & Back to Portal buttons).
			11. Accessibility settings button.
			12. Close dashboard button.
			"""
			self.panel = wx.Panel(self, style=wx.TAB_TRAVERSAL)
			root_sizer = wx.BoxSizer(wx.VERTICAL)

			# 1. Dashboard Title Banner (read-only single-line text control at step 1 in Tab order)
			self.lbl_header = wx.StaticText(self.panel, label=tr("lbl_dashboard_header"))
			self.txt_dashboard_title = wx.TextCtrl(
				self.panel,
				value=tr("dashboard_banner_text"),
				style=wx.TE_READONLY,
			)
			self.txt_dashboard_title.SetName(tr("acc_dashboard_header"))
			header_sizer = wx.BoxSizer(wx.HORIZONTAL)
			header_sizer.Add(self.lbl_header, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
			header_sizer.Add(self.txt_dashboard_title, 1, wx.EXPAND)
			root_sizer.Add(header_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

			# Row for News Portal (2) and News Rubric (3) selectors
			selector_sizer = wx.FlexGridSizer(rows=0, cols=4, vgap=8, hgap=10)
			selector_sizer.AddGrowableCol(1, 1)
			selector_sizer.AddGrowableCol(3, 1)

			# 2. News Portal Selection
			self.lbl_site = wx.StaticText(self.panel, label=tr("lbl_site_choice"))
			self.choice_site = wx.Choice(
				self.panel,
				choices=[s.display_label for s in self._sites],
			)
			self.choice_site.SetName(tr("acc_site_choice"))

			# 3. News Rubric Selection
			self.lbl_rubric = wx.StaticText(self.panel, label=tr("lbl_rubric_choice"))
			self.choice_rubric = wx.Choice(self.panel, choices=[])
			self.choice_rubric.SetName(tr("acc_rubric_choice"))

			selector_sizer.Add(self.lbl_site, 0, wx.ALIGN_CENTER_VERTICAL)
			selector_sizer.Add(self.choice_site, 1, wx.EXPAND)
			selector_sizer.Add(self.lbl_rubric, 0, wx.ALIGN_CENTER_VERTICAL)
			selector_sizer.Add(self.choice_rubric, 1, wx.EXPAND)
			root_sizer.Add(selector_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

			# 4. Article Headline Selection
			article_sel_sizer = wx.BoxSizer(wx.HORIZONTAL)
			self.lbl_article = wx.StaticText(self.panel, label=tr("lbl_article_choice"))
			self.choice_article = wx.Choice(self.panel, choices=[tr("no_articles_loaded")])
			self.choice_article.SetName(tr("acc_article_choice"))
			self.choice_article.SetSelection(0)
			article_sel_sizer.Add(self.lbl_article, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
			article_sel_sizer.Add(self.choice_article, 1, wx.EXPAND)
			root_sizer.Add(article_sel_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

			# 5. Loading Status Information
			status_sizer = wx.BoxSizer(wx.HORIZONTAL)
			self.lbl_status = wx.StaticText(self.panel, label=tr("lbl_status"))
			self.txt_status = wx.TextCtrl(
				self.panel,
				value=tr("initial_status_ready"),
				style=wx.TE_READONLY,
			)
			self.txt_status.SetName(tr("acc_status"))
			status_sizer.Add(self.lbl_status, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
			status_sizer.Add(self.txt_status, 1, wx.EXPAND)
			root_sizer.Add(status_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)

			# 6. Full Article Content Area (Multiline Read-Only navigable via standard NVDA reading commands)
			self.lbl_content = wx.StaticText(self.panel, label=tr("lbl_content"))
			root_sizer.Add(self.lbl_content, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

			self.txt_content = wx.TextCtrl(
				self.panel,
				value=tr("initial_content_prompt"),
				style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.HSCROLL,
			)
			self.txt_content.SetName(tr("acc_content"))
			root_sizer.Add(self.txt_content, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 4)

			# Action Button Bar following focus order steps 7 through 12
			btn_bar_sizer = wx.WrapSizer(wx.HORIZONTAL)

			# 7. Previous & Next Article Navigation
			self.btn_prev = wx.Button(self.panel, label=tr("btn_prev_label"))
			self.btn_prev.SetName(tr("acc_btn_prev"))

			self.btn_next = wx.Button(self.panel, label=tr("btn_next_label"))
			self.btn_next.SetName(tr("acc_btn_next"))

			# 8. Refresh Article List Button
			self.btn_refresh_list = wx.Button(self.panel, label=tr("btn_refresh_label"))
			self.btn_refresh_list.SetName(tr("acc_btn_refresh"))

			# 9. Reload Current Article Button
			self.btn_reload_article = wx.Button(self.panel, label=tr("btn_reload_label"))
			self.btn_reload_article.SetName(tr("acc_btn_reload"))

			# 10. Open Original Article in Browser Button
			self.btn_open_browser = wx.Button(self.panel, label=tr("btn_open_browser_label"))
			self.btn_open_browser.SetName(tr("acc_btn_open_browser"))

			# Back to Rubric Selection & Back to Portal Selection Buttons
			self.btn_back_rubric = wx.Button(self.panel, label=tr("btn_back_rubric_label"))
			self.btn_back_rubric.SetName(tr("acc_btn_back_rubric"))

			self.btn_back_site = wx.Button(self.panel, label=tr("btn_back_site_label"))
			self.btn_back_site.SetName(tr("acc_btn_back_site"))

			# 11. Accessibility Settings Button
			self.btn_settings = wx.Button(self.panel, label=tr("btn_settings_label"))
			self.btn_settings.SetName(tr("acc_btn_settings"))

			# 12. Close Dashboard Button
			self.btn_close = wx.Button(self.panel, wx.ID_CLOSE, label=tr("btn_close_label"))
			self.btn_close.SetName(tr("acc_btn_close"))

			for btn in (
				self.btn_prev,
				self.btn_next,
				self.btn_refresh_list,
				self.btn_reload_article,
				self.btn_open_browser,
				self.btn_back_rubric,
				self.btn_back_site,
				self.btn_settings,
				self.btn_close,
			):
				btn_bar_sizer.Add(btn, 0, wx.ALL, 4)

			root_sizer.Add(btn_bar_sizer, 0, wx.EXPAND | wx.ALL, 8)
			self.panel.SetSizer(root_sizer)

			dlg_sizer = wx.BoxSizer(wx.VERTICAL)
			dlg_sizer.Add(self.panel, 1, wx.EXPAND)
			self.SetSizer(dlg_sizer)
			self.SetMinSize(wx.Size(780, 560))
			self.CentreOnScreen()

			# Enforce the exact Tab order from step 1 through step 12
			ordered_controls = [
				self.txt_dashboard_title,
				self.choice_site,
				self.choice_rubric,
				self.choice_article,
				self.txt_status,
				self.txt_content,
				self.btn_prev,
				self.btn_next,
				self.btn_refresh_list,
				self.btn_reload_article,
				self.btn_open_browser,
				self.btn_back_rubric,
				self.btn_back_site,
				self.btn_settings,
				self.btn_close,
			]
			for idx in range(1, len(ordered_controls)):
				ordered_controls[idx].MoveAfterInTabOrder(ordered_controls[idx - 1])

		def _bind_events(self) -> None:
			self.choice_site.Bind(wx.EVT_CHOICE, self._on_site_selected)
			self.choice_rubric.Bind(wx.EVT_CHOICE, self._on_rubric_selected)
			self.choice_article.Bind(wx.EVT_CHOICE, self._on_article_selected)

			self.btn_prev.Bind(wx.EVT_BUTTON, lambda evt: self.navigate_relative_article(-1))
			self.btn_next.Bind(wx.EVT_BUTTON, lambda evt: self.navigate_relative_article(1))
			self.btn_refresh_list.Bind(wx.EVT_BUTTON, lambda evt: self.refresh_current_rubric(force=True))
			self.btn_reload_article.Bind(wx.EVT_BUTTON, lambda evt: self.reload_current_article())
			self.btn_open_browser.Bind(wx.EVT_BUTTON, lambda evt: self.open_current_article_in_browser())
			self.btn_back_rubric.Bind(wx.EVT_BUTTON, lambda evt: self.focus_rubric_selection())
			self.btn_back_site.Bind(wx.EVT_BUTTON, lambda evt: self.focus_site_selection())
			self.btn_settings.Bind(wx.EVT_BUTTON, self._on_open_settings)
			self.btn_close.Bind(wx.EVT_BUTTON, lambda evt: self.close_dashboard())

			self.Bind(wx.EVT_CLOSE, self._on_close_window)
			self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

		def refresh_ui_language(self) -> None:
			"""
			Dynamically update all control labels, accessible names, site/rubric display labels,
			and the currently rendered article when the user switches the interface language.
			"""
			if self._is_closing:
				return

			self.SetTitle(tr("dashboard_window_title"))
			self.SetName(tr("dashboard_window_title"))

			self.lbl_header.SetLabel(tr("lbl_dashboard_header"))
			self.txt_dashboard_title.ChangeValue(tr("dashboard_banner_text"))
			self.txt_dashboard_title.SetName(tr("acc_dashboard_header"))

			self.lbl_site.SetLabel(tr("lbl_site_choice"))
			self.choice_site.SetName(tr("acc_site_choice"))
			site_sel = self.choice_site.GetSelection()
			self.choice_site.Clear()
			for s in self._sites:
				self.choice_site.Append(s.display_label)
			if site_sel != wx.NOT_FOUND and site_sel < len(self._sites):
				self.choice_site.SetSelection(site_sel)

			self.lbl_rubric.SetLabel(tr("lbl_rubric_choice"))
			self.choice_rubric.SetName(tr("acc_rubric_choice"))
			if self._active_site and self._active_site.supported and self._active_rubrics:
				rub_sel = self.choice_rubric.GetSelection()
				self.choice_rubric.Clear()
				for r in self._active_rubrics:
					self.choice_rubric.Append(r.display_label)
				if rub_sel != wx.NOT_FOUND and rub_sel < len(self._active_rubrics):
					self.choice_rubric.SetSelection(rub_sel)
			else:
				self.choice_rubric.Clear()
				self.choice_rubric.Append(tr("no_rubric_unsupported_site"))
				self.choice_rubric.SetSelection(0)

			self.lbl_article.SetLabel(tr("lbl_article_choice"))
			self.choice_article.SetName(tr("acc_article_choice"))

			self.lbl_status.SetLabel(tr("lbl_status"))
			self.txt_status.SetName(tr("acc_status"))

			self.lbl_content.SetLabel(tr("lbl_content"))
			self.txt_content.SetName(tr("acc_content"))

			self.btn_prev.SetLabel(tr("btn_prev_label"))
			self.btn_prev.SetName(tr("acc_btn_prev"))

			self.btn_next.SetLabel(tr("btn_next_label"))
			self.btn_next.SetName(tr("acc_btn_next"))

			self.btn_refresh_list.SetLabel(tr("btn_refresh_label"))
			self.btn_refresh_list.SetName(tr("acc_btn_refresh"))

			self.btn_reload_article.SetLabel(tr("btn_reload_label"))
			self.btn_reload_article.SetName(tr("acc_btn_reload"))

			self.btn_open_browser.SetLabel(tr("btn_open_browser_label"))
			self.btn_open_browser.SetName(tr("acc_btn_open_browser"))

			self.btn_back_rubric.SetLabel(tr("btn_back_rubric_label"))
			self.btn_back_rubric.SetName(tr("acc_btn_back_rubric"))

			self.btn_back_site.SetLabel(tr("btn_back_site_label"))
			self.btn_back_site.SetName(tr("acc_btn_back_site"))

			self.btn_settings.SetLabel(tr("btn_settings_label"))
			self.btn_settings.SetName(tr("acc_btn_settings"))

			self.btn_close.SetLabel(tr("btn_close_label"))
			self.btn_close.SetName(tr("acc_btn_close"))

			if self._current_article is not None:
				self._render_article_to_view(self._current_article, preserve_reading_pos=True)
			elif not self._active_site.supported:
				msg = tr("site_not_supported_msg", site_name=self._active_site.name)
				self.txt_content.ChangeValue(tr("site_not_supported_body", msg=msg))

			self.panel.Layout()
			self.panel.Refresh()

		def _on_external_settings_changed(self) -> None:
			"""Apply language, visual, and timer changes triggered from NVDA Settings or the settings dialog."""
			if self._is_closing:
				return
			self.refresh_ui_language()
			self._apply_visual_preferences()
			self._configure_auto_refresh_timer()

		def _apply_visual_preferences(self) -> None:
			"""
			Apply color theme (Light, Dark, High Contrast), font size (85%-150%),
			and font family (Sans-serif / Serif) without disrupting NVDA reading.
			"""
			theme_key = config_manager.get("color_theme")
			palette = THEME_PALETTES.get(theme_key, THEME_PALETTES["light"])

			font_scale = config_manager.get("font_scale")
			font_family_key = config_manager.get("font_family")

			base_pt = 10
			scaled_pt = max(8, int(round(base_pt * (font_scale / 100.0))))
			heading_pt = max(9, int(round((base_pt + 1) * (font_scale / 100.0))))

			wx_family = wx.FONTFAMILY_ROMAN if font_family_key == "serif" else wx.FONTFAMILY_SWISS
			body_font = wx.Font(
				scaled_pt,
				wx_family,
				wx.FONTSTYLE_NORMAL,
				wx.FONTWEIGHT_NORMAL,
			)
			bold_font = wx.Font(
				heading_pt,
				wx_family,
				wx.FONTSTYLE_NORMAL,
				wx.FONTWEIGHT_BOLD,
			)

			dlg_bg = wx.Colour(*palette["dialog_bg"])
			text_fg = wx.Colour(*palette["text_fg"])
			ctrl_bg = wx.Colour(*palette["control_bg"])
			ctrl_fg = wx.Colour(*palette["control_fg"])
			status_bg = wx.Colour(*palette["status_bg"])
			status_fg = wx.Colour(*palette["status_fg"])

			self.SetBackgroundColour(dlg_bg)
			self.panel.SetBackgroundColour(dlg_bg)

			for lbl in (
				self.lbl_header,
				self.lbl_site,
				self.lbl_rubric,
				self.lbl_article,
				self.lbl_status,
				self.lbl_content,
			):
				lbl.SetForegroundColour(text_fg)
				lbl.SetFont(bold_font)

			self.txt_dashboard_title.SetBackgroundColour(status_bg)
			self.txt_dashboard_title.SetForegroundColour(status_fg)
			self.txt_dashboard_title.SetFont(bold_font)

			self.txt_status.SetBackgroundColour(status_bg)
			self.txt_status.SetForegroundColour(status_fg)
			self.txt_status.SetFont(body_font)

			self.txt_content.SetBackgroundColour(ctrl_bg)
			self.txt_content.SetForegroundColour(ctrl_fg)
			self.txt_content.SetFont(body_font)

			for ctrl in (self.choice_site, self.choice_rubric, self.choice_article):
				ctrl.SetBackgroundColour(ctrl_bg)
				ctrl.SetForegroundColour(ctrl_fg)
				ctrl.SetFont(body_font)

			# Re-render the active article if paragraph spacing changed
			if self._current_article is not None:
				self._render_article_to_view(self._current_article, preserve_reading_pos=True)

			self.panel.Refresh()

		def _configure_auto_refresh_timer(self) -> None:
			"""Configure the background auto-refresh timer according to user preferences."""
			if self._auto_refresh_timer.IsRunning():
				self._auto_refresh_timer.Stop()

			if self._is_closing:
				return

			enabled = bool(config_manager.get("auto_refresh_enabled"))
			interval_sec = int(config_manager.get("auto_refresh_interval_sec") or 60)
			max_articles = int(config_manager.get("max_articles") or 40)
			cache_ttl = int(config_manager.get("cache_ttl_sec") or 180)
			self.article_manager.configure(cache_ttl_sec=cache_ttl, max_articles=max_articles)

			if enabled and self._active_site and self._active_site.supported:
				self._auto_refresh_timer.Start(interval_sec * 1000)

		def _set_status(self, message: str, announce: bool = True) -> None:
			"""Update the status control text and optionally announce it via NVDA."""
			if self._is_closing:
				return
			self.txt_status.SetValue(message)
			if announce:
				announce_nvda(message)

		def _update_navigation_buttons_state(self) -> None:
			"""
			Update the enabled/disabled state of navigation and action buttons.
			Previous and Next buttons remain enabled whenever at least 1 article is loaded
			so pressing them at the first or last boundary announces a clear boundary message.
			"""
			has_articles = len(self._articles) > 0
			has_current = self._current_article is not None
			site_supported = bool(self._active_site and self._active_site.supported)

			self.choice_rubric.Enable(site_supported and len(self._active_rubrics) > 0)
			self.choice_article.Enable(site_supported and has_articles)
			self.btn_prev.Enable(site_supported and has_articles)
			self.btn_next.Enable(site_supported and has_articles)
			self.btn_refresh_list.Enable(site_supported and self._active_rubric is not None)
			self.btn_reload_article.Enable(site_supported and has_current)
			self.btn_open_browser.Enable(has_current and bool(self._current_article.url))

		def _restore_last_context_and_load(self) -> None:
			"""Restore the last selected news portal and rubric when the dashboard opens."""
			last_site_id = config_manager.get("last_site_id")
			site_idx = 0
			for i, s in enumerate(self._sites):
				if s.id == last_site_id:
					site_idx = i
					break

			self.choice_site.SetSelection(site_idx)
			self._active_site = self._sites[site_idx]
			self._populate_rubrics_for_active_site(restore_last_rubric=True)

			# Place initial focus on the news portal selector
			self.choice_site.SetFocus()

		def _populate_rubrics_for_active_site(self, restore_last_rubric: bool = False) -> None:
			"""Populate the rubric list corresponding to the currently selected news portal."""
			self.article_manager.cancel_pending_requests()
			self._articles = []
			self._current_article = None

			if not self._active_site.supported:
				self._active_rubrics = []
				self._active_rubric = None
				self.choice_rubric.Clear()
				self.choice_rubric.Append(tr("no_rubric_unsupported_site"))
				self.choice_rubric.SetSelection(0)

				self.choice_article.Clear()
				self.choice_article.Append(tr("no_article_item"))
				self.choice_article.SetSelection(0)

				msg = tr("site_not_supported_msg", site_name=self._active_site.name)
				self.txt_content.SetValue(tr("site_not_supported_body", msg=msg))
				self._set_status(msg, announce=True)
				self._update_navigation_buttons_state()
				return

			self._active_rubrics = list(self._active_site.rubrics)
			self.choice_rubric.Clear()
			for r in self._active_rubrics:
				self.choice_rubric.Append(r.display_label)

			target_idx = 0
			if restore_last_rubric:
				last_rubric_id = config_manager.get("last_rubric_id")
				for i, r in enumerate(self._active_rubrics):
					if r.id == last_rubric_id:
						target_idx = i
						break

			if self._active_rubrics:
				self.choice_rubric.SetSelection(target_idx)
				self._active_rubric = self._active_rubrics[target_idx]
				config_manager.set("last_rubric_id", self._active_rubric.id)
				self._update_navigation_buttons_state()
				self.refresh_current_rubric(force=False)

		def _on_site_selected(self, event: wx.CommandEvent) -> None:
			sel = self.choice_site.GetSelection()
			if sel == wx.NOT_FOUND or sel >= len(self._sites):
				return
			new_site = self._sites[sel]
			self._active_site = new_site
			config_manager.set("last_site_id", new_site.id)
			self._populate_rubrics_for_active_site(restore_last_rubric=False)
			self._configure_auto_refresh_timer()

		def _on_rubric_selected(self, event: wx.CommandEvent) -> None:
			sel = self.choice_rubric.GetSelection()
			if sel == wx.NOT_FOUND or sel >= len(self._active_rubrics):
				return
			new_rubric = self._active_rubrics[sel]
			if self._active_rubric and self._active_rubric.id == new_rubric.id and self._articles:
				return

			# Clear the previous rubric's article list so articles from different rubrics never mix
			self._active_rubric = new_rubric
			config_manager.set("last_rubric_id", new_rubric.id)
			self._articles = []
			self._current_article = None
			self.choice_article.Clear()
			self.choice_article.Append(tr("loading_rubric_choice_item", rubric_name=new_rubric.name))
			self.choice_article.SetSelection(0)
			self.txt_content.SetValue(
				tr("loading_rubric_body", rubric_name=new_rubric.name, site_name=self._active_site.name)
			)
			self._update_navigation_buttons_state()
			self.refresh_current_rubric(force=False)

		def refresh_current_rubric(self, force: bool = False, is_background_auto: bool = False) -> None:
			"""
			Fetch the latest article list for the active rubric.
			When `force=False` and valid cached headlines exist, reuses the session cache.
			"""
			if self._is_closing or not self._active_site or not self._active_site.supported or not self._active_rubric:
				return

			rubric = self._active_rubric
			site = self._active_site

			if not is_background_auto:
				self._set_status(tr("status_fetching_rubric", rubric_name=rubric.name), announce=True)

			def _on_success(articles: List[Article], bg_auto: bool) -> None:
				if self._is_closing:
					return
				wx.CallAfter(self._handle_rubric_loaded_on_gui, site.id, rubric.id, articles, bg_auto)

			def _on_error(error_msg: str, bg_auto: bool) -> None:
				if self._is_closing:
					return
				wx.CallAfter(self._handle_rubric_error_on_gui, site.id, rubric.id, error_msg, bg_auto)

			self.article_manager.fetch_rubric_articles_async(
				site=site,
				rubric=rubric,
				force_refresh=force,
				is_background_auto=is_background_auto,
				on_success=_on_success,
				on_error=_on_error,
			)

		def _handle_rubric_loaded_on_gui(
			self,
			site_id: str,
			rubric_id: str,
			new_articles: List[Article],
			is_background_auto: bool,
		) -> None:
			"""
			Update the article headline list on the GUI thread without stealing focus
			or interrupting the user's active article reading session.
			"""
			if self._is_closing or not self._active_site or not self._active_rubric:
				return
			if self._active_site.id != site_id or self._active_rubric.id != rubric_id:
				return

			previous_article = self._current_article
			merged_list = list(new_articles)

			# If the user is actively reading an article that dropped off the latest list during a background refresh,
			# retain that article in the session list so active reading is never disrupted.
			if previous_article is not None and previous_article.rubric_id == rubric_id:
				if not any(a.canonical_url == previous_article.canonical_url for a in merged_list):
					merged_list.insert(0, previous_article)

			self._articles = merged_list
			self.choice_article.Clear()
			for idx, art in enumerate(self._articles, start=1):
				self.choice_article.Append(f"{idx}. {art.title}")

			# Determine the selected article index
			selected_idx = 0
			if previous_article is not None:
				for i, art in enumerate(self._articles):
					if art.canonical_url == previous_article.canonical_url:
						selected_idx = i
						break

			if self._articles:
				self.choice_article.SetSelection(selected_idx)
				target_article = self._articles[selected_idx]
			else:
				target_article = None

			self._update_navigation_buttons_state()

			if is_background_auto:
				# Background auto-refresh must not steal focus or replace the currently read article
				self._set_status(
					tr(
						"status_auto_refreshed",
						rubric_name=self._active_rubric.name,
						count=len(self._articles),
					),
					announce=False,
				)
				return

			self._set_status(
				tr(
					"status_rubric_loaded",
					count=len(self._articles),
					rubric_name=self._active_rubric.name,
				),
				announce=True,
			)

			# If no article was previously open in this rubric, load the first article without moving focus
			if target_article is not None and (
				previous_article is None or previous_article.canonical_url != target_article.canonical_url
			):
				self._select_and_load_article(selected_idx, announce_selection=False, force_reload=False)

		def _handle_rubric_error_on_gui(
			self,
			site_id: str,
			rubric_id: str,
			error_msg: str,
			is_background_auto: bool,
		) -> None:
			"""
			Handle rubric loading errors informatively.
			Never discards a previously loaded article list if a subsequent refresh fails.
			"""
			if self._is_closing or not self._active_site or not self._active_rubric:
				return
			if self._active_site.id != site_id or self._active_rubric.id != rubric_id:
				return

			if is_background_auto and self._articles:
				return

			if self._articles:
				msg = tr("status_rubric_error_with_cached", error_msg=error_msg, count=len(self._articles))
				self._set_status(msg, announce=True)
			else:
				self.choice_article.Clear()
				self.choice_article.Append(tr("choice_rubric_load_failed"))
				self.choice_article.SetSelection(0)
				self.txt_content.SetValue(tr("body_rubric_load_failed", error_msg=error_msg))
				self._set_status(error_msg, announce=True)
			self._update_navigation_buttons_state()

		def _on_article_selected(self, event: wx.CommandEvent) -> None:
			sel = self.choice_article.GetSelection()
			if sel == wx.NOT_FOUND or sel >= len(self._articles):
				return
			self._select_and_load_article(sel, announce_selection=True, force_reload=False)

		def _select_and_load_article(
			self,
			index: int,
			announce_selection: bool = True,
			force_reload: bool = False,
		) -> None:
			"""Select the article at `index` and fetch its full content in the background if needed."""
			if index < 0 or index >= len(self._articles):
				return

			self.choice_article.SetSelection(index)
			article = self._articles[index]
			self._current_article = article
			self._update_navigation_buttons_state()

			rubric_name = self._active_rubric.name if self._active_rubric else ""

			# If full content is already cached and force_reload is False, render immediately
			if not force_reload and article.content_status in (
				ArticleStatus.CONTENT_LOADED,
				ArticleStatus.CONTENT_PARTIAL,
			) and article.content:
				self._render_article_to_view(article, preserve_reading_pos=False)
				if announce_selection:
					ann = format_article_selection_announcement(
						article, index, len(self._articles), rubric_name=rubric_name
					)
					self._set_status(ann, announce=True)
				return

			# Explicitly display loading status while full content is fetched in the background
			article.content_status = ArticleStatus.CONTENT_LOADING
			self._render_article_to_view(article, preserve_reading_pos=False)
			if announce_selection:
				self._set_status(
					tr("status_article_selected_loading", title=article.title),
					announce=True,
				)
			else:
				self._set_status(
					tr("status_rubric_loaded_loading_first", count=len(self._articles)),
					announce=False,
				)

			site = self._active_site

			def _on_content_success(updated_article: Article) -> None:
				if self._is_closing:
					return
				wx.CallAfter(self._handle_article_loaded_on_gui, updated_article, index)

			def _on_content_error(failed_article: Article, err_msg: str) -> None:
				if self._is_closing:
					return
				wx.CallAfter(self._handle_article_error_on_gui, failed_article, err_msg)

			self.article_manager.fetch_article_content_async(
				site=site,
				article=article,
				force_reload=force_reload,
				on_success=_on_content_success,
				on_error=_on_content_error,
			)

		def _handle_article_loaded_on_gui(self, article: Article, index: int) -> None:
			"""Render the loaded article content on the GUI thread without moving focus."""
			if self._is_closing or self._current_article is None:
				return
			if self._current_article.id != article.id:
				return

			self._render_article_to_view(article, preserve_reading_pos=False)
			self._update_navigation_buttons_state()

			rubric_name = self._active_rubric.name if self._active_rubric else ""
			selection_summary = format_article_selection_announcement(
				article, index, len(self._articles), rubric_name=rubric_name
			)
			if article.content_status == ArticleStatus.CONTENT_PARTIAL:
				self._set_status(
					tr("status_article_loaded_partial", summary=selection_summary),
					announce=True,
				)
			else:
				self._set_status(
					tr("status_article_loaded_full", summary=selection_summary),
					announce=True,
				)

		def _handle_article_error_on_gui(self, article: Article, err_msg: str) -> None:
			if self._is_closing or self._current_article is None:
				return
			if self._current_article.id != article.id:
				return

			self._render_article_to_view(article, preserve_reading_pos=False)
			self._update_navigation_buttons_state()
			if article.content_status == ArticleStatus.CONTENT_PARTIAL:
				self._set_status(
					tr("status_article_loaded_partial_err", error_msg=err_msg),
					announce=True,
				)
			else:
				self._set_status(err_msg, announce=True)

		def _render_article_to_view(self, article: Article, preserve_reading_pos: bool = False) -> None:
			"""
			Write formatted article text into `txt_content` while preserving the user's
			reading cursor position when requested (such as during theme, spacing, or language changes).
			"""
			rubric_name = self._active_rubric.name if self._active_rubric else ""
			spacing = config_manager.get("paragraph_spacing")
			formatted_text = format_article_for_reading(
				article=article,
				rubric_name=rubric_name,
				paragraph_spacing=spacing,
			)

			saved_insertion = 0
			if preserve_reading_pos:
				try:
					saved_insertion = self.txt_content.GetInsertionPoint()
				except Exception:
					saved_insertion = 0

			self.txt_content.ChangeValue(formatted_text)
			if preserve_reading_pos and saved_insertion > 0:
				max_pos = max(0, self.txt_content.GetLastPosition())
				self.txt_content.SetInsertionPoint(min(saved_insertion, max_pos))
			else:
				self.txt_content.SetInsertionPoint(0)

		def navigate_relative_article(self, delta: int) -> None:
			"""
			Navigate to the previous (`delta=-1`) or next (`delta=+1`) article in the active rubric
			while preventing out-of-bounds indices.
			"""
			if not self._articles:
				announce_nvda(tr("nav_no_articles"))
				return

			current_idx = self.choice_article.GetSelection()
			if current_idx == wx.NOT_FOUND:
				current_idx = 0

			target_idx = current_idx + delta
			if target_idx < 0:
				announce_nvda(tr("nav_at_first_article"))
				return
			if target_idx >= len(self._articles):
				announce_nvda(tr("nav_at_last_article"))
				return

			self._select_and_load_article(target_idx, announce_selection=True, force_reload=False)

		def reload_current_article(self) -> None:
			"""Reload the currently selected article's full content from the source page."""
			if not self._articles or self._current_article is None:
				announce_nvda(tr("nav_select_article_first"))
				return
			idx = self.choice_article.GetSelection()
			if idx == wx.NOT_FOUND:
				idx = 0
			self._select_and_load_article(idx, announce_selection=True, force_reload=True)

		def focus_rubric_selection(self) -> None:
			"""Move keyboard focus back to the rubric selection control."""
			if self.choice_rubric.IsEnabled():
				self.choice_rubric.SetFocus()
				announce_nvda(tr("nav_back_to_rubric"))
			else:
				self.choice_site.SetFocus()
				announce_nvda(tr("nav_rubric_unavailable_focus_site"))

		def focus_site_selection(self) -> None:
			"""Move keyboard focus back to the news portal selection control."""
			self.choice_site.SetFocus()
			announce_nvda(tr("nav_back_to_site"))

		def open_current_article_in_browser(self) -> None:
			"""Open the original article URL in the user's default web browser."""
			if self._current_article is None or not self._current_article.url:
				announce_nvda(tr("nav_no_article_url"))
				return
			try:
				announce_nvda(tr("nav_opening_browser", title=self._current_article.title))
				webbrowser.open(self._current_article.url, new=2)
			except Exception:
				self._set_status(tr("nav_open_browser_failed"), announce=True)

		def _on_open_settings(self, event: wx.CommandEvent) -> None:
			dlg = AccessibilitySettingsDialog(self)
			if dlg.ShowModal() == wx.ID_OK:
				self.refresh_ui_language()
				self._apply_visual_preferences()
				self._configure_auto_refresh_timer()
				announce_nvda(tr("settings_saved_announcement"))
			dlg.Destroy()

		def _on_auto_refresh_timer(self, event: wx.TimerEvent) -> None:
			"""Handle periodic background headline auto-refresh timer ticks."""
			if self._is_closing or not self.IsShown():
				return
			if not bool(config_manager.get("auto_refresh_enabled")):
				return
			if self._active_site and self._active_site.supported and self._active_rubric:
				self.refresh_current_rubric(force=True, is_background_auto=True)

		def _on_char_hook(self, event: wx.KeyEvent) -> None:
			"""
			Handle dashboard keyboard shortcuts:
			- Alt+[  : Previous article
			- Alt+]  : Next article
			- F5     : Refresh article list
			- Ctrl+R : Reload selected article content
			- Esc    : Step back to the previous selection stage or close the dashboard
			"""
			key_code = event.GetKeyCode()
			alt_down = event.AltDown()
			ctrl_down = event.ControlDown()
			shift_down = event.ShiftDown()

			# Alt+[ (ASCII 91 '[') -> Previous Article
			if alt_down and not ctrl_down and not shift_down and key_code == ord("["):
				self.navigate_relative_article(-1)
				return

			# Alt+] (ASCII 93 ']') -> Next Article
			if alt_down and not ctrl_down and not shift_down and key_code == ord("]"):
				self.navigate_relative_article(1)
				return

			# F5 -> Refresh article list
			if key_code == wx.WXK_F5 and not alt_down and not ctrl_down:
				self.refresh_current_rubric(force=True, is_background_auto=False)
				return

			# Ctrl+R -> Reload selected article content
			if ctrl_down and not alt_down and not shift_down and key_code in (ord("R"), ord("r")):
				self.reload_current_article()
				return

			# Esc -> Contextually step back to the previous stage or close the dialog
			if key_code == wx.WXK_ESCAPE and not alt_down and not ctrl_down and not shift_down:
				focused = wx.Window.FindFocus()
				if focused == self.txt_content:
					self.choice_article.SetFocus()
					announce_nvda(tr("nav_back_to_article"))
					return
				if focused == self.choice_article:
					self.choice_rubric.SetFocus()
					announce_nvda(tr("nav_back_to_rubric"))
					return
				if focused == self.choice_rubric:
					self.choice_site.SetFocus()
					announce_nvda(tr("nav_back_to_site"))
					return
				self.close_dashboard()
				return

			event.Skip()

		def close_dashboard(self) -> None:
			"""Close the dashboard cleanly, stopping the timer and cancelling pending callbacks."""
			if self._is_closing:
				return
			self._is_closing = True
			unregister_settings_change_listener(self._on_external_settings_changed)
			if self._auto_refresh_timer.IsRunning():
				self._auto_refresh_timer.Stop()
			self.article_manager.cancel_pending_requests()
			self.Destroy()

		def _on_close_window(self, event: wx.CloseEvent) -> None:
			self.close_dashboard()
else:
	AccessibilitySettingsDialog = None
	NewsHubDashboardDialog = None
