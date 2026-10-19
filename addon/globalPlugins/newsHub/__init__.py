# -*- coding: utf-8 -*-
"""
Main GlobalPlugin entry point for the NewsHub for NVDA add-on.

Provides:
- Global shortcut `NVDA+Shift+K` to open the multi-site news reader dashboard.
- NVDA Settings panel integration under `NVDA -> Preferences -> Settings -> NewsHub for NVDA`
  (plus a direct item in `NVDA -> Preferences -> NewsHub for NVDA Settings...`).
- Menu item under `NVDA -> Tools -> NewsHub for NVDA...`.
- Clean lifecycle termination (`terminate()`) with no timer, menu, or thread leaks.
"""

try:
	import globalPluginHandler
	_BaseGlobalPlugin = globalPluginHandler.GlobalPlugin
except ImportError:
	globalPluginHandler = None
	class _BaseGlobalPlugin(object):
		def terminate(self):
			pass

try:
	import scriptHandler
	_script_decorator = scriptHandler.script
except ImportError:
	scriptHandler = None
	def _script_decorator(**kwargs):
		def _wrap(func):
			func._script_meta = kwargs
			return func
		return _wrap

try:
	import addonHandler
	addonHandler.initTranslation()
except Exception:
	def _(s: str) -> str:
		return s

try:
	import gui
	from gui.settingsDialogs import NVDASettingsDialog
	import wx
except ImportError:
	gui = None
	NVDASettingsDialog = None
	wx = None

from .article_manager import ArticleManager
from .config_manager import config_manager
from .dialogs import (
	AccessibilitySettingsDialog,
	NewsHubDashboardDialog,
	NewsHubSettingsPanel,
	announce_nvda,
	register_settings_change_listener,
	unregister_settings_change_listener,
)


