# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Nobu Notes is a Windows desktop app: a voice-activated, fully offline note recorder and Word-like writing app built with Python 3.11 + Tkinter. The user says "Nobu, record this" ("no-boo"), and the speech is recorded, transcribed with faster-whisper, and saved as a note. All source code is in `app/`. The launcher's Go source is in `launcher/`, the tests in `tests/`, helper scripts in `tools/`, and design history in `docs/design-notes.md`. There is no linter or build step for the Python code.

This folder is also a **live install holding the user's real data**. `Notes/` (their books and campaigns), `Recordings/`, `Images/`, `config.json`, `cache/`, `logs/` and the top-level `fonts/` (their own fonts) belong to the user. Do not edit, move or delete them while working on code. `.gitignore` keeps them out of git; never force-add them.

## Rules from the user (always follow)

1. **Change this install only.** The copy for other people (`..\Nobu Notes - Share` and `..\Nobu Notes - Share.zip` on the Desktop) is updated **only when the user asks**, and only with `tools\make_share_copy.py --yes`.
2. **After every new or changed feature**, update the tutorial (the `SECTIONS` text in `app/nobu_help.py`) and the "NEW IN VERSION x" section at the top of `README.txt`. Tutorial style, in the user's words: explain every feature "in the easiest possible way to understand ... minimal fluff or filler words, and minimum technical jargon the average person might not understand ... as concise and informative as possible."
3. **Don't run the test suite unless the user asks for it** (said Oct 25 2026). Instead, add a check for every new or changed feature as you go, ideally in `tests/test_audit.py` for anything with a button, slider or menu entry, so it runs whenever the user asks for the tests. A quick syntax check (`runtime\python.exe tests\run_tests.py compile`, a few seconds, no windows) is fine. When you report a change, say plainly that the tests haven't been run yet.
4. **Commit to git** after each finished change (see Git), so any change can be undone.
5. Talk to the user in plain words. They are a writer, not a programmer.

## Running

`NobuNotes.exe` is a launcher. On first start it unpacks `setup/runtime.zip.00*` into `runtime/` (a bundled Python with every dependency in `runtime/Lib/site-packages`), then runs `app/nobu_main.py`. To run it from source with visible errors (this is what `Debug - show errors.bat` does):

```bash
runtime\python.exe app\nobu_main.py
```

- It runs as **one copy at a time**: `main()` binds `127.0.0.1:47651`. If a copy is already running (often hidden in the tray), a new launch just tells that copy to show its window and exits. Quit the tray icon before testing changes. `--restart` waits for the old copy to close; `--tray` starts it hidden.
- Logs go to `logs/nobu.log` (rotating). stdout and stderr go to `logs/stdout.txt` and `logs/stderr.txt` when there is no console.
- To check the syntax of every module: `runtime\python.exe -m py_compile app\nobu_main.py` (one file at a time, or loop over `app\nobu_*.py`).
- `NOBU_HOME` overrides the data root (by default the folder that contains `app/`). Set it to a scratch folder when you exercise the library, document or export code headlessly, so the real `Notes/` is not touched.
- On first start, `_unpack_addons()` in `nobu_main.py` also extracts `setup/addons-v4.zip` (docx, reportlab, pypdf, spellchecker…) into site-packages and `setup/fontlib-v43.zip` into `app/fonts/lib`. A `.unpacked-<zip>` marker file controls this, so you must change the zip name to make an update extract again.

## Architecture

**Threads.** `App` in `nobu_main.py` owns the Tk root. The audio engine, the transcriber, the hotkeys and the instance listener run on background threads and **never touch Tk directly**. They call `app.ui(fn, *args)`, which puts the call on `uiq`, and `_pump()` runs those calls on the Tk thread every 150 ms. New background code must follow this pattern.

**Voice pipeline.**
- `nobu_audio.Engine` reads the mic in 50 ms blocks at 16 kHz. Each block goes through `nobu_dsp.Frontend` (gain, hum filter, noise reduction) and then `SpeechDetector` (an ONNX voice-activity detector). A state machine in the engine handles idle, recording, paused, teach and capture.
- Short bursts of speech go to `nobu_transcribe.Detector` (a small whisper model, `detect_model`). The engine checks the result against the commands record, stop, edit and cut using `nobu_match`, which does fuzzy matching against `wake_aliases` and `phrase_samples` learned by "Teach Nobu my voice".
- A finished recording is written to `Recordings/` and queued on `Transcriber` (the large model, `transcribe_model`, unloaded after idle minutes). `nobu_dictionary` respellings are applied, and the result reaches the App as an event that creates a note in `Notes/Unassigned/`.
- The engine reports what happens through `on_event(name, **kw)`, which goes to `App._engine_event`. The transcriber's events go to `App._tx_event`.
- The engine keeps two versions of the audio: the noise-filtered sound is used to detect commands, and the "natural" sound (`Block.light`) is used to transcribe, controlled by `transcribe_original`.

