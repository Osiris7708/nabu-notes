NABU NOTES  (version 5.0.1)
===========================

Say  "Nabu, record this"  and start talking.  ("Nabu" is said "naboo".)
Say  "Nabu, end recording"  (or stay quiet for 8 seconds) to finish.
Each recording is transcribed into a new note in "Unassigned". File it into a book or
campaign whenever you like. Everything runs on this computer - no cloud, no account.

NEW IN VERSION 5.0.1
--------------------
- New icon: the gold-scrolled "NN" with a microphone, on the window, the taskbar, the tray,
  every dialog and NabuNotes.exe (and so on your desktop shortcut). If Explorer still shows
  the old icon for a while, that's Windows' icon memory - it updates on its own.
- Updating from Nobu Notes (before 5.0)? Copy the new files over your old folder and start
  NabuNotes.exe - your notes and settings move over by themselves (more in 5.0.0 below).

NEW IN VERSION 5.0.0
--------------------
- New name: Nobu Notes is now Nabu Notes, said "naboo". Say "Nabu, record this" to start
  and "Nabu, end recording" to stop (and "Nabu, edit this" / "Nabu, cut this").
  The program is NabuNotes.exe, and notes are now .nabu files.
- Updating from Nobu Notes: copy the new files over your old Nobu Notes folder and start
  NabuNotes.exe. The first time, it moves everything over by itself: your notes (.nobu
  becomes .nabu), folders, backups, Trash, settings, the "start with Windows" option, and
  shortcuts to the old NobuNotes.exe on your desktop and Start menu. The old program files
  are removed. Nothing you wrote is changed. Then run gear > Teach Nabu my voice once, so
  it learns how you say the new name (what it learned for the old name is cleared).
- Licence: Nabu Notes is free and open under the MIT licence (see LICENSE). The fonts,
  thesaurus and other parts it comes with are credited, with their own licences, in
  THIRD-PARTY-NOTICES.txt.
- Pasting keeps the font. Text pasted from another program now keeps its font and size on
  every line (before, every other line could fall back to your own font). The copied page's
  own colours - a dark page's black background and white text, or plain black text - are
  left behind, so pasted text no longer comes in highlighted. Real colours and real
  highlights are kept.
- Choose what pasted fonts change into. When a paste has a font your last paste didn't, the
  "Fonts in the pasted text" window opens, with a row for every font in the paste (one or
  several). Pick a font and size for each (or "My note font" / "My note size") and click
  Apply: the text you just pasted changes, and from then on every paste in that font changes
  by itself - no window. Pasting chapter after chapter in the same font asks only once; the
  window comes back only after a paste in a different font, with your choices filled in, so
  you can change them. Close leaves everything as it was. Your choices are also listed in
  Settings > Fonts, where you can change or remove them. (Text copied from another Nabu note
  is never changed.)
- Fonts you don't have: paste text in a font this computer doesn't have and Nabu looks for a
  free, legal copy on Google Fonts. If there is one, it's downloaded and added to your fonts
  (and the pasted text shows in it straight away). The font window says either way. Paid
  fonts, like Book Antiqua, are never downloaded - the text keeps the font's name, so it
  shows correctly on a computer that has it. Only the font's name is sent, never your
  writing. Turn it off in Settings > Fonts.
- Folder names can use any characters, including / : * ? " < > and |.
- Dragging shows where things will land: the label beside the mouse now has a second line,
  e.g. "Goes into: "The Hollow Crown > Chapters", above "Chapter 3"", "Goes to: Unassigned",
  or "Not here - let go to cancel". Files dragged in from File Explorer get a label too:
  over a note, a blue line shows where a picture will go; over a folder list, it names the
  folder documents will be imported into.

NEW IN VERSION 4.9.4
--------------------
- Choose your speech model the first time Nabu starts. Four choices, with what each needs:
    Large v3 Turbo .... the most accurate. 1.6 GB download. 8 GB memory, a 4-core processor.
    Medium (English) .. very accurate. 1.5 GB download. 8 GB memory, a 4-core processor.
    Small (English) ... good, faster. 480 MB download. 4 GB memory, any 2-core processor.
    Base (English) .... basic, fastest. 145 MB download. 4 GB memory, any processor.
  Nabu looks at your computer's memory and processor and ticks the best one it runs well.
  (Before, a new install always got Medium.) Change it any time in Settings, which now shows
  the same details. Updating an install that already has its models? Nothing to choose.