class GlobalPlugin(_BaseGlobalPlugin):
	"""GlobalPlugin for NewsHub for NVDA (Multi-site News Reader with Kompas.com, Detik.com, CNN Indonesia, CNBC Indonesia, and Tempo.co support)."""
	scriptCategory = "NewsHub for NVDA"

	def __init__(self):
		super().__init__()
		config_manager.init_config()
		self.article_manager = ArticleManager(
			cache_ttl_sec=config_manager.get("cache_ttl_sec"),
			max_articles=config_manager.get("max_articles"),
		)
		self._dashboard_dlg = None
		self._tools_menu_item = None
		self._prefs_menu_item = None
		self._register_settings_panel()
		self._register_menus()
		register_settings_change_listener(self._on_settings_saved)

	def _register_settings_panel(self) -> None:
		"""Register NewsHubSettingsPanel in NVDA Preferences -> Settings category list."""
		if NVDASettingsDialog is None or NewsHubSettingsPanel is None:
			return
		try:
			if NewsHubSettingsPanel not in NVDASettingsDialog.categoryClasses:
				NVDASettingsDialog.categoryClasses.append(NewsHubSettingsPanel)
		except Exception:
			pass

	def _unregister_settings_panel(self) -> None:
		"""Remove NewsHubSettingsPanel from NVDA Preferences -> Settings category list."""
		if NVDASettingsDialog is None or NewsHubSettingsPanel is None:
			return
		try:
			if NewsHubSettingsPanel in NVDASettingsDialog.categoryClasses:
				NVDASettingsDialog.categoryClasses.remove(NewsHubSettingsPanel)
		except Exception:
			pass

	def _register_menus(self) -> None:
		"""Register NewsHub for NVDA items in both the NVDA Tools and Preferences menus."""
		if gui is None or wx is None:
			return
		try:
			tools_menu = gui.mainFrame.sysTrayIcon.toolsMenu
			self._tools_menu_item = tools_menu.Append(
				wx.ID_ANY,
				_('&NewsHub for NVDA (News Reader)...'),
				_('Open the NewsHub for NVDA multi-site news reader dashboard'),
			)
			gui.mainFrame.sysTrayIcon.Bind(
				wx.EVT_MENU,
				self._on_menu_open_dashboard,
				self._tools_menu_item,
			)
		except Exception:
			self._tools_menu_item = None

		try:
			prefs_menu = gui.mainFrame.sysTrayIcon.preferencesMenu
			self._prefs_menu_item = prefs_menu.Append(
				wx.ID_ANY,
				_('&NewsHub for NVDA Settings...'),
				_('Configure language and display preferences for NewsHub for NVDA'),
			)
			gui.mainFrame.sysTrayIcon.Bind(
				wx.EVT_MENU,
				self._on_menu_open_settings,
				self._prefs_menu_item,
			)
		except Exception:
			self._prefs_menu_item = None

	def _on_settings_saved(self) -> None:
		"""Update menu item labels dynamically when the user changes the interface language."""
		try:
			if self._tools_menu_item is not None:
				self._tools_menu_item.SetItemLabel(_('&NewsHub for NVDA (News Reader)...'))
				self._tools_menu_item.SetHelp(_('Open the NewsHub for NVDA multi-site news reader dashboard'))
			if self._prefs_menu_item is not None:
				self._prefs_menu_item.SetItemLabel(_('&NewsHub for NVDA Settings...'))
				self._prefs_menu_item.SetHelp(_('Configure language and display preferences for NewsHub for NVDA'))
		except Exception:
			pass

	def _on_menu_open_dashboard(self, event) -> None:
		self._open_dashboard()

	def _on_menu_open_settings(self, event) -> None:
		"""Open the NewsHub for NVDA category inside NVDA Settings, or fallback to the standalone dialog."""
		if gui is None or wx is None:
			return

		def _show_settings():
			try:
				if (
					NVDASettingsDialog is not None
					and NewsHubSettingsPanel is not None
					and hasattr(gui.mainFrame, "_popupSettingsDialog")
				):
					gui.mainFrame._popupSettingsDialog(NVDASettingsDialog, NewsHubSettingsPanel)
					return
			except Exception:
				pass

			try:
				gui.mainFrame.prePopup()
				dlg = AccessibilitySettingsDialog(gui.mainFrame)
				if dlg.ShowModal() == wx.ID_OK:
					announce_nvda(_('NewsHub for NVDA settings have been saved and applied.'))
				dlg.Destroy()
				gui.mainFrame.postPopup()
			except Exception:
				pass

		wx.CallAfter(_show_settings)

	def _open_dashboard(self) -> None:
		"""Open or raise the NewsHub for NVDA dashboard window on the GUI thread."""
		if gui is None or wx is None or NewsHubDashboardDialog is None:
			return

		def _show():
			try:
				if self._dashboard_dlg is not None and not self._dashboard_dlg._is_closing:
					if self._dashboard_dlg.IsIconized():
						self._dashboard_dlg.Iconize(False)
					self._dashboard_dlg.Raise()
					self._dashboard_dlg.SetFocus()
					announce_nvda(_('NewsHub for NVDA dashboard is active.'))
					return

				gui.mainFrame.prePopup()
				self._dashboard_dlg = NewsHubDashboardDialog(
					parent=gui.mainFrame,
					article_manager=self.article_manager,
				)
				self._dashboard_dlg.Show()
				self._dashboard_dlg.Raise()
				gui.mainFrame.postPopup()
			except Exception as e:
				try:
					from logHandler import log
					log.error(f"NewsHub: Failed to open dashboard: {e}")
				except Exception:
					pass

		wx.CallAfter(_show)

	@_script_decorator(
		description=_("Open the NewsHub for NVDA dashboard (Multi-site News Reader)"),
		category="NewsHub for NVDA",
		gesture="kb:NVDA+shift+k",
	)
	def script_openNewsHubDashboard(self, gesture) -> None:
		"""Open the main NewsHub for NVDA dashboard when NVDA+Shift+K is pressed."""
		self._open_dashboard()

	def terminate(self) -> None:
		"""
		Stop all timers, cancel background workers, destroy open dialogs, unregister the
		NVDA Settings panel, and remove menu items when NVDA exits or the add-on is disabled.
		"""
		unregister_settings_change_listener(self._on_settings_saved)
		self._unregister_settings_panel()

		try:
			self.article_manager.shutdown()
		except Exception:
			pass

		try:
			if self._dashboard_dlg is not None:
				self._dashboard_dlg.close_dashboard()
				self._dashboard_dlg = None
		except Exception:
			pass

		try:
			if self._tools_menu_item is not None and gui is not None:
				tools_menu = gui.mainFrame.sysTrayIcon.toolsMenu
				tools_menu.Remove(self._tools_menu_item.GetId())
				self._tools_menu_item.Destroy()
				self._tools_menu_item = None
		except Exception:
			pass

		try:
			if self._prefs_menu_item is not None and gui is not None:
				prefs_menu = gui.mainFrame.sysTrayIcon.preferencesMenu
				prefs_menu.Remove(self._prefs_menu_item.GetId())
				self._prefs_menu_item.Destroy()
				self._prefs_menu_item = None
		except Exception:
			pass

		super().terminate()
