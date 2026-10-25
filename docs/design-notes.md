# Nobu Notes: design summary (v4.9, Oct 22 2026)

> **STANDING INSTRUCTION FROM THE USER (applies after every new feature):** "re write the tutorial, make it explain every single feature in nobu in the easiest possible way to understand. in this context easy to understand means minimal fluff or filler words, and minimum technical jargon the average person might not understand. we want it as concise and informative as possible." In practice: after any feature change, update `app/nobu_help.py` `SECTIONS` (and README "what's new") so every feature is covered, short and plain.
> Other standing rules: deliver changes to the personal copy (`C:\Users\orion\Desktop\Nobu Notes`) only; update the share folder/zip only when asked.

**What it is:** A fully offline Windows tray app. Say "No boo, record this" to start dictating. Recording ends after 8 s of real silence (with an on-screen countdown) or on "No boo, end recording". The audio is saved as a WAV, and each transcript becomes its own note in **Unassigned**. The user files notes into project folders (books and campaigns) from the app. Since v4 it is also a Word-style writing app with export to Word, PDF, e-book and web formats.

**In-note voice commands (v3):** These work only while a note is open and Nobu's window has focus (`engine.note_open`).
- **"No boo, edit this":** dictation goes in at the cursor, or replaces the selected text.
- **"No boo, cut this":** the user recites a passage. Nobu fuzzy-matches it in the note (word-level SequenceMatcher anchors, then a window search), highlights it in red, and asks Delete / Cancel. Ctrl+Z undoes the cut.
- The same actions are available as toolbar buttons ("Dictate here", "Cut by voice") and on the note's right-click menu.

**Pronunciation dictionary (v3):**
- The list is global and stored in `dictionary.json` as `{word, sounds[]}`.
- The user types a spelling and records 2–3 samples. Engine "capture" mode saves the next utterance, and the transcriber's `_sample` job transcribes it with and without a hint prompt.
- Each sound-alike it hears is learned, except common words, which are skipped.
- Transcripts, dictations and cuts get those sound-alikes replaced, plus a fuzzy pass for capitalised words (ratio ≥ 0.86).
- The dictionary words are also passed to the model as `initial_prompt`. Since v4, spell check never flags them.
- v3.1 adds a "New word" box with a button at the top of the window, plus right-click and double-click on the list.

**Trash (v3):**
- Each deletion becomes a bundle, `Notes\.trash\<stamp> <name>\{item\, audio\, info.json}`. Linked .wav and .txt files go into the bundle too.
- Restore puts everything back where it was. Delete permanently uses `SHFileOperationW` with FOF_ALLOWUNDO, so items land in the Windows Recycle Bin.
- Trash appears in the sidebar. The inbox, project and trash lists have right-click menus and support multi-select.

**Layout (folder: Desktop\Nobu Notes):**
- NobuNotes.exe is a Go launcher; the source is in app\*.py.
- setup\runtime.zip.00N holds the bundled Python 3.11 runtime, unpacked to runtime\.
- Notes\Unassigned\ is the inbox, Notes\<Project>\ holds project notes, Notes\.trash\ holds deleted bundles and Notes\.backups\ holds one backup per note.
- Recordings\ holds all audio as a flat list plus a .txt per recording.
- logs\ includes commands\, samples\ and heard\.

**Audio pipeline:**
- Gain, then a 60–120 Hz high-pass, then adaptive spectral noise reduction with an intensity slider.
- Then the Silero neural VAD behind an energy gate.
- Total load is about 0.5% of one core.

**Commands:** Speech bursts go to `base.en` with word timestamps, and `match_command` returns record, edit or cut. Transcription uses `medium.en` int8.

**UI sizing rule (v3.1 lesson):** The user runs Windows display scaling above 100%. Tk scales fonts, but fixed pixel window sizes do not scale.
- In v3, the Teach, Dictionary and Word windows cut off their bottom buttons (Start, Add word, Save, Record). Teach therefore never started, and the phrases fell through to normal recording.
- Fix: `T.toplevel` scales sizes by `winfo_fpixels('1i')/96`, and `T.fit(win)` grows the window to its content (clamped to the screen).
- Bottom button rows are packed first, with `side="bottom"` and `before=`.
- Every new dialog must follow this rule.

**History:**
- v1: an energy VAD with sensitivity too low missed the user's speech (Blue Snowball mic, steady fan noise).
- v2: added noise reduction, the neural VAD and the dark UI with projects. The wake and stop phrases were confirmed working live.
- v2 bug: in Settings, the teach button destroyed the window before reading its widgets.
- v3: added edit/cut commands, the dictionary and Trash.
- v3.1: DPI-safe dialogs.
- Computer-use screenshots can't target the app, because pythonw.exe isn't an installed app. Diagnose from logs instead.

**User preferences:**
- Assigning a transcript makes it its own note in the folder.
- Room noise is a steady fan/AC hum, and the cleaned audio is what gets saved.
- Audio stays in one Recordings folder, and deleting a transcript sends its audio to Trash with it.
- "Edit this" dictation goes in at the cursor, and "cut this" asks for confirmation.
- The dictionary is one global list.

