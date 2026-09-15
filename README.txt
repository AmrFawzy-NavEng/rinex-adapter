RINEX-ADAPTER v1.0
==================

Version: 1.0
Release date: 2026-09-08

A tool to adapt RINEX 3.x observation file headers and epochs. It can edit or
insert header records, apply a time filter, thin the sampling interval, and do
the same header edits over many files at once (batch mode).

Part of the PCC software suite developed at the Institut für Erdmessung (IfE),
Leibniz Universität Hannover.

Developers:
  Amr Fawzy, M.Sc.
  Dr.-Ing. Johannes Kröger


CITATION
--------
If you use this software, please cite:

  Kröger, J., Kersten, T. & Schön, S. PCC-Explorer: An open-source software
  tool to assess the impact of GNSS antenna phase center corrections on
  geodetic parameters. GPS Solut 30, 93 (2026).
  https://doi.org/10.1007/s10291-026-02056-2

A DOI for this program itself is planned with the v2.0 release of the suite;
until then please cite the paper above.


QUICK START
-----------
1. Double-click  launch_gui.bat  (or RINEX-Adapter.exe)
2. Select a RINEX observation file (top "Browse..." button)
3. Choose a tab and make your change
4. Check where the result will be written - see WHERE THE RESULTS GO below


WHERE THE RESULTS GO
--------------------
A checkbox above the tabs decides the output layout, and a grey hint always
shows where the next result will land.

Ticked (default) - "Keep the original file name and save into sub-folder":
  the result keeps the NAME OF THE INPUT FILE and is written into a sub-folder
  next to it, "adapted" by default; the folder name can be changed. The file
  name therefore still follows the RINEX naming convention, which matters for
  software that is strict about it, and the original cannot be overwritten.
  In batch mode each file is written into a sub-folder beside its OWN input,
  so a selection spanning several folders is not merged. (Suggested by Kai
  Baasch.)

Unticked:
  the previous behaviour - the result is written next to the input with a
  suffix: <name>_hdr.rnx, <name>_timefiltered.rnx, <name>_60s.rnx, or
  <name>_adapted.rnx in batch mode.

If the chosen sub-folder would resolve onto the input file itself, the program
refuses and says so instead of writing over your data.


CHARACTERS AND BLANK FIELDS
---------------------------
  * Only ASCII can be stored in a RINEX header. If a value contains ö, ä, ü, ß
    or similar, the program says so BEFORE writing, names the field and the
    character, and offers the ASCII spelling to use instead
    (Müller -> Mueller, BÖRJ -> BOERJ).
  * Blank East/North are written as zeros for ANTENNA: DELTA H/E/N, since an
    antenna usually has a height offset only.
  * APPROX POSITION XYZ still needs all three values: a blank coordinate is a
    missing value, not a zero. Leave the whole record empty to keep the file's
    own position.


TAB 1: EDIT HEADER
------------------
  Set or insert single header records. Fill in only the fields you want to
  change; empty rows are left untouched. Missing records are added.

  Supported records:
    MARKER NAME, MARKER NUMBER, MARKER TYPE, OBSERVER / AGENCY,
    REC # / TYPE / VERS, ANT # / TYPE, APPROX POSITION XYZ [m],
    ANTENNA: DELTA H/E/N [m]

  Notes:
    - Fields are padded with blanks to their fixed RINEX width.
    - ANT # / TYPE has three boxes: number, antenna, radome. The radome
      is placed in the last 4 columns, e.g.  LEIAR25.R3      LEIT
    - If MARKER NUMBER is missing it is inserted directly below MARKER NAME.
    - All other header lines and comments are kept unchanged.

  Click "Apply header changes" -> writes <name>_hdr.rnx


TAB 2: TIME FILTER
------------------
  Keep only epochs within a time window.
    - Enter Start and/or End as  YYYY-MM-DD HH:MM:SS
    - Leave either blank for no limit on that side
  TIME OF FIRST OBS / TIME OF LAST OBS in the header are updated to match.

  Click "Apply time filter" -> writes <name>_timefiltered.rnx


TAB 3: CHANGE INTERVAL
----------------------
  Thin the observations to a coarser interval. Epochs are kept so that they
  are at least the new interval apart. This also works for uneven timestamps
  (e.g. smartphone RINEX): the spacing is judged from the data itself, not
  from a possibly wrong/incomplete INTERVAL header. INTERVAL and the epoch
  span are updated. The tool only thins data; it cannot create epochs.

  Click "Change interval" -> writes <name>_<seconds>s.rnx


TAB 4: BATCH HEADER
-------------------
  Apply header edits to several files at once.
    1. "Add files..." to pick the RINEX files.
    2. Enter DEFAULT values that apply to every file.
    3. Tick "differs" for the fields that vary between files.
    4. "Build / refresh per-file table", then fill those fields per file.
       - A blank per-file cell uses the default value.
       - A blank default leaves that record untouched.
    5. "Apply to all files" -> writes <name>_adapted.rnx for each input.


COMMAND LINE (optional)
-----------------------
  python rinex_adapter.py header  in.rnx out.rnx --set "MARKER NAME=NOV2"
  python rinex_adapter.py timefilter in.rnx out.rnx --start "2020-08-05 06:00:00"
  python rinex_adapter.py interval in.rnx out.rnx 60


FOLDER STRUCTURE
----------------
  RINEX-Adapter\
  +-- RINEX-Adapter.exe    Main application
  +-- launch_gui.bat       Launcher script
  +-- README.txt           This file
  +-- README.md            Developer notes
  +-- LICENSE.txt          License
  +-- samples\             Example RINEX files


SUPPORTED
---------
  RINEX 3.x observation files (all constellations: G/R/E/C/J).
  Header records and epoch timestamps are handled; observation data is
  copied through unchanged.

  RINEX 4.0 observation files also work. The header section did not change
  in a way that matters here, so header editing, the time filter and the
  interval change all behave as they do for 3.x, and the version line is
  left as it is. Records this tool does not edit, including the event blocks
  RINEX 4 adds, are copied through untouched rather than interpreted.
  Verified on a constructed 4.00 file (2026-08-24); if you have a real one
  from a receiver that behaves differently, please send it in.


NOTES
-----
  - Output files are always written next to the input with a suffix, so the
    original file is never overwritten.
  - The "Info" and "Contact" buttons show version and developer information.
  - A "merge files" function is planned for a future version.

STAY INFORMED
-------------

  The Institut für Erdmessung runs a moderated mailing list for its GNSS
  software. It announces new releases and warns you about changes that can
  break your work, for example when a server for satellite orbit products
  moves to a new address. Every program in the suite offers this once when it
  first starts, and the Contact dialog can open it again at any time.

  Subscribe (web form):
    https://listserv.uni-hannover.de/cgi-bin/wa?SUBED1=SOFTWARE-IFE&A=1

  Subscribe by e-mail:
    send the single line   subscribe software-ife
    to                     listserv@listserv.uni-hannover.de

  Send that command line on its own. LISTSERV reads the message body line by
  line, so a signature added by your mail program can stop it.

  List address: SOFTWARE-IFE@LISTSERV.UNI-HANNOVER.DE

  LISTSERV answers with a confirmation mail. The subscription becomes active
  only after you reply to it and a moderator approves the request. Subscribing
  is voluntary and you can leave the list at any time.