**Note model.**
- A `.nobu` file is JSON, `{"format":"nobu-note","version":2,"items":[...]}`, handled in `nobu_doc.py`. Items are text runs that carry tag lists, plus image, table and page-break blocks.
- The tag vocabulary (character tags like `b`, `ff:`, `fs:`, paragraph tags like `st:`, `al:`, `li:`) is defined in `nobu_rich.py`. That module is the shared hub: the editor, importers, exporters and clipboard all convert through `items_to_paras()` / "paras" and `to_html()`. When you add a formatting feature, update `nobu_rich` first, then the editor (`nobu_editor.NoteEditor`, which maps tags to Tk text tags), `nobu_export` (docx/pdf/epub/html/txt) and `nobu_importers`.
- `save_doc()` writes atomically through a `.tmp` file and keeps one backup per note in `Notes/.backups`.
- Paths saved inside notes and config (images, audio links like `audio|Recordings/...`) are **relative to HOME**. Always use `rel_to_home` / `abs_from_home` from `nobu_config`.
- Pictures: `nobu_pictool` (select, move, resize with the mouse) and `nobu_float` (pictures placed anywhere, text flowing round them). Floating pictures make the editor add invisible `"\n"` characters tagged `softnl` beside them. They are never saved, so any code that walks the Text by lines must skip them: use `flow.plain()` for text, and `_par_start`, `_is_cont` and `_line_iter` for paragraphs. Never call `count -update` straight after changing tags (it can crash Tk), and avoid `tag_raise` in anything that runs per keystroke (it makes Tk re-measure the whole note). `docs/design-notes.md` has the details.

**Library on disk** (`nobu_library.py`).
- `Notes/Unassigned` is the inbox. Each top-level folder is a book or campaign, and sub-folders can nest to any depth.
- `.trash` holds deleted items: deleting always moves the item, and its audio, there.
- `.nobufolder` JSON files store the sidebar order and colour labels.
- A note's title can contain any character. `note_stem()` swaps the characters Windows forbids in file names for look-alike Unicode characters and also handles reserved names like CON. Always build note file names with `note_stem` / `unique_path`, never by hand.
- `cache/noteinfo.json` stores note previews between runs.

**UI layout.**
- `nobu_main.App`: the main window, sidebar tree, Home and folder lists, tray, and the glue code.
- `nobu_workspace.Workspace`: tabs, up to 6 side-by-side `Pane`s, and `PopOut` windows.
- `nobu_dragdrop`: drag and drop in the sidebar and lists.
- `nobu_ui`: Settings, Teach, Diagnostics, Dictionary, the recording badge and the first-run model download (`SetupWindow`, through `nobu_models`).
- `nobu_theme`: colour themes. The `T.*` colour constants are read at startup, so changing theme restarts the app.
- `nobu_fonts`: the bundled font library (`app/fonts/lib/fonts.json`) and per-user Windows font installs. User fonts go in `fonts/`. Fonts marked personal-use or demo must never be embedded in docx, epub or html exports.

**Offline guarantee.** `nobu_offline.install()` runs early in startup and blocks the process's own non-local network connections. The only exception is the model download in `nobu_models`. Do not add features that need the network.

## Conventions

- Settings live in `nobu_config.DEFAULTS`. Add new keys there with a short comment. `Config.save()` writes only the values that differ from the defaults. `set_temp()` changes a value without saving it, for live preview; `update()` saves it.
- Bump `VERSION` in `nobu_config.py` and add a "NEW IN VERSION x" section at the top of `README.txt` when you ship user-visible changes. README.txt is the user-facing changelog and manual, and the tutorial text is in `nobu_help.py`.
- `docs/design-notes.md` records what each version changed and why. Add a short section to it whenever you ship a version.
- Text the user sees, and code comments, use plain, non-technical British-leaning English ("colour", "Settings > Appearance > ..."). Match that tone.
- Heavy modules (faster_whisper, docx, reportlab, the spell checker, the thesaurus) are imported lazily inside functions to keep startup and idle memory low. Keep it that way.
- **Timers:** schedule with `T.later(widget, ms, fn, *args)` (from `nobu_theme`), not `root.after` directly. `T.later` skips the call if the widget has been destroyed. Plain `after` callbacks from closed windows used to fire into unrelated commands.
- **Dialogs:** use `T.info`, `T.confirm`, `T.ask_string` and `T.menu`. They open over the window the user is working in (pop-outs included) and clean up after themselves. Use `T.confirm(..., danger=True)` for anything that deletes: Enter then means "No".
- Set every attribute in `__init__`, not through `getattr(self, "x", default)` fallbacks.
- Esc cancels drags (`DragDrop._cancel`, `Workspace._cancel_tab_drag`). Keep that working for any new drag.

