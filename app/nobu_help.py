"""The tutorial window (Home page > "How to use Nobu")."""
import tkinter as tk
from tkinter import ttk

import nobu_theme as T
from nobu_config import STOP_PHRASE, WAKE_PHRASE

# (section title, [(kind, text)])  kind: p = paragraph, b = bullet, h = small heading, k = key/phrase line
# Written to be short and plain. Update it whenever a feature is added or changed.
SECTIONS = [
    ("Start here", [
        ("p", "Nobu Notes turns your voice into written notes, and is also a full writing app. Everything stays "
              "on this computer."),
        ("b", "Say “%s” (say it “no-boo”), then talk." % WAKE_PHRASE),
        ("b", "Stop talking for 8 seconds, or say “%s”." % STOP_PHRASE),
        ("b", "Your words appear as a new note in Unassigned."),
        ("b", "Open it, give it a title, and move it into a book or campaign."),
        ("b", "Settings, tools and this tutorial are in the ⚙ button at the bottom left."),
    ]),
    ("Recording by voice", [
        ("k", "“%s”  —  start recording" % WAKE_PHRASE),
        ("k", "“%s”  —  stop recording" % STOP_PHRASE),
        ("k", "“Nobu, edit this”  —  type by voice into the open note"),
        ("k", "“Nobu, cut this”  —  delete a passage from the open note"),
        ("b", "Say the whole phrase, pause briefly, then start talking. A rising beep means recording started; a "
              "falling beep means it stopped."),
        ("b", "Recording stops after 8 seconds of silence. A small badge at the top of the screen counts down."),
        ("b", "The command phrases are never written into your notes."),
        ("b", "Turning speech into text happens on your computer, so it takes a moment. Progress shows at the "
              "bottom of the window."),
        ("b", "No voice? Use the ● Record button (bottom left) or Ctrl+Alt+R. Press again to stop."),
        ("b", "❚❚ pauses listening (for calls or music). ▶ resumes."),
        ("b", "Each recording's sound is kept. Click “▶ Play recording” at the top of a transcript to hear it."),
        ("b", "⚙ > Transcribe an audio file… turns an existing sound file into a note."),
    ]),
    ("Writing without speaking", [
        ("b", "“+ New note” (in Unassigned or any folder) makes a blank note to type into. Ctrl+N does the same."),
        ("b", "A new note goes into the folder you're looking at, or into Unassigned."),
        ("b", "Titles can use any characters, including quotes, / and ?."),
    ]),
    ("Unassigned & titles", [
        ("b", "Unassigned is your inbox. Every recording lands here first, newest at the top."),
        ("b", "The first time you open a recorded note, Nobu asks for a title. “Later” asks again next time; "
              "“Don't ask for this note” stops asking."),
        ("b", "The title at the top of the page and the note's name stay the same: change one and the other "
              "follows."),
        ("b", "To file notes: select them and click “Move selected to project”, right-click > Move to, or drag "
              "them onto a folder in the sidebar."),
        ("b", "Open a note: double-click it, press Enter, or right-click > Open."),
    ]),
    ("Books, folders & the sidebar", [
        ("b", "Books & campaigns are the top folders in the sidebar. Click + to make one."),
        ("b", "Right-click a folder > New sub-folder here, to make folders inside it (as many levels as you like)."),
        ("b", "Click a folder's name to open it; click it again to close it. The triangle does the same."),
        ("b", "Shift-click selects a range; Ctrl-click adds or removes one. Right-click the selection to colour, "
              "move, export, open or delete them all at once."),
        ("b", "Right-click > Colour label gives a folder or note one of 40 colours (or your own). Colours only show "
              "in the sidebar and lists, never inside the note."),
        ("b", "Drag the dotted strip on the sidebar's right edge to make it wider. Double-click it to fit the "
              "longest name."),
        ("h", "Dragging in the sidebar"),
        ("b", "Drop onto a folder (it lights up) to put the item inside it."),
        ("b", "Drop on the top or bottom edge of an item (a blue line shows) to place it above or below. Your "
              "order is remembered."),
        ("b", "Hold over a closed folder for a moment to open it."),
        ("b", "Drop notes on Unassigned to send them back, or on Trash to delete them."),
        ("b", "Changed your mind mid-drag? Press Esc. Nothing moves."),
    ]),
    ("Tabs & side-by-side pages", [
        ("b", "Each note you open gets a tab above the page. Click a tab to switch."),
        ("b", "Close a tab with its ✕, a middle-click or Ctrl+W. Notes are saved first."),
        ("b", "Ctrl+Tab / Ctrl+Shift+Tab (or Ctrl+Page Down / Up) move between tabs. Right-click a tab for more "
              "options."),
        ("b", "The notes you had open come back, with their pages and tabs, the next time Nobu starts. (Turn "
              "this off in Settings.)"),
        ("h", "Putting notes side by side"),
        ("b", "Drag a tab to the left or right part of the page. A coloured shade shows where it will land. Let go "
              "and the page splits."),
        ("b", "Drag a tab onto the middle of another page, or onto its tabs, to make it a tab there."),
        ("b", "Notes you haven't opened work the same way: drag one from the sidebar or a list onto the page area."),
        ("b", "Also: right-click a note > Open side by side, middle-click it, or the ⧉ button above a page "
              "(it lists the notes in the same folder and book, and recent ones)."),
        ("b", "Press Esc while dragging a tab to cancel."),
        ("b", "Up to 6 pages fit. Drag the dotted bars between them to resize. Double-click a bar, or “⇔ Even "
              "widths”, to make them equal. “Join into one page” turns them back into tabs."),
        ("b", "Side-by-side pages show a shorter toolbar: style, font, size, bold, italic, underline. Everything "
              "else is under “▾ More tools”. ☰ switches between the short and the full toolbar."),
        ("b", "The page you clicked last has a coloured line on top. Voice editing goes there."),
        ("h", "A note in its own window"),
        ("b", "Drag a tab (or a note from a list) well outside Nobu's window, or press ⇱. It opens in its own "
              "window you can move anywhere, even to another screen."),
        ("b", "To put it back: drag its name onto Nobu's page, drag the window to the left or right edge of "
              "Nobu's page, or press ⇲."),
        ("b", "You can change the shade's colour and strength: ⚙ > Settings > Appearance > Make my own colours > "
              "Drop highlight."),
    ]),
    ("Writing tools", [
        ("p", "The page works like Microsoft Word, and looks the same when exported."),
        ("b", "Styles (Normal, Title, Headings, Quote…), fonts, sizes, bold, italic, underline, strikethrough, "
              "superscript, subscript."),
        ("b", "Text colour, highlight, change case (UPPER, lower…; with nothing selected it changes the word at "
              "the cursor), clear formatting."),
        ("b", "Format painter: click it, then select text to copy the formatting onto it."),
        ("b", "Alignment, line and paragraph spacing (including a manuscript preset), indents, bullet and "
              "numbered lists (Tab / Shift+Tab change the level)."),
        ("b", "Insert: tables (right-click a cell to add or remove rows and columns), pictures, page breaks, "
              "symbols, today's date."),
        ("b", "Pictures: use the Picture button, drag a file in, or paste with Ctrl+V - a screenshot, a picture "
              "copied from a web page (right-click it > Copy image) or from another program, or picture files "
              "copied in File Explorer."),
        ("b", "Click a picture to select it: a blue frame with squares on its corners and sides appears."),
        ("b", "Move it: drag the picture anywhere on the page - it comes loose from its line and the text flows "
              "round it. Near the left edge, the middle or the right edge it snaps there (hold Alt to stop it "
              "snapping). Esc while dragging cancels."),
        ("b", "Ctrl + drag moves a picture within the text instead (a blue line shows where it will land)."),
        ("b", "Right-click a picture > Place on page: top, middle or bottom of the page, left or right."),
        ("b", "Resize it: drag a side to make it wider, narrower, taller or shorter. Drag a corner to make it "
              "bigger or smaller and keep its shape (hold Shift to stretch it freely). Right-click > Original "
              "shape undoes stretching."),
        ("b", "Delete removes the selected picture; Esc or a click elsewhere lets go of it. Ctrl+Z undoes any "
              "move or resize."),
        ("b", "Place a picture anywhere on the page: right-click it > Text wrapping. Square = text beside it "
              "(on the right, on the left, or whichever side has more room). Top and bottom = text above and "
              "below only. In front of text = it sits over the words. In line with text = back to normal."),
        ("b", "A floating picture: drag it anywhere - the text moves out of its way as you go. Arrow keys nudge "
              "it (Shift + arrow: a tiny step). It stays with its paragraph when you write above it, and Word, "
              "PDF, e-book and web page exports keep it in place."),
        ("b", "Right-click a picture to copy it (paste it into another note, Word, an email or a chat), pick a "
              "set size, or Crop… to keep only part of it: drag a box over the part you want (drag the box to "
              "move it, its edges to resize it), then Crop. Ctrl+Z undoes it."),
        ("b", "Links: paste a web address and it becomes a link (blue, underlined). Ctrl+click it to open the "
              "page in your web browser. Text copied from a web page keeps its links. Right-click a link to open "
              "it, copy its address or remove the link. Links still work in Word, PDF, e-book and web page "
              "exports."),
        ("b", "Spelling: a red wavy line marks a possible mistake. Right-click for suggestions, add the word, or "
              "ignore it. F7 jumps to the next one."),
        ("b", "Thesaurus: right-click a word > Synonyms, or Shift+F7."),
        ("b", "Find & replace: Ctrl+F. Enter finds the next match (it carries on from the top); Enter in "
              "“Replace with” replaces it. Esc closes."),
        ("b", "Right-click the page for: cut, copy, paste, paste as plain text, picture, table, find, spelling, "
              "thesaurus and voice editing."),
        ("b", "Pages: a new page starts when text reaches the bottom. Buttons at the bottom jump between pages."),
        ("b", "Mouse wheel on the page scrolls; beside the page it zooms. Ctrl + wheel zooms too."),
        ("b", "Click the word count (bottom) for full counts."),
        ("b", "⋯ (top right of a note): word count, show the file, delete."),
        ("b", "Notes save themselves a few seconds after you stop typing. Ctrl+Z undoes, Ctrl+Y redoes."),
        ("b", "Justified text looks left-aligned in Nobu but is justified in Word and PDF."),
    ]),
    ("Voice editing", [
        ("p", "Works only while a note is open and Nobu's window is in front, so nothing changes by accident."),
        ("h", "“Nobu, edit this”  (● Dictate here, Ctrl+Alt+E)"),
        ("b", "Click where the words should go, then say the phrase and talk. Selected text gets replaced."),
        ("b", "New words flash green for a moment."),
        ("b", "It stops after 8 seconds of quiet, or when you say “%s”." % STOP_PHRASE),
        ("h", "“Nobu, cut this”  (✂ Cut by voice, Ctrl+Alt+X)"),
        ("b", "Say the phrase, then read out the passage to delete. Nobu marks the closest match in red and asks "
              "before deleting. Ctrl+Z brings it back."),
        ("h", "Options (⚙ > Settings > Dictation, cuts & shortcuts)"),
        ("b", "How long a quiet pause ends dictation, or only stop when you say so."),
        ("b", "Show dictated words first and let you Insert or Discard them."),
        ("b", "Turn off the question before a cut."),
    ]),
    ("Keyboard shortcuts", [
        ("k", "Ctrl+Alt+R  record / stop      Ctrl+Alt+E  dictate      Ctrl+Alt+X  cut by voice"),
        ("p", "These three work from any program. Change them in ⚙ > Settings > Dictation, cuts & shortcuts: "
              "click one and press the new key."),
        ("b", "A single key is fine (F9, Insert, a number-pad key, even a letter). Keys that normally type ask "
              "first, because Nobu takes that key over everywhere while it runs."),
        ("b", "Esc, Enter, Tab, Backspace, Delete and Print Screen need Ctrl or Alt with them. The Windows key "
              "and Windows' own shortcuts can't be used."),
        ("h", "In a note"),
        ("k", "Ctrl+B / I / U  bold, italic, underline      Ctrl+L / E / R / J  align"),
        ("k", "Ctrl+F  find & replace      F7  spelling      Shift+F7  synonyms"),
        ("k", "Ctrl+Enter  page break      Ctrl+] / Ctrl+[  bigger / smaller text      Ctrl+Space  clear formatting"),
        ("k", "Ctrl+N  new note      Ctrl+W  close tab      Ctrl+Tab / Ctrl+Shift+Tab  next / previous tab"),
        ("k", "Ctrl+Z  undo      Ctrl+Y  redo      Ctrl+S  save now"),
        ("h", "Everywhere"),
        ("k", "Esc  cancel a drag, or close a small window      Enter  the highlighted button"),
        ("b", "When Nobu asks before deleting, Enter means “no”. Press Tab to reach the delete button."),
    ]),
    ("Teach Nobu your voice", [
        ("p", "Do this once if Nobu misses your commands or reacts to the TV. It takes about two minutes."),
        ("b", "⚙ > Teach Nobu my voice. It listens to your room, then asks you to say each command a few times."),
        ("b", "It remembers how it hears your voice and accepts that from then on."),
        ("b", "At the end, test any command: ✔ or ✘. If one fails, say it a few more times; it keeps learning."),
        ("b", "Run it again after moving the microphone or changing rooms. Earlier learning is kept."),
        ("b", "⚙ > What is it hearing? shows, live, what Nobu thinks you said."),
    ]),
    ("My dictionary (names & spellings)", [
        ("p", "For names and invented words the speech engine gets wrong."),
        ("b", "⚙ > My dictionary. Type the word as you want it spelled, press Record and say it 2–3 times."),
        ("b", "Nobu then fixes how it mishears that word in every new recording, dictation and cut."),
        ("b", "Dictionary words are never marked as spelling mistakes."),
        ("b", "“Fix the open note now” applies the dictionary to an existing note."),
        ("b", "Quick way: select a word in a note, right-click > Add to my pronunciation dictionary."),
    ]),
    ("Microphone & listening settings", [
        ("p", "⚙ > Microphone, noise & settings."),
        ("b", "Device: which microphone to use."),
        ("b", "Gain: louder or quieter. Keep the meter mostly green."),
        ("b", "Noise filter: removes steady background sound (fans, air conditioning) while listening for "
              "commands. It learns your room's sound by itself whenever you're not talking."),
        ("b", "Speech sensitivity: raise it if Nobu stops while you're still talking quietly."),
        ("b", "“Record a 6-second test” lets you hear what Nobu hears."),
        ("b", "Stop after silence: how many quiet seconds end a recording."),
        ("b", "Wake word strictness, and “Also accept just ‘record this’”: how sure Nobu must be that it heard "
              "“Nobu”."),
        ("b", "Beeps on start and stop can be turned off."),
        ("b", "The mouse wheel scrolls the Settings page. It never changes a setting by accident."),
    ]),
    ("Getting the most accurate text", [
        ("b", "Add names to My dictionary. They help through the whole recording."),
        ("b", "Keep “Transcribe from the natural sound” ticked (Settings). The speech engine understands "
              "unfiltered sound better."),
        ("b", "Transcription model: you pick it the first time Nobu starts - the best one for your computer is "
              "already ticked. Change it any time in Settings (a new one downloads once)."),
        ("b", "large-v3-turbo: most accurate, needs 8 GB memory and a 4-core processor. medium.en: very "
              "accurate, the same. small.en: good, 4 GB. base.en: basic, fastest, runs on anything."),
        ("b", "Wake word model: base.en is more reliable; tiny.en is lighter on older computers."),
    ]),
    ("Export & import", [
        ("b", "“⇧ Export / share” (top of a note, in folders, or right-click): Word, PDF, e-book (.epub), web "
              "page or plain text."),
        ("b", "Export one note, several, or a whole folder. Each note can start on a new page with its name as a "
              "heading. Page numbers are optional."),
        ("b", "Word files carry their fonts, so they look right on other computers."),
        ("b", "Grey dates and “Play recording” links are left out unless you tick the option."),
        ("b", "Copying text into Word, email or Google Docs keeps formatting and pictures."),
        ("b", "Import documents (button in Unassigned or a folder, ⚙ menu, or drag files onto a list): Word, PDF, "
              "web pages, Markdown, RTF and text become notes. Choose to keep their fonts or use yours."),
    ]),
    ("Fonts", [
        ("b", "72 free fonts come with Nobu. Fonts… (toolbar or ⚙) shows them by style with previews."),
        ("b", "Use a font on selected text, or set it as your note, heading or interface font. Settings > Fonts "
              "also sets the text size."),
        ("b", "Nobu installs its fonts into Windows, so Word has them too."),
        ("h", "Adding your own"),
        ("b", "Download a font (.ttf, .otf or a .zip), then Fonts… > “+ Add fonts…”. It works straight away."),
        ("b", "Check the licence before sharing: “personal use” fonts are left out of Word files and e-books."),
        ("b", "PDF export needs .ttf fonts; .otf fonts are swapped for a standard font in PDFs."),
    ]),
    ("Colours & themes", [
        ("b", "Settings > Appearance: Dark, Midnight blue, Ember, Forest, Parchment, Light, High contrast. Nobu "
              "restarts to switch."),
        ("b", "“Make my own colours…”: pick 10 colours with a live preview, starting from any theme."),
        ("b", "In the same window, “Drop highlight” sets the colour and strength of the shade shown when dragging "
              "notes. This changes right away, for every theme."),
    ]),
    ("Trash & backups", [
        ("b", "Deleting moves notes and folders, with their recordings, to Trash. Nothing is lost."),
        ("b", "In Trash, right-click > Restore puts items back where they were. Select several first to restore "
              "them together."),
        ("b", "Right-click > Delete permanently, or “Empty trash”, sends items to the Windows Recycle Bin."),
        ("b", "Nobu also keeps one backup copy of every note (Notes\\.backups)."),
    ]),
    ("Running in the background", [
        ("b", "Closing the window keeps Nobu listening. Its icon sits by the clock; right-click it > Quit to stop "
              "completely."),
        ("b", "Settings can start Nobu when Windows starts, or make closing the window quit instead."),
        ("b", "Opening Nobu while it's already running just shows the window."),
        ("b", "Nobu remembers its window size and place, and whether it was maximised."),
    ]),
    ("Privacy", [
        ("b", "Recordings, text and notes are made and stored only on this computer. No account, no cloud."),
        ("b", "Nobu blocks itself from the internet while it runs. The only exception: downloading speech "
              "engines (first start, or when you pick a new one), which only downloads."),
        ("b", "This block applies to Nobu only. Other programs and Windows are not affected."),
        ("b", "Home > “How is this checked?” shows how many of Nobu's own connection attempts were blocked."),
    ]),
    ("Where your files are", [
        ("k", "Notes  —  your notes"),
        ("k", "Recordings  —  recordings (.wav) and their raw text (.txt)"),
        ("k", "Images  —  pictures in your notes"),
        ("k", "fonts  —  fonts you added"),
        ("k", "models  —  speech engines"),
        ("k", "logs  —  diagnostics"),
        ("b", "To back everything up, copy the whole Nobu Notes folder."),
        ("b", "⚙ > Open Recordings folder / Open log file."),
    ]),
    ("If something's wrong", [
        ("h", "Doesn't react to “%s”" % WAKE_PHRASE),
        ("b", "The dot under “Nobu Notes” should be green (Listening). Then run Teach Nobu my voice."),
        ("h", "Stops while I'm still talking"),
        ("b", "Raise Speech sensitivity or lower the noise filter."),
        ("h", "Gets names wrong"),
        ("b", "Add them to My dictionary."),
        ("h", "“Edit this” or “Cut this” does nothing"),
        ("b", "Open a note and click on Nobu's window first."),
        ("h", "Anything else"),
        ("b", "⚙ > Open log file shows what happened."),
    ]),
]