NEW IN VERSION 4.9.3
--------------------
- New icon (the window, the taskbar, the tray and NabuNotes.exe itself). If Explorer still
  shows the old icon for a while, that's Windows' icon memory - it updates on its own.
- Drag a picture anywhere on the page: as soon as you drag it, it comes loose from its line
  and follows the mouse, with the text flowing round it. Near the left edge, the middle or the
  right edge of the page it snaps there (hold Alt to place it freely). Esc while dragging puts
  it back. Ctrl + drag still moves a picture within the text (between words).
- Right-click a picture > Place on page: Top left, Top right, Middle left, Middle right,
  Bottom left or Bottom right of the page it's on.
- Settings: the "Re-learn room noise" button is gone. It did nothing you could see, because
  the noise filter already learns your room's sound by itself whenever you're not talking
  (Settings now says so). "Teach Nabu my voice" still starts by learning the room afresh.
- Place pictures anywhere on the page, with the text flowing round them line by line (like
  Word's text wrapping). Right-click a picture > Text wrapping:
    In line with text ............ as before: the picture sits in a line of text
    Square - text on the right ... the picture on the left, the text running down its right side
    Square - text on the left .... the other way round
    Square - side with more room . Nabu picks the side with more space
    Top and bottom ............... text above and below it only
    In front of text ............. the picture sits over the words; the text ignores it
  Then drag the picture anywhere: the text moves out of its way as you drag. Arrow keys nudge
  it (Shift + arrow: one pixel). Its sides and corners resize it as before. It is pinned to the
  paragraph next to it, so it moves down when you write above it. Word files get real floating
  pictures with the same wrapping; PDFs, e-books and web pages flow the text round them too.
  Copying text copies its floating pictures with it. Older versions of Nabu show these
  pictures as ordinary in-line pictures.
- Opening a folder with thousands of notes in the sidebar is instant (it used to freeze for
  several seconds the first time while Nabu read every note for its colour label; the labels
  now appear a moment later).
- Move and resize pictures with the mouse: click a picture to select it - a blue frame with
  squares on its corners and sides appears right around it (also on cropped pictures).
  * Move: drag the picture. A see-through copy follows the mouse and a blue line shows where
    it will land. Esc while dragging cancels.
  * Stretch: drag the left or right side to change only the width, the top or bottom to
    change only the height.
  * Resize: drag a corner to make it bigger or smaller and keep its shape (hold Shift to
    stretch it freely). Right-click > "Original shape" undoes stretching.
  * Sizes go from thumbnail up to the full page. Stretched pictures stay stretched in Word,
    PDF, e-book and web page exports.
  Delete removes the selected picture; Esc, typing or a click elsewhere lets go of it. Each
  move or resize is one Ctrl+Z.
- Copy a picture out of a note: right-click it > Copy picture (or select just the picture and
  press Ctrl+C). Paste it into another note, Word, an email, Paint or a chat - no need to open
  it in another program first.
- Links: paste a web address (https://... or www...) and it becomes a link. Ctrl+click it to
  open the page in your web browser (a plain click just puts the cursor there, so you can
  edit it). Text copied from a web page keeps its links. Right-click a link to open it, copy
  its address or remove the link. Links can be clicked in Word, PDF, e-book and web page
  exports too; plain text exports write the address in brackets. Spell check ignores web
  addresses, and Clear formatting keeps links.

NEW IN VERSION 4.9.2
--------------------
- Paste pictures with Ctrl+V (or right-click > Paste): screenshots, pictures copied from a web
  page (right-click the picture > Copy image), from another program, or picture files copied
  in File Explorer. Pictures copied from web pages used to paste nothing.
- Crop a picture: right-click it > Crop... Drag a box over the part you want to keep (drag
  the box to move it, or its edges to change its size), then press Crop or Enter.
  "Whole picture" starts again, Esc cancels, and Ctrl+Z brings back the whole picture
  afterwards. The original picture file is always kept.

NEW IN VERSION 4.9.1  (a full check of every button, slider and menu)
--------------------
- The notes you had open come back - with their pages and tabs - when Nabu starts.
  (Settings > Transcription & program > "Reopen the notes I had open". On by default.)
- Nabu remembers if its window was maximised.
- Esc cancels a drag (notes, folders or tabs): nothing moves.
- Ctrl+Tab / Ctrl+Shift+Tab switch tabs. Ctrl+W also works with Caps Lock on.
- New windows and questions open over the window you're working in (also a note in its own
  window, or a second screen), not always in the middle of the main screen.
- When Nabu asks before deleting something, Enter now means "no". Tab to the delete button.
- The mouse wheel scrolls the Settings page; it no longer changes a drop-down or number box
  that happens to be under the pointer. The Home page scrolls with the wheel anywhere on it.
- Tooltips wait a moment before showing, so they don't flash as you move across the toolbar.
- Change case with nothing selected changes the word at the cursor.
- Find & replace: Enter in "Replace with" replaces, Esc closes, it says when it went back to the
  top, and Ctrl+F with new words selected searches for those.
- The side-by-side button (⧉) also lists the other notes in the same book or campaign.
- Dictionary: asks before removing words; Enter saves a word.
- Fixed:
  * raised/lowered text (x² x₂) now stays in the right place when you zoom;
  * pictures are no longer kept locked by Nabu after they're shown;
  * timers of a closed window (Teach Nabu, a note's own window) could fire later by mistake;
  * the "What is it hearing?" list no longer jumps back to the top every half second;
  * the sidebar level meter can't stop updating after a hiccup;
  * right-click menus no longer pile up in memory;
  * "recordings with no transcript" now says clearly what skipping does.
- Lots of unused and duplicated code removed, and the slider for the drop highlight no longer
  writes to disk on every pixel.

NEW IN VERSION 4.9
------------------
- Side-by-side pages now line up exactly, and keep a short toolbar: style, font, size, bold, italic,
  underline. Everything else is in "More tools" on that toolbar. The full toolbar is one click away (☰).
- Right-click on the page now also has Find & replace, Next spelling mistake and Thesaurus.
- The shade that shows where a dragged note will land no longer flickers. Its colour and strength
  can be changed: Settings > Appearance > Make my own colours > Drop highlight.
- 40 colour labels for books, folders and notes (was 12), shown as a grid.
- The tutorial (gear > How to use Nabu) is rewritten: every feature, short and plain.

NEW IN VERSION 4.8
------------------
- Tabs: every note you open gets a tab above the page (close with its x, middle-click or Ctrl+W).
- Snapping inside Nabu: drag a tab onto the LEFT or RIGHT part of the page and the page splits with
  that note on that side (a blue shadow shows where). Drag it onto the middle of a page or onto its
  tabs to make it a tab there. Up to 6 pages side by side; "Join into one page" puts them back.
- Notes you haven't opened yet work the same way: drag one from the sidebar, Unassigned or a folder
  list onto the left / middle / right of the page area and it opens there when you let go - or drop
  it well outside Nabu's window to open it in its own window. Dropping a folder there opens it.
- Clicking a book's or folder's name in the sidebar now closes it again (click = open, click = close).

NEW IN VERSION 4.7
------------------
- Type without speaking: "+ New note" in Unassigned (and every folder, Ctrl+N, or right-click
  Unassigned) makes a blank note. The old "Open" button is gone - double-click a note, or
  right-click > Open.
- Several notes side by side: right-click a note > "Open side by side" (or middle-click it, or
  drag it from the sidebar onto the open page). Drag the dotted bars between them to resize;
  double-click a bar or "Even widths" to make them equal. Up to 6.
- Snapping: drag a note's name (top of its page) to the left or right side of the page area and
  it snaps there (a blue shadow shows where). Inside the Nabu window it never pops out by accident.
- Pop-out windows: drag a note's name well away from the Nabu window and it opens in its own
  window. Drag its name - or the window itself by its title bar - to the left or right edge of
  Nabu's page and it snaps back in on that side (or press the button).
- Trash: Restore and Delete permanently are on the right-click menu (the buttons are gone).
- Shift-click / Ctrl-click several books, folders or notes in the sidebar, then right-click to
  colour, move, export, open side by side or delete them all at once.
- Note titles can contain any characters, including quotation marks and / : ? * < > |.
- Smoother clicking: a folder never closes on the second click of a double-click; clicking
  Home / Unassigned / Trash always goes there; slightly shaky clicks are no longer taken as drags.
- Fixed: importing into Unassigned no longer opens folders in "Books & campaigns".
- Faster with big libraries: the sidebar only reads folders you open, lists fill in batches,
  and note previews are remembered between runs (cache\noteinfo.json). Tested with 4,500 notes.
- More accurate transcripts:
  * your dictionary names are suggested to the speech model through the WHOLE recording
    (before, only the first 30 seconds);
  * recordings keep the natural sound - the noise filter is still used to listen for commands,
    but the speech model is more accurate without it (Settings: "Transcribe from the natural
    sound", on by default; untick it to keep the filtered sound instead);
  * quiet recordings are levelled up, soft word beginnings/endings are no longer clipped, and
    a garbled or repeating stretch is automatically decoded a second time;
  * optional newest model: Settings > Transcription model > large-v3-turbo (most accurate, about
    the speed of medium, one-time 1.6 GB download).

NEW IN VERSION 4.6
------------------
- Keyboard shortcuts that work from any program (press once to start, again to stop):
    Ctrl+Alt+R  start / stop a recording
    Ctrl+Alt+E  dictate into the open note   (same as "Nabu, edit this")
    Ctrl+Alt+X  cut a passage by voice       (same as "Nabu, cut this")
  Change them in gear > Microphone, noise & settings > "Dictation, cuts & shortcuts"
  (click a shortcut and press the new key). Any single key works (F9, Insert, a number-pad
  key, even a letter - keys that normally type ask first, since Nabu takes them over everywhere
  while it runs). Esc, Enter, Tab, Backspace, Delete and Print Screen need Ctrl or Alt with them;
  the Windows key and Windows' own shortcuts can't be used. Changes are saved at once and kept after restarts.
- Same settings section: when dictation stops (after 4-20 s of quiet, or only when you
  say "Nabu, end recording" / press the shortcut), whether "cut this" asks before deleting,
  and whether dictated text is shown for you to confirm before it goes in.
- Better at hearing the voice commands the first time:
  * "Teach Nabu my voice" now trains all four commands (record, end, edit, cut), remembers
    exactly how it hears you say each one, and ends with a test where you can keep
    practising until every command gets a tick.
  * When something sounds almost like a command, Nabu listens to it a second time, more
    carefully, before giving up.
  Run "Teach Nabu my voice" once after updating to get the full benefit.
- Your own colour theme: Settings > Appearance > "Make my own colours..." (10 colours, live
  preview, start from any theme).
- Change the title at the top of a note and the note is renamed to match (sidebar, lists).
  Renaming a note also changes the title on its page.
- Fonts... > "+ Add fonts..." adds .ttf/.otf files (or a .zip of them) and they work at
  once - no restart. Adding a font you already have just says so (it used to show a
  "Permission denied" error because Windows locks fonts that are in use). Personal-use,
  trial and demo fonts are never packed into shared Word files / e-books. The tutorial
  explains it all.
- Bigger open/close triangles in the sidebar; clicking anywhere just left of a folder's
  name opens or closes it.

NEW IN VERSION 4.5
------------------
- Faster with long notes (a 60,000-word manuscript): typing never pauses to save undo steps,
  page counting is about 10x faster, loading and spell check are 3-4x faster, and notes
  with extremely long paragraphs (e.g. pasted text with no line breaks) no longer freeze.
- Undo works per burst of typing (like Word) plus per new paragraph.
- The thesaurus uses about 20 MB of memory instead of 130 MB, and the spell checker only
  loads when you open a note (less memory while Nabu waits in the tray).
- The log no longer records every speech burst (less disk writing).
- The network guard wording makes clear it only affects Nabu itself.

NEW IN VERSION 4.4
------------------
- Tutorial: Home > Help > "How to use Nabu - the full tutorial" (also in the gear menu).
- Drag & drop in the sidebar: drag any note or folder onto a folder to put it inside; onto
  the top/bottom edge of another item (blue line) to place it above/below; next to a
  book/campaign to make it a book/campaign; onto "Unassigned" to send notes back; onto
  "Trash" to delete. Hovering over a closed folder opens it. You can also drag from the
  folder lists and from Unassigned. Your order is remembered.
- Settings: the "Names & unusual words" box was removed - My dictionary does the same job
  and more (it also corrects the spelling). Anything you had typed in that box was moved
  into My dictionary automatically.

NEW IN VERSION 4.3
------------------
- Sidebar edge: the drag handle is now a wide strip with grip dots (it lights up when the
  mouse is over it). Drag anywhere on it; double-click it to fit the longest name.
- Headings and note titles now use Eagle Lake (by Astigmatic), a free font under the SIL
  Open Font License - you can share your notes, Word files, PDFs and e-books with friends
  and the font goes with them. Varnyx stays available in the font lists if you want it for
  yourself. 8 more free fonts were added (Texturina, Almendra Display, Kings, Lancelot,
  Fruktur, Germania One, Macondo Swash Caps, Rye) - 72 in total. Licence texts are in
  app\fonts\lib.
- Colour themes (gear > Microphone, noise & settings > Appearance): Dark (classic),
  Midnight blue, Ember (warm dark), Forest, Parchment (light), Light and High contrast.
  Nabu restarts itself to switch.
- Private by design: the Home page now says so, and Nabu enforces it - while it runs, Nabu's
  own network connections are blocked (logged in logs\nabu.log). This only affects Nabu;
  Windows and your other programs are not touched. The only exceptions are downloading the
  speech models (first start / changing models), which only downloads, and (since 4.9.5) free
  fonts for pasted text in a font you don't have.
- Any screen size: the window is fitted to the screen it opens on (no more off-screen or
  too-big windows after changing monitors or resolution), the Home page scrolls when it
  doesn't fit, and every dialog sizes itself to your display scaling.

NEW IN VERSION 4.2
------------------
- The left sidebar can be resized: drag its right edge (it lights up blue under the
  mouse). Double-click the edge to fit the longest name. The width is remembered.
- Folder lists have more space between rows and alternating shading. The date and
  time (12-hour, e.g. "Oct 21, 2026   3:05 PM") are on the left; the note name and its
  first words are centred.
- Opening a recording that still has its automatic date name asks you for a title.
  "Save title" renames the note and puts the title, centred, at the top of the page.
  "Later" asks again next time; "Don't ask for this note" stops asking.
- The Title style is centred by default (you can still align it left or right).
  New notes start with their name as a centred Title.
- Colour labels: right-click a book/campaign, sub-folder or note (in the sidebar or in a
  folder list) > "Colour label". The colour shows only in the sidebar and folder lists -
  never inside the note itself. "No colour" removes it.

NEW IN VERSION 4.1
------------------
- The page sits in the middle of the window.
- Note text is 12 pt by default (headings scale with it). Change it in Settings > Fonts.
- Mouse wheel ON the page scrolls; mouse wheel BESIDE the page (the dark margins) zooms.
  Ctrl + wheel on the page zooms too.
- NabuNotes.exe has its own icon (quill, book and voice waves). If Windows still shows
  the old icon for a while, that's its icon cache - it updates on its own.

NEW IN VERSION 4 - NABU IS NOW A WRITING APP TOO
-----------------------------------------------
The page
- Notes are laid out like a Word page: 8.5" wide with 1" margins, so lines break where
  they would in Word. When the text runs past the bottom of a page, the next page starts
  ("Page 2" shows in the margins). The page buttons at the bottom (1 2 3 ...) jump to a
  page. Zoom is next to them ("Fit width", 50% - 200%, or the mouse wheel beside the page).
- Note text is IM Fell English 12 pt (the standard manuscript size) in Word's "Normal" style (8 pt after each
  paragraph, 1.08 line spacing).

The toolbar (it wraps onto more rows when the window is narrow)
- Style: Normal, Title, Subtitle, Heading 1-3, Quote - the same names as Word, and they
  become real Word styles when exported.
- Font, size, A+ / A- (Ctrl+] / Ctrl+[), "Fonts..." opens the font browser.
- B I U S, superscript (Ctrl+Shift+=), subscript (Ctrl+=), text colour, highlight,
  change case (Aa), Clear formatting (Ctrl+Space), format Painter.
- Find & replace (Ctrl+F / Ctrl+H), Spelling (F7), Thesaurus (Shift+F7).
- Align left / centre / right / justify (Ctrl+L / E / R / J). Justified text shows as
  left-aligned on screen but is fully justified in Word and PDF exports.
- Spacing menu: line spacing, space before / after, first-line indent, and one-click
  "Manuscript format" (double-spaced, indented).
- Indent / outdent, bullet and numbered lists (Tab / Shift+Tab change the list level;
  Enter on an empty item ends the list).
- Table, Picture, Page break (Ctrl+Enter), Symbol (dashes, quotes, accents, runes...),
  Date. Right-click a table cell to add / delete rows and columns.
- Ctrl+Z / Ctrl+Y undo and redo everything, formatting included.
- Anything you can also do by voice has the phrase written under it, e.g.
  "Dictate here (Nabu, edit this)", "Cut by voice (Nabu, cut this)",
  "Record (Nabu, record this)".

Spell check and thesaurus (both work offline)
- Misspelled words get a red underline. Right-click one for suggestions, "Add to
  spelling dictionary" or "Ignore all". Words in My dictionary (your fantasy names) are
  never marked wrong.
- Right-click any word > "Synonyms for ..." to swap it for a synonym.

Copy and paste
- Copying from Nabu into Word, Google Docs or an email keeps fonts, sizes, colours and
  pictures. Pasting from Word or a web page into Nabu keeps them too. Right-click >
  "Paste as plain text" when you only want the words.

Fonts
- 64 free fonts come with Nabu (gear > Fonts..., or "Fonts..." on the toolbar):
  Fantasy & medieval, Book & manuscript, Handwriting & script, Gothic & horror,
  Typewriter, Clean & modern - plus every font already on Windows.
- Nabu also installs its fonts into Windows for your user account (no admin needed), so
  Word and other programs show the same fonts. Untick this in the font browser if you
  don't want it.
- Your own fonts: put .ttf / .otf files in the "fonts" folder and restart Nabu.

Export / share  (button at the top of a note, in every folder, or right-click)
- Choose a note, the selected notes, or a whole folder (with its sub-folders), then:
    Word document (.docx)  - editable; Nabu's styles become Word styles, and the fonts are
                             packed inside the file so it looks the same on their PC.
    PDF (.pdf)             - looks identical everywhere; best for sending and printing.
    E-book (.epub)         - one chapter per note, for e-readers and book apps.
    Web page (.html) or plain text (.txt).
- Options: page numbers, each note on a new page, note names as chapter headings, and
  whether to include Nabu's grey dates / "Play recording" links (left out by default).
- About Varnyx: its free demo licence is personal-use only and forbids packing it into
  files, so Word files / e-books / web pages leave it out (other people see a standard
  heading font). PDFs keep it exactly.

Import
- "Import documents..." in Unassigned and every folder (or right-click a folder in the
  sidebar > "Import documents here", or drag files onto a list). Word (.docx),
  OpenDocument (.odt), PDF (text only), web pages, Markdown, rich text (.rtf) and .txt.
  Each document becomes a note in that folder, with its formatting, tables and pictures.
  You can keep the document's own fonts, or switch it to your Nabu fonts.

First start after this update unpacks the new writing tools (about 15 seconds, once).

NEW IN VERSION 3.2
------------------
- Sub-folders: inside any book or campaign, click "+ New sub-folder" (or right-click a
  folder in the sidebar > "New sub-folder here"). Folders can go as deep as you like
  (e.g. The Hollow Crown > Characters > Villains). "Move to" menus show the whole tree,
  so transcripts can be filed straight into a sub-folder. Folders can be renamed, moved
  into other folders, and deleted to Trash (and restored) like notes.
- Fonts: note text uses IM Fell English (an old printed-book typeface), headings and
  titles use your Varnyx font, and the sidebar, folders, buttons and settings use
  Grenze (a sharp, slightly blackletter fantasy face). IM Fell and Grenze are free
  (SIL Open Font License).
  Settings > Fonts lets you pick any font for text, headings and the interface, and the
  text size. (The interface font fully applies after restarting Nabu.)
  To add more fonts, put .ttf or .otf files in the "fonts" folder and restart Nabu.
  Note: your Varnyx download is a free DEMO for personal use only, and it has no
  punctuation or numbers - that's why it is used for headings only. If you buy the full
  version, drop it into the "fonts" folder in place of the demo.

NEW IN VERSION 3
----------------
- Right-click any transcript (in Unassigned or a project list): Open & edit text, Rename,
  Move to book / campaign, or Delete. Ctrl/Shift-click to act on several at once.
- Voice editing inside an open note (only works while a note is open and the Nabu window
  is in front):
    "Nabu, edit this"  - dictate; the words go in at the text cursor (or replace the
                           highlighted text). Finish with a pause or "Nabu, end recording".
    "Nabu, cut this"   - then recite the passage. Nabu highlights the closest match in red
                           and asks Delete / Cancel. Ctrl+Z brings it back.
  The same is on the note toolbar: "Dictate here" and "Cut by voice", and on the
  right-click menu inside a note.
- My dictionary (gear menu, Home, or right-click a selected word > "Add to my dictionary"):
  type the spelling you want (e.g. Kryptik), then press Record and say the word 2-3 times.
  Nabu learns how the speech model hears you ("kripke", "krip key"...) and from then on
  replaces those with your spelling in every transcript, dictation and cut. You can also
  type sound-alikes by hand. "Fix the open note now" applies it to an existing note.
- Trash (left sidebar): deleted notes and projects go here together with their audio.
  Right-click > Restore puts everything back. Right-click > Delete permanently (or
  "Empty trash") sends it to the Windows Recycle Bin.
- Fixed: "Teach Nabu my voice" from the Settings window now opens properly.

FIRST START AFTER UPDATING
--------------------------
- If Nabu Notes is already running, right-click its tray icon (near the clock) > Quit,
  then double-click NabuNotes.exe again.
- It downloads one more small speech model (about 145 MB, once) that is much better at
  hearing "Nabu".
- Then open the gear button (bottom-left) > "Teach Nabu my voice". It takes a minute:
  it learns your room's background noise, listens to you say both phrases, and suggests
  a microphone gain. Do this once, and again if you move the microphone.

THE WINDOW
----------
Left side:
  Home              status, what's waiting, recently edited notes
  Unassigned (n)    new transcripts. Select one or several (Ctrl/Shift-click) and use
                    "Move selected to project" - or open one, edit it, then "Move to project".
  BOOKS & CAMPAIGNS click + to make a folder for each book or campaign. Click a folder to
                    see its notes; right-click for New note / Rename / Delete.
  Bottom            live mic level, Record / Stop, Pause listening, gear menu.
Notes: a Word-style page with the full toolbar described above. Pictures: Picture button,
Ctrl+V, or drag a file in; right-click a picture to resize. Everything saves automatically.
Deleting moves things (with their audio) to Trash - nothing is destroyed outright.

MICROPHONE, NOISE FILTER AND GAIN  (gear > Microphone, noise & settings)
------------------------------------------------------------------------
- Gain: makes the mic louder or quieter. Keep the top meter mostly green; if it says
  TOO LOUD, lower it.
- Noise filter: removes steady background noise (PC fan, AC, hum). 60% is a good start.
  Use "Record a 6-second test" to hear exactly what Nabu hears, and adjust. It learns your
  room's sound by itself whenever you're not talking (a fan switched on or off is picked up
  within a second or two), so there is nothing to press when the room changes.
- Speech sensitivity: how readily a sound counts as your voice. Raise it if Nabu misses
  you; lower it if it reacts to other sounds.
Slider changes are heard live; press Save to keep them.

WHILE RECORDING
---------------
A small badge at the top of the screen shows it's recording. If you go quiet it counts
down ("stopping in 5 s unless you keep talking") so you're never cut off by surprise.
Pauses to think are fine. Only real silence for the set time (8 s) ends it.

IF IT DOESN'T REACT TO "NABU, RECORD THIS"
--------------------------------------------
1. Gear > "What is it hearing?" - speak the phrase and see what the model heard.
   A tick means it counted. The "After noise filter" bar should jump when you talk.
2. Run "Teach Nabu my voice" again.
3. In Settings: lower "Wake word strictness" a little, or raise "Speech sensitivity".
4. For troubleshooting, tick "Save what it hears" in the diagnostics window. Short clips
   are kept in logs\heard so they can be checked.

FOLDERS (all inside "Nabu Notes")
---------------------------------
  Notes\Unassigned\   new transcripts
  Notes\<project>\    your books and campaigns
  Recordings\         all audio (.wav, cleaned by the noise filter) + a .txt of each transcript
  Images\             copies of pictures you added
  models\  logs\      speech models; nabu.log for troubleshooting
  app\ setup\ runtime\ NabuNotes.exe   the program itself (leave these alone)

TRANSCRIPTION SPEED
-------------------
You pick the model the first time Nabu starts (Large v3 Turbo is the most accurate; Small and
Base are lighter for older PCs). Switch any time in Settings > Transcription model. The audio
is always saved first, so nothing is lost while it works. Put character and place names in
My dictionary (gear menu) so they are spelled right.

TROUBLESHOOTING
---------------
Run "Debug - show errors.bat" and look at logs\nabu.log. To start the program fresh,
delete the "runtime" folder - it unpacks again from "setup".
