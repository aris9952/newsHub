 NewsHub for NVDA

 Author: Aris Yohanes Elean, S.Kom
 Version: 1.3.0
 Minimum NVDA Version: 2022.1.0
 Last Tested NVDA Version: 2026.1.0
 License: GNU General Public License v2 (GPL v2)

Reading news from various national and international news portals such as Kompas.com, Detik.com, CNN Indonesia, CNBC Indonesia, Tempo.co, and other news portals ar truly enjoyable. Aside from providing reliable information, it also broadens our knowledge as readers.

However, as we know, the web pages of these news portals are often not friendly to screen readers. There are many advertisements, pop-up banners, and complex navigation elements that make reading difficult.

That is why NewsHub for NVDA is here!

With this add-on, you can read news from 5 trusted Indonesian news portals (76 official rubrics) easily and comfortably:
1. Kompas.com (23 rubrics)
2. Detik.com (27 rubrics)
3. CNN Indonesia (8 rubrics)
4. CNBC Indonesia (7 rubrics)
5. Tempo.co (11 rubrics)

---

 Key Features in Version 1.3.0

 Native NVDA HTML Browse Mode (`Enter` / `Alt+H`): Uses NVDA's official `ui.browseableMessage(..., isHtml=True)` virtual buffer so you can read full news articles with standard NVDA Browse Mode single-letter navigation:
   `H` / `1`–`3`: Jump between article title and section subheadings.
   `G`: Jump to inline article photos (`<figure><img alt="..."><figcaption>`) and read image descriptions/captions.
   `K`: Jump to inline video links (`YouTube`, `20Detik`, `CNN Indonesia TV`, `CNBC Indonesia TV`, `Kompas TV`) and original source links.
   `T` and `Ctrl+Alt+Arrow Keys`: Navigate news data tables with full column/row header announcements.
   `L` / `I`: Navigate bulleted and numbered lists.
   `Q`: Jump to blockquotes.
   `Escape`: Close the HTML Browse Mode view and return directly to the NewsHub dashboard.
 Cross-Portal Keyword Search (`Ctrl+F`): Search for any news topic across all 5 portals (`Kompas.com`, `Detik.com`, `CNN Indonesia`, `CNBC Indonesia`, and `Tempo.co`) simultaneously. While search results are displayed, the portal and rubric selectors are automatically hidden for a cleaner workflow; press `Escape` to clear search results and return to the default rubric view.
 Conflict-Free In-Dialog Reading Area: Keeps the dashboard reading area as a responsive `wx.TextCtrl` (`TE_MULTILINE | TE_READONLY | TE_RICH2`) so `Tab` / `Shift+Tab`, `Up` / `Down Arrow`, `Alt+[`, `Alt+]`, and `Escape` work smoothly without any focus traps.
 Bundled SSL Certificate Store & Anti-403 Resilience: Includes Mozilla's CA bundle (`certs/cacert.pem`), automatic SSL fallback, session cookie persistence, and Windows Schannel `curl.exe` / RSS syndication fallback.
 Bilingual Interface (English & Indonesian): Automatically adapts to NVDA's language setting (`en` and `id`) via official NVDA `addonHandler.initTranslation()` gettext catalogs.

---

 Keyboard Shortcuts

| Shortcut | Action |
| `NVDA+Shift+K` | Open the NewsHub for NVDA dashboard from anywhere |
| `Tab` / `Shift+Tab` | Move between controls in the dashboard |
| `Up` / `Down Arrow` | Select a news portal, rubric, or article headline, or read text line by line |
| `Enter` / `Alt+H` | Open the current article in HTML Browse Mode (with headings, photos, videos, tables, and links) |
| `Ctrl+F` | Focus the cross-portal Search News keyword box |
| `Alt+[` | Navigate to the previous article in the active list |
| `Alt+]` | Navigate to the next article in the active list |
| `F5` | Refresh the article list for the active rubric (or re-run active search) |
| `Ctrl+R` | Reload the full content of the currently selected article |
| `Alt+R` | Return focus to the rubric selection control |
| `Alt+S` | Return focus to the news portal selection control |
| `Escape` | Clear active search results, step back to the previous selection stage, or close the dashboard |

---

 Building From Source (NVDA AddonTemplate)

To build the `.nvda-addon` package from this repository using SCons:

```bash
scons
```

To generate the translation template (`.pot`):

```bash
scons pot
```