**v3.2–v3.3 (fonts & folders):** Sub-folders at any depth inside projects. Fonts are IM Fell English for note text, Varnyx (the user's own demo font) for headings, and Grenze for the interface. Varnyx's demo licence is personal-use only, so it is loaded from `Nobu Notes\fonts\` and never embedded in Word, e-book or web exports.

**v4.0: writing app (Oct 21 2026)**
- **Document model (`nobu_rich.py`):**
  - Notes stay as `.nobu` JSON items, but tags are now Word-like.
  - Character tags: `b i u s sup sub meta`, plus `ff:`, `fs:`, `fg:` and `hl:`.
  - Paragraph tags: `st:` (normal/title/subtitle/h1/h2/h3/quote), `al:`, `ls:`, `sb:`, `sa:`, `ind:`, `fi:`, `li:kind:level`.
  - List markers are text tagged `lm`. Tables are `{"table":{rows}}` and page breaks are `{"pb":1}`.
  - Legacy `h1`, `h2` and `center` tags are upgraded on load.
  - `items_to_paras` and `paras_to_items` convert to and from block form, which every exporter and importer uses.
- **Editor (`nobu_editor.py`):**
  - Page geometry: an 8.5" page with 1" side margins (scaled by DPI × zoom). The top and bottom margins are `docstart`/`docend` spacing tags, not Text padding.
  - Display: composite `F|fam|size|b|i|vpos` and `P|...` tags are rebuilt by `_restyle`.
  - Undo is snapshot-based (serialize/restore) and covers formatting.
  - The ribbon is groups laid out with a wrapping flow layout.
  - Pagination: page marks come from `count -update -ypixels` with a binary search. Page labels appear in the side gutters, and a "Page X of N" bar has clickable page buttons.
  - Tables are embedded frames of Text cells, and page breaks are embedded frames.
  - Spell check uses pyspellchecker with a red `underlinefg`. The thesaurus is the WordNet MyThes file `app\data\thesaurus_en.dat.gz`.
  - Rich clipboard: CF_HTML + RTF on copy, and HTML paste through `html_to_paras`.
- **Export (`nobu_export.py`, popup in `nobu_share.py`):** the popup offers all four formats every time.
  - DOCX via python-docx: real Word styles, numbering definitions, fonts embedded as obfuscated `.odttf`. It passes OOXML validation.
  - PDF via reportlab: TTFs come from `nobu_fonts.font_file`, with glyph fallback fonts. Synthetic bold is done with a patched text render mode.
  - EPUB3 embeds OFL fonts only.
  - HTML is self-contained; TXT is also offered.
- **Import (`nobu_importers.py`):**
  - Formats: docx (styles, runs, effective fonts via theme, lists, tables, images), odt, pdf (text only), html, md, rtf, txt.
  - The user chooses between keeping the document's fonts and switching to their Nobu fonts.
- **Fonts:**
  - 64 OFL families are kept in `app\fonts\lib` with a `fonts.json` category index.
  - At startup they load privately, and they are also installed per-user into Windows (HKCU, `Nobu_` file prefix) so Word has them.
  - A font browser groups them by category.
- **Packaging:**
  - New Python packages (python-docx, reportlab, pyspellchecker, fontTools, pypdf, striprtf, lxml) ship as `setup\addons-v4.zip`. The font library ships as `setup\fontlib-v4.zip`.
  - `nobu_main._unpack_addons` extracts both on first start, with marker files.
- **Voice hints:** Every control that also has a voice command shows the phrase in brackets, e.g. "Dictate here (No boo, edit this)", "Cut by voice (No boo, cut this)", "Record (No boo, record this)" / "(No boo, end recording)".
- **User choices for v4:**
  - Word page width, with text flowing onto new pages and a clickable page navigator.
  - Install fonts into Windows.
  - Show all four export formats every time.
  - Spell check, tables and thesaurus.
  - All font categories.
  - New-note Normal style is IM Fell English 14 pt with Word spacing.

**v4.1 (Oct 21 2026):**
- The page is centred: the gutters expand equally on both sides.
- Mouse wheel beside the page zooms (30–300%), and the wheel on the page scrolls.
- Default text size is 12 pt.
- On-screen phrases are spelled "Nobu, …", with a tip on the Home screen that it's said "no-boo". Wake-word matching is unchanged.
- NobuNotes.exe has an icon (quill, book and voice waves, built via llvm-rc + llvm-cvtres → `rsrc_windows_amd64.syso`). The same art, `app\nobu_icon.png`, is used for the window and tray.
- The user's screen is 4K (3840 wide), and they used 150% zoom.

**v4.2 (Oct 21 2026):**
- **Resizable sidebar:** drag the 5 px sash to resize it, or double-click it to fit the longest name. The width is saved as `sidebar_width`.
- **Row spacing:** rows are spaced from the font's line height (list rows ≈ 2.1×, sidebar rows ≈ 1.65×), and the lists alternate row shading.
- **Folder lists:** the date and 12-hour time are on the left, and the name and preview are centred.
- **Title prompt:** opening a note that has a recording and still carries its automatic date name (`lib.is_auto_named`) asks for a title.
  - Save title: renames the note, inserts a `st:title` line at the top, and sets `doc["titled"]`.
  - Later: asks again next time.
  - Don't ask: sets `titled` without renaming.
- **Centred titles:** the Title style is centred by default via a style-level `align`. An explicit `al:` tag is stored only when the alignment differs from the style's own. New notes start with a Title line.
- **Colour labels:**
  - A note's colour is stored as `doc["color"]`. The editor keeps non-item keys in `editor.meta`, so saving the note preserves them.
  - A folder's colour is stored in a hidden `.nobufolder` JSON file inside the folder.
  - Colours show only as text colour in the sidebar tree and the folder lists, never inside a note.
  - `lib.note_info` caches each note's colour, preview, audio flag and titled flag, keyed on the file's modified time.

**v4.3 (Oct 21 2026):**
- **Sidebar handle:** a 12 px canvas grip with dots, highlighted on hover. Before, the visible 1 px line was a child widget with no bindings, which is why it was impossible to grab.
- **Heading font:** the user chose Eagle Lake (Astigmatic, OFL) for headings, so it is now the default `heading_font`. Varnyx is still in the user's fonts folder.
- **Font library:** 8 more OFL fonts bring it to 72 families, shipped in `setup\fontlib-v43.zip`. Licence texts are included: OFL, or Apache for Homemade Apple, Satisfy and Special Elite.
- **Themes:** `T.THEMES` offers dark, midnight, ember, forest, parchment (light), light and contrast, stored as `cfg theme`.
  - `T.set_theme` runs before any widgets are built, and the editor takes PAPER/DESK/INK from the theme.
  - Switching themes restarts Nobu: it starts `--restart`, which waits for the port, then quits.
- **Offline guard (`nobu_offline.py`):** patches `socket.connect`/`connect_ex` to allow only loopback connections. `nobu_models.download` runs inside `allow_downloads()` (thread-local). HF offline and telemetry env vars are set, and blocked attempts are logged. The Home page has a "100% local and private" panel with details.
- **Screen fit:** the saved geometry is clamped to the current screen, the minimum size is scaled, and the Home page scrolls when it doesn't fit. Tested at 1366×768.

**v4.4 (Oct 21 2026):**
- **Tutorial (`nobu_help.py`):** a window with a table of contents and 15 sections. It opens from a link under Help at the bottom of the Home page, and from the gear menu.
- **Drag & drop (`nobu_dragdrop.py`):** works in the sidebar tree, the folder list and the Unassigned list.
  - Drop targets: into a folder, above/below an item (shown by a blue line), the Unassigned nav item (notes only), or Trash.
  - Hovering over a closed folder for 0.8 s opens it, and the tree auto-scrolls near its edges.
  - Order is saved in `.nobufolder` as `order` (folders) and `note_order` (notes); the top-level order is in `Notes\.nobufolder`. `lib._ordered` lists ordered items first, then the rest A–Z, and renames update the order. `lib.place()` does the moving and ordering.
- **Vocabulary box removed:** the Settings "Names & unusual words" box only fed the speech model a list of words to expect. My dictionary does that and also corrects spellings, so the box is gone. Any text in it is migrated into `dictionary.json` at startup.

**v4.5 (Oct 21 2026), efficiency review:**
- **Guard wording:** the network guard is in-process only (it patches Python sockets inside Nobu). The Home panel, popup, tutorial and README now say it doesn't affect other programs.
- **Editor change counter:** the Text widget's commands are routed through a Tcl proc that counts insert/delete/replace and image/window create in `::nobu_ver...`. Table cells go through it too. It is done in Tcl, not a Python `createcommand`, because exceptions raised in Python callbacks are re-raised by the mainloop. `_version()` adds this count to `self._ver`.
- **Cached copy of the note:** `_items_now()` reuses the copy made at the last quiet moment (`_idle_work`, 900 ms) while the version hasn't changed. Undo snapshots share that items list (cost about 0), and undo history is capped at 80 steps or about 20M characters. Undo groups typing in bursts (a pause of more than 1.2 s, or a new paragraph).
- **Pagination:**
  - One `count -update -ypixels` pass, per-line heights without update, and a bisect over line tops.
  - Normal paragraphs: binary search over display lines.
  - Paragraphs over 2500 characters: proportional estimate plus `display linestart`. In Tk, `+N display lines` and partial ypixels/displaylines counts are O(n) for long logical lines.
  - Result on a 60k-word note: 2.2 s → about 0.15 s.
- **Spell check:** column indices (`L.c`) instead of per-word `+Nc` arithmetic and `tag_names` calls. Previously this was O(n²) on long lines.
- **Word count:** moved to idle time.
- **Thesaurus:** unpacked to `cache\thesaurus_en.dat` with a JSON word → offset index, so it uses about 20 MB instead of 130 MB. The speller loads lazily on first note open (about 40 MB).
- **Logging:** the `faster_whisper` logger is set to WARNING, and the offline guard is installed after logging is configured.
- **Measured (60k words):** load 97 ms, keystroke 0.5 ms, spell check of the whole note 117 ms. The library refresh with 636 notes takes 23 ms warm and 156 ms cold.
- **User's log:** no errors and no BLOCKED connections across versions 4.0–4.4.

**v4.6 (Oct 22 2026), personal copy only (the share folder is still 4.5 until the user asks):**
- **Shortcuts (`nobu_hotkeys.py`):** Windows RegisterHotKey in its own message-loop thread (system-wide; Tk `bind_all` is the fallback elsewhere).
  - Defaults: Ctrl+Alt+R record, Ctrl+Alt+E edit, Ctrl+Alt+X cut. Pressing one while recording stops it.
  - Configured in Settings > "Dictation, cuts & shortcuts" by press-to-capture. Shortcuts are shown next to the voice phrases.
- **Dictation and cut options:**
  - `edit_silence_seconds`: 0 means dictation only ends on the phrase or the shortcut.
  - `confirm_cut` (default on): off deletes straight away, and Ctrl+Z still restores it.
  - `confirm_edit`: shows the dictated text with Insert/Discard before inserting.
- **Command recognition:**
  - `phrase_samples` per command (record/stop/edit/cut): the normalised strings the speech model produced for the user's voice, matched with a 2–7 token window at ratio ≥ 0.86.
  - Second listen: if a burst is a near miss (verb-ish, wake-ish, or a short burst ending in this/that or starting with an n-sound), it is re-transcribed with an `initial_prompt` naming the commands. The stop check does the same.
  - Teach now covers all four commands (3/3/2/2), with a 1.1 s phrase hang so "Nobu … record this" stays one phrase. It ends in a test stage that keeps learning from near misses, and closing early still saves what was learned.
- **Custom theme:** 10 user colours; `build_custom` derives the rest. Stored as `cfg custom_theme` with theme "custom", registered before `set_theme`. Editor is ThemeEditor with a live preview.
- **Title sync:**
  - Editing the first Title-style paragraph renames the note at idle time (`_check_title`, compared with the title at load).
  - Renaming from outside updates the title line: in the open editor via `replace_title`, or in the file via `lib.rename_note(sync_title=True)`.
- **Fonts:** `nobu_fonts.add_user_fonts` takes .ttf/.otf or a .zip, copies into `fonts\`, loads them privately (AddFontResourceEx), resets the registry and installs them into Windows. No restart needed. Added to the Fonts window and the tutorial.
- **Sidebar triangles:** Treeview indicatorsize 13 × scale with margins, plus a click zone left of the name (depth × indent + 34 px) that toggles open/closed.

**v4.6.1 (Oct 22 2026), personal copy only:**
- **Font import:** "Permission denied" happened because the user had already unzipped those fonts into `fonts\`, and Windows locks fonts loaded with AddFontResourceEx.
  - `add_user_fonts` now skips identical files ("already in your fonts"), writes a different file under a "(2)" name, and ignores `__MACOSX` entries.
  - The registry prefers .ttf over .otf for the same style.
  - `licence_blocks_embedding` also blocks family or file names containing personal, trial, demo or non-commercial.
- **Shortcut persistence:** shortcuts are saved the moment they're captured or cleared. The likely loss was ThemeEditor calling `settings.cancel()`; it now saves the open Settings with the theme set to Custom.
- **Single-key shortcuts:** allowed for F1–F24, Pause, ScrollLock, Insert, Home/End, PageUp/Down, Menu and numpad keys. Other keys need Ctrl or Alt. Esc, Enter, Tab, Backspace, Delete, PrintScreen, the arrows, Caps/Num Lock and Win are never allowed.
- **Second-listen safety:** the user's log showed the hinted listen hallucinating ("Now he will be able to" → "Nobu, edit this."; "Oof. Oof…").
  - `near_miss` now requires a window similarity of at least 0.5 to a canonical or learned command.
  - `consistent()` rejects a second result whose key ratio to the first is below 0.45, that runs more than 4 tokens longer than the first, or that repeats a token more than 3 times.

**v4.6.2 (Oct 22 2026), personal copy only:**
- **Bug:** every captured shortcut came out as "Alt+key". `combo_from_event` read Tk state bit 0x8 as Alt, but on Windows 0x8 means Num Lock is on (Alt is 0x20000). Alt now uses 0x20000 on Windows and 0x8 elsewhere.
- **Any single key allowed** (`valid()` now returns `(ok, problem, warning)`):
  - F-keys, Pause, ScrollLock, Insert, Home/End, PageUp/Down, Menu and numpad keys: accepted silently.
  - Letters, digits, punctuation, Space, arrows (and Shift+those): accepted after a "Use it anyway / Pick another" warning, since RegisterHotKey takes the key over system-wide while Nobu runs.
  - Esc, Enter, Tab, Backspace, Delete, PrintScreen, Caps/Num Lock: need Ctrl or Alt ("multi" combo).
  - Win key and Windows shortcuts (Alt+Tab, Alt+F4, Ctrl+Esc, Alt+Esc, Ctrl+Alt+Del, Ctrl+Shift+Esc, Alt+Space): refused.
- Shifted symbols (exclam, at…) map back to their base key; VK codes added for arrows, Enter, Tab, Esc, Backspace, Delete.
- **Share package (Oct 23 2026):** `Nobu Notes - Share` updated to v4.6.2 (all app .py + README). The archive on the Desktop is now `Nobu Notes - Share.zip` (made with File Explorer's Compress to ZIP; ~128 MB, verified). The old .7z went to the Recycle Bin. 7-Zip isn't installed, and the Win11 "Compress to 7z" option is only on the right-click menu.

**v4.7 (Oct 24 2026), personal copy only (share folder still v4.6.2):**
- **Typed notes:** Unassigned's "Open" button is replaced by "+ New note"; the folder view's Open button is removed. Opening is by double-click on the row under the pointer (`_list_double`), right-click > Open / Open side by side / Open in its own window, Enter, or middle-click (opens side by side). `new_note()` defaults to the folder in view, then the open note's folder, then Unassigned.
- **Titles with any characters (`lib.note_stem`, `lib.title`, `lib.same_title`):** `" / \ : * ? < > |` are mapped to look-alikes in file names (＂ ∕ ⧵ ꞉ ＊ ？ ＜ ＞ ｜). Trailing dots become U+2024, and reserved device names get a U+2060 suffix. `title()` maps them back. `same_title` ignores " (n)" suffixes, which fixes a rename loop when renaming from the title line.
- **Sidebar:**
  - selectmode is extended. A plain click opens or navigates on mouse *release*; Shift/Ctrl-click only selects; right-click on a multi-selection gives a bulk menu (Colour, Open side by side, Move, Export, Delete).
  - Toggle zone = indent + indicator (23 px × scale) + width of " ▪ ". A second click within 0.4 s on the same triangle is ignored. `_tree_double` never closes a folder.
  - A drag that ends on its own row counts as a click. The drag threshold is now 10 px.
  - Nav clicks are handled on release, so clicking an already-selected entry still navigates. Right-clicking Unassigned offers New note / Import.
- **Lazy tree:** closed folders get a `lazy:` placeholder and are filled on `<<TreeviewOpen>>` or `_tree_open`. `refresh_library` keeps the set of open folders and never force-expands; the old rule kept the current project's ancestors open, which caused the import expansion bug. `_reveal(path)` expands ancestors only on explicit navigation.
- **Import default:** the folder in view, else Unassigned (no longer a stale `current_project`).
- **Speed:**
  - `lib._scan` uses scandir (mtimes come free with the listing); also `contents()`, `count_notes()` and `has_children()`.
  - `folder_meta` is cached by mtime_ns. `inbox_count` and `trash_count` no longer parse files.
  - `note_info` has a persistent cache at `cache\noteinfo.json` (v2; keyed by path relative to home, plus mtime and size). It is saved 5 s after refreshes and pruned on quit.
  - Lists fill 250 rows at once, then 400 per tick, and keep selection and scroll position.
  - Home's Recent comes from `cfg.recent_notes` plus the newest inbox notes, with no full walk. The .bak tidy now runs once (marker `cache\.tidied-v4`).
  - Test results with 4,500 notes: refresh 0.014 s, inbox first rows 0.17 s, a 3,000-note folder in 0.24 s, Home 0.17 s.
- **Workspace (`nobu_workspace.py`):**
  - Panes are placed with fractions and separated by custom grip-dot sash canvases (drag; double-click to even), up to 6.
  - `app.editor` is the active editor (set on FocusIn or click). `main_active` tracks the last active pane in the main window. Pop-outs are non-transient Toplevels.
  - Transfers keep undo/redo, cursor and scroll. Dragging a note's title or "where" label out of the root pops it out; dragging over panes reorders; dragging from a pop-out onto Nobu docks it. Sidebar or list drags onto the page open notes side by side (target "side").
  - The ribbon is hidden by default when more than one pane is open (☰ toggles; the choice is kept per editor). In narrow panes the head switches to small buttons and the gutters shrink to 10 px.
  - App helpers: `editors_for`, `_repath`, `_note_showing`, `workspace_emptied`, `show_workspace`. Dictation and cut route via `cmd_editor` / `_cmd_ed(note)`. `start_in_note(kind, ed)` and `title_edited(text, ed)` take the editor explicitly.
- **Speech:**
  - `nobu_transcribe.DECODE` uses beam 5, temperature fallback [0, .2, .4, .6, .8], and VAD threshold 0.4 / min_silence 900 / pad 400.
  - Dictionary names are passed as **hotwords**, which apply to every 30 s window; `initial_prompt` only reaches the first.
  - `level()` raises quiet audio (99.9th percentile → 0.5, at most 6×).
  - `Frontend.process2` returns (cleaned, natural); natural = gain + high-pass only. Engine Blocks carry `.light`, and recordings write it when `transcribe_original` is on (default). Detection and the 6 s mic test still use cleaned audio.
  - Optional model `large-v3-turbo` (mobiuslabsgmbh/faster-whisper-large-v3-turbo). Not tested here because huggingface is blocked in the sandbox; the downloader is generic.

**v4.7.1 (Oct 24 2026), personal copy only:**
- **Triangle debounce** is now 0.2 s (`_zone_toggle`). Windows reports any second press within roughly 0.5 s as `<Double-Button-1>`, and that event used to be swallowed in the toggle zone, which felt like a long lock-out. Now:
  - A double-click in the zone toggles too (so a quick close-then-open works).
  - A double-click elsewhere behaves like a press: Ctrl or Shift selection is handled manually (`_tree_extend`), the drag starts, and navigation happens on release. A folder is never closed this way.
  - Lists open on release after a double-click, unless the press turned into a drag (`_list_release`).
- **Snapping (`Workspace.snap_target`):**
  - Dragging a note's tab: the left third of the page area (or over the sidebar) goes to index 0, the right third (or up to 48 px past the window edge) goes to the end, and the middle goes to the nearest gap.
  - Inside the window, or within 48 px of it, a tab drag never pops out; only well outside does.
  - Preview: a translucent accent Toplevel (alpha 0.28) on Windows, or a line elsewhere.
  - Pop-out windows dragged by the OS title bar: `<Configure>` position changes are watched every 60 ms using `GetAsyncKeyState` (respecting swapped buttons). Releasing with the pointer in a 48–72 px band at the page area's left or right edge docks the window on that side. Resizes and the first second after creation are ignored. On non-Windows it's disabled (the button state is unknown).
  - Pop-outs bind FocusIn/FocusOut to update the voice-command context.
- **Trash:** only the "Empty trash" button remains. Restore and Delete permanently (also for multiple items) are on the right-click menu; right-clicking empty space offers Empty trash.
- **Tests:**
  - `tests/v4/test_47w.py`: 48 checks driven by real synthesized events (clicks, double-clicks, Ctrl/Shift, shaky click, mouse drag into a folder, nav, list double-click / Enter / middle-click, toolbar toggle, snapping left and right, pop-out by drag, window-drag docking, editing and saving a moved pop-out, deleting a book while its notes are open, Trash right-click restore, symbol titles from the page, dictation routing, import default, settings, cache).
  - `tests/test_audio47.py`: hiss RMS in the recording is about 687 with natural sound and about 29 with filtering.

**v4.8 (Oct 24 2026), personal copy only (share folder still v4.6.2):**
- **Sidebar:** clicking a folder name toggles it. A closed folder opens and shows its contents; an open one closes. This uses the same 0.2 s bounce guard as the triangle.
- **Workspace rewritten around tabs (`nobu_workspace.py`):**
  - Each `Pane` ("page") has a tab bar: `tabs_fr` plus `ctl` (☰ toolbar, ⧉ open beside, ⇱ own window), a 1 px line, and `body`. Every tab is its own NoteEditor (only the current one is packed), so switching tabs is instant and keeps undo history.
  - `Pane.ed` is the current tab. `MAX_TABS` is 12 per page; the least recently shown tab is closed (and saved) beyond that. `MAX_PANES` is 6.
  - `open()` adds a tab next to the current one in `cur_pane`. `side=True` creates a new page; `pane=` and `tab_index=` place it explicitly. An already-open note is brought forward, or moved if a place was requested.
  - `move_tab` transfers an editor between pages, or pop-out → page. `split(ed, index)`, `close_editor`, `close_others` (joins all pages into one, as tabs), `pop_out(ed)`, `open_popout(path)` and `dock(po, index|pane)`.
  - `ws.blank` is a hidden NoteEditor that stands in as `app.editor` when nothing is open.
  - Tabs:
    - click shows the tab and focuses its text (so Ctrl+W hits the right note)
    - ✕, middle-click or Ctrl+W closes; Ctrl+PgUp/PgDn cycles
    - right-click menu: close / close others / new page left or right / own window / rename
- **Snapping (`target(xr, yr, src)`):**
  - Over a page: left 28% → split to its left; right 28% → split to its right; middle → a tab of that page; tab bar → a tab at that position.
  - Left of the page area (sidebar) or just past the right edge → far left or far right.
  - More than 48 px outside the window → its own window. A lone tab dropped on its own page does nothing.
  - When a folder list is showing (or nothing is open): `open` with side left / right / center over `app.content`.
  - Shadow: a single Toplevel with alpha 0.30 (translucent on Windows).
- **DragDrop:** dropping on a folder row in a list still moves the item into that folder. Anywhere else on the page area (or far outside the window) gives an `("open", target)` → `ws.drop_notes`; a folder dropped there is opened. The ghost label describes the action. The old move-into-current-folder-by-dropping-on-the-list behaviour is gone.
- **Editor:** delayed font-list and "just added" callbacks are now tracked as `*_job`s, so closing a tab cancels them (fixes TclErrors on quickly closed tabs).
- **Tests:** `tests/v4/test_48.py` (28 checks, real events: name toggle, tabs, Ctrl+W, the shadow appearing on the correct side mid-drag, split right/left, join by middle, lone-tab no-op, edge vs far-out pop-out, pop-out name docking right, list drags left/middle/right/out, folder drag opens, sidebar drag right, join pages, tab limit, close all → blank, dictation routing, clean log). `test_47v` and `test_47w` were updated to the new design. All suites pass.

**v4.9 (Oct 24 2026), personal copy only (share folder still v4.6.2):**
- **Even side-by-side pages:**
  - Both editor header rows have a fixed height (`_fit_head` sets `head_top` / `head_row` heights with pack_propagate off).
  - The header switches to small buttons whenever title + big buttons don't fit.
  - The Unassigned banner is hidden in compact or side-by-side mode.
  - Tk sometimes left `rib_box` collapsed (reqheight 1) while the ribbon was still packed, so pages were offset by about 80 px roughly 1 run in 10. The fix: `show_ribbon` never re-packs an already-managed ribbon, and `_check_rib_box` (scheduled after every flow, layout and tab show) re-packs if the holder is shorter than the ribbon. 12 of 12 runs were clean after the fix.
- **Compact toolbar** (user's choice): side-by-side pages show only group 0 (style / font / size) and group 1 (B I U S x² x₂), plus "▾ More tools" (`_g_more` → `_more_tools`).
  - More tools holds colour, highlight, case, clear, painter, align, spacing, indent, lists, find, spelling, thesaurus, an Insert submenu (picture / table / page break / symbol / date) and dictate / cut.
  - Menu builders were refactored into `_fill_color`, `_fill_hl`, `_fill_case`, `_fill_spacing` and `_fill_symbols`.
  - ☰ switches between full and compact (`_rib_choice` is "full" / "compact" / None). A single page or a pop-out gets full by default.
  - The page right-click menu gained Find & replace, Next spelling mistake and Thesaurus (Insert picture was already there).
- **Flicker fix:**
  - `ws.show_drop` only touches the overlay when the rect changes, never re-lifts, and recreates the window only when the colour or strength changes.
  - DragDrop no longer hides and reshows the overlay on every motion, skips everything when the target hasn't changed, and finds widgets by position instead of `winfo_containing` (the overlay itself was being hit-tested).
  - Test: 40 wiggles in one zone showed the overlay once and never withdrew it.
- **Drop highlight colour:** config keys `drop_color` ("" = accent) and `drop_alpha` (0.12–0.7, default 0.30). Set in Settings > Appearance > Make my own colours > "Drop highlight" (swatch, strength slider, "Same as accent"). Saved immediately, works with any theme, and is previewed in the theme preview.
- **Colour labels:** `lib.COLOR_FAMILIES` holds 8 families × 5 colours = 40 (the original 12 names and values kept), plus Custom and None. The menu uses columnbreak, giving 9 columns.
- **Tutorial rewritten** (21 sections, about 2,300 words, every feature, plain wording); the contents column was widened to 290 px.
- **Tests:** `tests/v4/test_49.py` (14 checks: page tops / toolbar / header line up even when the widths differ, compact toolbar groups, More tools contents, ☰ toggle, right-click items, no-flicker counts, default and custom highlight colour, 40-colour grid, picking a new colour, clean log) and `test_tut.py` (renders the tutorial). All earlier suites pass.

**v4.9.1 (Oct 24 2026) — full code audit, personal copy only (share folder still v4.6.2):**
- **Dead code removed:**
  - unused functions: `replay`, `ribbon_shown`, `rename_current`, `delete_current`, `close_pane`, `to_text`, `process()` (DSP now uses `process2` with an in-place `_ola`), `log_path`, `Pane.ed`
  - an `and False` branch, `size = size`, `"ZapfDingbats" if False`, and unused variables
  - `getattr` fallbacks replaced with attributes initialised in `__init__`
- **Bugs fixed:**
  - HTML import leaked formatting past void tags (`<br>` inside `<b>`): the format stack is now tag-matched.
  - Sup/sub offsets now rescale on zoom: `_ftags` cache, which also replaces the per-run `tag_names()` scan.
  - `Image.open` calls are context-managed, so Windows no longer keeps files locked.
  - Pending `after()` timers from destroyed windows could later fire as whatever command reused their name. Python 3.11 names `callit` after the lambda, and this caused a random `TypeError` in tests. New helper `T.later(widget, ms, fn)` schedules on the main root and skips the call if the widget is gone; the editor, Tip, Meters, Teach, Diagnostics, ThemeEditor and workspace `_transfer` use it.
  - Popup menus (`T.menu` with a non-Menu parent) were never destroyed. Unmapped old popups are now destroyed when a new one is made.
  - Diagnostics no longer redraws (and resets scroll) unless the detections changed.
  - `_tick_meter` always reschedules itself.
  - `apply_dictionary` doesn't leave an empty undo step.
  - `_fit_head` → `_update_header(refit=False)` avoids a re-entrant refit.
  - Tray icon art loads once.
- **Quality-of-life additions:**
  - Restore session: config keys `open_tabs` (pages → `{tabs, cur}`; pop-outs become tabs of the last page) and `reopen_notes` (Settings checkbox). `App._session` / `_restore_session` run after `show_home` at start; `_remember_window` saves geometry plus a `maximized` flag on hide and quit (the window is zoomed at start if the flag is set).
  - Esc cancels a sidebar or list drag (`DragDrop._cancel`, `.cancelled` blocks release-as-click) and a tab drag (`ws._cancel_tab_drag`). Both temporarily take over the root `<Escape>` binding and restore the previous one afterwards.
  - Ctrl+Tab / Ctrl+Shift+Tab cycle tabs; Ctrl+W also works with Caps Lock on.
  - `T.toplevel` records `_anchor` (the focused toplevel), and `fit` / `_center` place dialogs over it (pop-outs, other monitors).
  - In `confirm(danger=True)` Enter = safe answer (focus on No); otherwise Enter invokes the focused button.
  - Settings: the wheel over a Combobox, Spinbox or Scale scrolls the page (`_wheel_scrolls_page`). Home: the wheel works anywhere on the page (bind_all + ancestor check, replacing the broken Enter/Leave approach).
  - Tooltips use a 450 ms delay and hide on press.
  - Change case with no selection uses the word at the cursor.
  - Find & replace:
    - Enter in Replace replaces; Esc closes and the window close button clears the highlight
    - wrap notice
    - Ctrl+F again with a new selection searches for it
    - Replace all says "Not found" with no empty undo step
  - The ⧉ menu adds "Elsewhere in <book>" (`lib.book_of`).
  - Dictionary: confirm before Remove; Enter saves a word.
  - FontBrowser: the size box refreshes on typing; prompts appear when no font is picked or no note is open.
  - Export: folder notes are scanned once; the font warning only shows for formats that embed fonts; the theme-editor drop-highlight slider is saved after a 400 ms debounce.
  - The pending-recordings prompt says what "Skip them" does.
  - Transcribe-file gives status feedback.
- **Tests (v4.9.1):** `tests/v4/test_audit.py` has 158 checks. It presses every toolbar button, every More-tools and right-click entry, header buttons (full and small), pane controls, every tab-menu entry, workspace bar, sidebar nav, folder, note and bulk menus, list and Unassigned buttons, Trash, Home buttons, the ⚙ menu, every Settings slider, checkbox and drop-down, hotkey capture and None, the theme editor, dictionary, fonts, diagnostics, Teach, all 5 export formats, import, danger-Enter, the drag-Esc cases, tooltip delay, dialog placement over a pop-out, popup cleanup, and session restore. It also checks for a clean log. All earlier suites pass (`test_46` uses `rename_note`; `test_47w` / `test_47v` use `pane.cur`).

**v4.9.2 (Oct 25 2026) — pasting and cropping pictures:**
- **Paste pictures:** "Copy image" in a browser puts a bitmap *and* HTML `<img src="https://...">` (plus the address as text) on the clipboard. The HTML path ran first, `fetch_image` refused the web address (offline), and nothing was pasted. `NoteEditor._has_words(items, text)` now decides: if the clipboard has no real writing (no text, picture or table in the HTML; text that is empty or a bare URL), `paste_image()` is tried first. A URL with no picture still pastes as text. `paste_image` replaces the selection, takes on the paragraph's tags (`_add_image`, shared with `insert_image_file`) and repaginates.
- **Crop:** picture right-click > "Crop…" opens `nobu_crop.CropWindow` (non-blocking, so tests can drive it). It shows a dimmed copy with the kept part bright. Drag outside the box (or anywhere while it's still the whole picture) draws a new box, inside moves it, near an edge or corner (9 px) resizes it. "Whole picture", Cancel / Esc, Crop / Enter. `NoteEditor.crop_image(name, box)` saves `<name>_cropped.png|jpg` into `Images/<note>/` with `nd.save_pil_image(img, note, name, ext)`, keeps the original file, keeps the display scale (`w * kept_width / width`) and pushes an undo step, so Ctrl+Z restores the whole picture.
- **Tests:** `test_audit.py` "pictures: paste and crop" (screenshot, browser Copy image, URL-only text, text + picture, Explorer files, empty clipboard; Crop… menu entry, Esc, mouse draw / move / resize, click outside, Whole picture, Cancel, the cropped file and scale, original kept, saved in the note, undo, crop again with Enter).

**v4.9.3 (Oct 25 2026) — copying pictures out, web links (share copy still v4.9.2):**
- **Copy picture:** picture right-click > "Copy picture" (`NoteEditor.copy_image`), and Ctrl+C when the selection is just one picture. `nobu_clip.set_rich(..., picture=path)` adds CF_DIB (flattened on white) and the registered "PNG" format (keeps transparency) next to the HTML (`file:///` img, so Nobu and Word paste it) and RTF (`\pngblip`). With no text, CF_UNICODETEXT is left out, so pasting back into Nobu takes the HTML path and `fetch_image` copies the file into the note's Images folder.
- **Web links:** new character key `link:<url>` (`R.CHAR_KEYS`). `R.clean_url` adds https:// to `www.` and %-encodes space, quotes, braces and backslash (tag-name and RTF safety); `R.find_urls` trims trailing sentence punctuation and unmatched brackets. Paste (not "plain text") runs `_autolink` over the inserted range (dump-based, so pictures and tables count as one character); HTML `<a href>` (http, https, mailto only) and Markdown `[text](url)` become links; Word import reads `Hyperlink.url`. Editor: `_ensure_link_tag` (accent colour, underline, raised; Ctrl+click → `open_link` → `open_path`, i.e. the browser, a separate process, so Nobu stays offline); right-click Open link / Copy link address / Remove link; `_typing_tags` keeps a link tag only when typing inside it; Clear formatting keeps links; spell check skips written addresses. Exports: docx `w:hyperlink` with an external relationship (Word blue + underline unless coloured), PDF `<a href>`, HTML/EPUB `<a href>`, RTF `HYPERLINK` field, txt adds " (url)" after link words that aren't the address.
- **Tests (not run yet, per the user's new rule):** `test_audit.py` "copy picture" (menu entry, real clipboard has the picture at full size, pastes back, Ctrl+C on a lone picture) and "web links" (paste addresses, paste HTML links, plain paste makes none, typing after / inside a link, Ctrl+click, plain click doesn't open, right-click entries, undo, saved, spell check, Clear formatting, copy keeps href). `test_export.py` link checks (find_urls, clean_url, HTML/Markdown in, every export format, RTF, Word re-import).