## Tests

Run these only when the user asks (rule 3).

```bat
"Run tests.bat"                                   :: double-click: every test, about 10 minutes
runtime\python.exe tests\run_tests.py             :: the same from a terminal
runtime\python.exe tests\run_tests.py --quick     :: fast tests only, no windows open (under a minute)
runtime\python.exe tests\run_tests.py audit 48    :: only tests whose names contain these words
```

- **Quit Nobu first** (tray icon > Quit). The window tests refuse to start while it is running, because they use the same shortcuts and the one-copy port.
- The window tests really open Nobu windows on screen for a few seconds each. Don't type or click while they run.
- Each test runs in its own temp folder with its own `NOBU_HOME`, so real notes and settings are never touched. Every test starts with `import _here` (`tests/_here.py`): it finds `app/`, repeats the Windows runtime set-up from `nobu_main`, and moves into a scratch folder.
- A test reports `RESULT a/b passed`, printing `PASS`/`FAIL` lines. Tests without a RESULT line (like test_audit and test_export) have their `PASS `/`FAIL ` lines counted. Tests with neither pass if they finish with no traceback. The runner ignores the "not installed" messages of the optional add-ons `pystray`, `sounddevice` and `tkinterdnd2`, and treats every other traceback as a failure. Full output of the last run is in `tests/last-run/` (ignored by git).
- `test_audit.py` is the main safety net: it presses every toolbar button, menu entry, slider, checkbox and dialog, and checks each one did its job. It answers dialogs automatically by replacing `T.confirm`, `T.ask_string`, the file pickers and `tk.Menu.tk_popup`.
- `test_voice.py` needs a recording of the wake phrase. It uses `Recordings/Nobu Notes/2026-10-21_09-28-28.wav` if it still exists, or `tests/samples/voice.wav`, and otherwise skips the engine checks.
- Set `NOBU_TEST_SHOTS=C:\some\folder` to save screenshots during the window tests.
- These tests were written and passed on Linux, under a virtual screen. When they first run on Windows, fix any purely Windows timing or window-manager differences in the test, not the app, unless the app is really wrong.

## Git

**First session only, if there is no `.git` folder yet:** set it up, then tell the user it's done. Git comes with Git for Windows; if `git` is missing, ask the user to install it.

```bat
git init -b main
git config core.autocrlf false
git add -A
git status --short
git commit -m "Nobu Notes 4.9.1: start of history"
```

Before committing, check that `git status --short` lists only `app/`, `docs/`, `launcher/`, `tests/` and `tools/` files, plus `CLAUDE.md`, `README.txt`, the two .bat files, `.gitignore` and `.gitattributes` (about 65 files). It must list nothing personal.

After that, the folder is a git repository with one branch, `main`. Only code, docs, tests and tools are tracked. `.gitignore` lists everything personal or bulky (runtime, models, setup zips, the font library, the thesaurus, NobuNotes.exe).

- Commit after each finished change, with a plain message saying what changed for the user, e.g. `git add -A && git commit -m "Find & replace: Esc closes it"`.
- Before a risky change, check `git status` is clean, so `git restore .` can undo it.
- Never commit anything under `Notes/`, `Recordings/`, `Images/`, `config.json`, `cache/`, `logs/` or `fonts/`.
- There is no remote. Don't add one or push unless the user asks. A public remote would need the README checked for anything personal first.

## The copy for other people

`runtime\python.exe tools\make_share_copy.py` shows what it would do. Add `--yes` to rebuild `..\Nobu Notes - Share` and `..\Nobu Notes - Share.zip`; the folder sits at the root of the zip. It copies only the program: exe, README, debug .bat, `app/` code, icon, thesaurus and base fonts, and the setup zips that `nobu_main._unpack_addons` names, plus the runtime parts. Run it only when the user asks (rule 1). If the tests haven't been run since the last change, say so first and ask whether to run them before building, since the copy goes to other people.

## Launcher

`launcher/main.go` is the source of `NobuNotes.exe`. It unpacks `setup/runtime.zip.00*` on first start, then runs `runtime\pythonw.exe app\nobu_main.py`. The `.syso` file holds the icon. Rebuild it only if the launcher must change: `cd launcher && go build -ldflags "-H windowsgui -s -w" -o ..\NobuNotes.exe` (from Linux, add `GOOS=windows GOARCH=amd64`). Go may not be installed on the user's computer.