class TutorialWindow:
    def __init__(self, root):
        sc = T.ui_scale(root)
        w = self.win = T.toplevel(root, "How to use Nobu Notes", int(980 * sc), int(680 * sc))
        top = ttk.Frame(w, padding=(18, 14, 18, 6))
        top.pack(fill="x")
        ttk.Label(top, text="How to use Nobu Notes", style="Title.TLabel").pack(anchor="w")
        bottom = ttk.Frame(w, padding=(18, 6, 18, 14))
        bottom.pack(side="bottom", fill="x")
        ttk.Button(bottom, text="Close", style="Accent.TButton", command=w.destroy).pack(side="right")
        mid = ttk.Frame(w, padding=(18, 0))
        mid.pack(fill="both", expand=True)
        self.toc = ttk.Treeview(mid, show="tree", selectmode="browse")
        self.toc.column("#0", width=int(330 * sc), stretch=False)
        self.toc.pack(side="left", fill="y")
        box = tk.Frame(mid, bg=T.EDITOR)
        box.pack(side="left", fill="both", expand=True, padx=(12, 0))
        sb = ttk.Scrollbar(box, orient="vertical")
        sb.pack(side="right", fill="y")
        t = self.text = tk.Text(box, wrap="word", bg=T.EDITOR, fg=T.FG, relief="flat", bd=0, highlightthickness=0,
                                padx=int(22 * sc), pady=int(16 * sc), font=(T.UI_FAMILY, T.UI_SIZE + 1),
                                yscrollcommand=sb.set, cursor="arrow", spacing3=int(4 * sc))
        t.pack(fill="both", expand=True)
        sb.configure(command=t.yview)
        t.tag_configure("title", font=(T.UI_FAMILY, T.UI_SIZE + 6, "bold"), foreground=T.FG,
                        spacing1=int(18 * sc), spacing3=int(8 * sc))
        t.tag_configure("h", font=(T.UI_FAMILY, T.UI_SIZE + 2, "bold"), foreground=T.ACCENT,
                        spacing1=int(10 * sc), spacing3=int(4 * sc))
        t.tag_configure("p", lmargin1=0, lmargin2=0, spacing3=int(8 * sc))
        t.tag_configure("b", lmargin1=int(10 * sc), lmargin2=int(28 * sc), spacing3=int(5 * sc))
        t.tag_configure("k", font=(T.UI_FAMILY, T.UI_SIZE + 1), foreground=T.ACCENT, lmargin1=int(10 * sc),
                        lmargin2=int(10 * sc))
        for i, (title, body) in enumerate(SECTIONS):
            mark = "sec%d" % i
            t.mark_set(mark, "end-1c")
            t.mark_gravity(mark, "left")
            t.insert("end", title + "\n", ("title",))
            for kind, txt in body:
                if kind == "b":
                    t.insert("end", "•\t" + txt + "\n", ("b",))
                else:
                    t.insert("end", txt + "\n", (kind,))
            self.toc.insert("", "end", iid=mark, text="  " + title)
        t.configure(state="disabled", tabs=(int(28 * sc),))
        self.toc.bind("<<TreeviewSelect>>", self._jump)
        self.toc.selection_set("sec0")
        T.fit(w)

    def _jump(self, _e=None):
        sel = self.toc.selection()
        if sel:
            self.text.yview(sel[0])
