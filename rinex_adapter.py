# rinex_adapter.py
"""
RINEX-ADAPTER - lightweight header/epoch adaptation for RINEX 3.x
observation files.

This is the "easy core" of the adapter: it reuses the
RINEX parser/writer already built for RINEX-Masker (rinex_handler.py) and adds:

  * set_header_fields  - edit / insert header records (MARKER NAME, ANT # / TYPE,
                         APPROX POSITION XYZ, ANTENNA: DELTA H/E/N, ...)
  * apply_time_filter  - keep epochs in a time window (same logic as RINEX-Masker)
  * change_interval    - decimate to a coarser sampling interval

All three keep the epoch-span header records (TIME OF FIRST/LAST OBS) consistent
with what is actually written, via rinex_handler.write_rinex().

Merge (combining several files) is deliberately NOT implemented here: it is the
one function with real design questions (incompatible SYS / # / OBS TYPES,
SYS / PHASE SHIFT, INTERVAL, ...). See merge_precheck() for a check-and-abort
skeleton that reflects the recommended v1 behaviour.
"""

import argparse
import os
from datetime import datetime

from rinex_handler import (parse_header, parse_rinex, iterate_epochs,
                           write_rinex)


# --- Column layout of the header records we support -------------------------
# Each entry: list of (type, start_col, end_col) 0-based, end exclusive.
#   's' = left-justified text, 'f' = right-justified F(width).4 float.
FIELD_SPECS = {
    'MARKER NAME':          [('s', 0, 60)],
    'MARKER NUMBER':        [('s', 0, 60)],
    'MARKER TYPE':          [('s', 0, 60)],
    'OBSERVER / AGENCY':    [('s', 0, 20), ('s', 20, 60)],
    'REC # / TYPE / VERS':  [('s', 0, 20), ('s', 20, 40), ('s', 40, 60)],
    # Antenna type field (cols 21-40) = antenna model (A16, cols 21-36) +
    # radome code (A4, cols 37-40), per the IGS naming convention.
    'ANT # / TYPE':         [('s', 0, 20), ('s', 20, 36), ('s', 36, 40)],
    'APPROX POSITION XYZ':  [('f', 0, 14), ('f', 14, 28), ('f', 28, 42)],
    'ANTENNA: DELTA H/E/N': [('f', 0, 14), ('f', 14, 28), ('f', 28, 42)],
}


#: Default name of the sub-folder adapted files are written into.
SUBFOLDER_DEFAULT = 'adapted'


def resolve_output_path(in_path, suffix=None, subfolder=None, create=True):
    """
    Where an adapted file is written.

    Two layouts:

      * ``subfolder`` given - ``<dir>/<subfolder>/<original file name>``. The
        name is **not** changed, so the result can be handed straight to
        software that expects the RINEX naming convention, and the original
        cannot be overwritten because it sits one directory up. Intended for
        batch runs.
      * otherwise - ``<dir>/<base>_<suffix><ext>``, the original behaviour.

    The sub-folder is created on demand. Writing onto the input file is
    refused: that is the exact accident the sub-folder exists to prevent.
    """
    in_path = os.path.abspath(in_path)
    directory, name = os.path.split(in_path)
    base, ext = os.path.splitext(name)

    if subfolder:
        out_dir = os.path.normpath(os.path.join(directory, subfolder))
        out = os.path.normpath(os.path.join(out_dir, name))
    else:
        out_dir = directory
        out = os.path.normpath(
            os.path.join(directory, f"{base}_{suffix}{ext or '.rnx'}"))

    # Checked before the folder is created, so a sub-folder of "." leaves
    # nothing behind on the way to being refused.
    if os.path.normcase(out) == os.path.normcase(in_path):
        raise ValueError(
            f"That would overwrite the input file:\n{in_path}\n\n"
            "Choose a different sub-folder name, or switch the sub-folder "
            "option off so a suffix is added to the file name instead.")

    if subfolder and create:
        os.makedirs(out_dir, exist_ok=True)
    return out


def build_header_record(label, values):
    """
    Build an 80-column RINEX header record for `label` from `values`.

    `values` is a str (single-field labels) or a list/tuple (multi-field).
    Unknown labels fall back to left-justifying the first value in cols 1-60.
    """
    if isinstance(values, (str, int, float)):
        values = [values]
    spec = FIELD_SPECS.get(label)
    buf = [' '] * 60

    if spec is None:
        text = str(values[0])[:60]
        for i, ch in enumerate(text):
            buf[i] = ch
    else:
        for (typ, start, end), val in zip(spec, values):
            width = end - start
            if typ == 'f':
                field = f"{float(val):{width}.4f}"[:width].rjust(width)
            else:
                field = str(val)[:width].ljust(width)
            for i, ch in enumerate(field):
                if start + i < 60:
                    buf[start + i] = ch

    data = ''.join(buf)
    return f"{data:<60}{label:<20}\n"


def _header_label(line):
    return line[60:].strip() if len(line) > 60 else ""


def _set_header_record(header, label, data60):
    """
    Replace (or insert before END OF HEADER) a single header record whose data
    portion is the pre-formatted `data60` string. Edits header.header_lines.
    """
    newline = f"{data60:<60}{label:<20}\n"
    for i, line in enumerate(header.header_lines):
        if _header_label(line) == label:
            header.header_lines[i] = newline
            return
    for i, line in enumerate(header.header_lines):
        if 'END OF HEADER' in _header_label(line):
            header.header_lines.insert(i, newline)
            return


# --- 1. Edit header fields --------------------------------------------------

# Preferred placement for records that get INSERTED (missing from the file):
# put them directly after their anchor record instead of at the end, so
# MARKER NUMBER sits right below MARKER NAME.
INSERT_AFTER = {
    'MARKER NUMBER': 'MARKER NAME',
}


def set_header_fields(in_path, out_path, updates, log=print):
    """
    Write `in_path` to `out_path` with header records replaced/inserted from
    `updates` = {rinex_label: value_or_list}. Every other header line and
    comment is copied through verbatim; only the epoch data is untouched.

    Inserted records go directly after their anchor (see INSERT_AFTER) when the
    anchor is present, otherwise just before END OF HEADER.

    Returns the set of labels that were applied.

    Raises ValueError with a readable message if any value contains characters
    RINEX cannot store - checked here so the CLI and the batch path
    fail the same way the GUI does, and never with a bare UnicodeEncodeError
    thrown from inside writelines().
    """
    problems = find_non_ascii(updates)
    if problems:
        raise ValueError(describe_non_ascii(problems))

    with open(in_path, 'r', encoding='ascii', errors='ignore') as f:
        lines = f.readlines()
    header, header_end_idx = parse_header(lines)

    # What the file already has, decided BEFORE the walk.
    #
    # Decided up front so that a record further down the header is not treated
    # as missing. When MARKER NAME goes past, a MARKER NUMBER below it has not
    # been reached yet; placing it under that anchor at that moment would insert
    # a second MARKER NUMBER and then also rewrite the file's own record.
    present = {_header_label(line) for line in header.header_lines}

    applied = set()
    out_lines = []
    for line in header.header_lines:
        label = _header_label(line)

        if 'END OF HEADER' in label:
            # Insert any remaining requested records that weren't placed yet.
            for key, val in updates.items():
                if key not in applied:
                    out_lines.append(build_header_record(key, val))
                    log(f"  + inserted {key}")
                    applied.add(key)
            out_lines.append(line)
            continue

        if label in updates:
            if label in applied:
                # The source carries this record twice. None of the records we
                # edit may legitimately repeat, so keep the one already written
                # instead of emitting the new value a second time.
                log(f"  - dropped duplicate {label} from the input")
                continue
            out_lines.append(build_header_record(label, updates[label]))
            log(f"  ~ updated  {label}")
            applied.add(label)
        else:
            out_lines.append(line)  # keep other header lines / comments verbatim

        # Place a requested record under its preferred anchor only when the file
        # does not have it at all. One that exists keeps its own place, and is
        # updated when the walk reaches it.
        for key, anchor in INSERT_AFTER.items():
            if (anchor == label and key in updates
                    and key not in applied and key not in present):
                out_lines.append(build_header_record(key, updates[key]))
                log(f"  + inserted {key} (below {anchor})")
                applied.add(key)

    body = lines[header_end_idx:]
    with open(out_path, 'w', encoding='ascii') as f:
        f.writelines(out_lines + body)

    log(f"  wrote {out_path}")
    return applied


# --- 2. Time filter ---------------------------------------------------------

def apply_time_filter(in_path, out_path, t_start=None, t_end=None, log=print):
    """Keep only epochs with t_start <= epoch <= t_end (either may be None)."""
    header, lines, header_end_idx = parse_rinex(in_path)
    kept, first, last, skipped = [], None, None, 0
    for ep in iterate_epochs(lines, header_end_idx):
        if t_start and ep.timestamp < t_start:
            skipped += 1
            continue
        if t_end and ep.timestamp > t_end:
            skipped += 1
            continue
        if first is None:
            first = ep.timestamp
        last = ep.timestamp
        kept.append(ep)
    write_rinex(out_path, header, kept, first_epoch=first, last_epoch=last)
    log(f"  time filter: kept {len(kept)} epochs, dropped {skipped}")
    return len(kept)


# --- 3. Change interval -----------------------------------------------------

def change_interval(in_path, out_path, new_interval, log=print):
    """
    Thin the observations to ~`new_interval` seconds and update the INTERVAL +
    TIME OF FIRST/LAST OBS header records.

    Works for uneven timestamps too, for example smartphone RINEX:
    instead of assuming a fixed grid, it keeps the first epoch and then the next
    epoch that is at least `new_interval` after the last kept one. For clean
    uniform data this is identical to plain decimation. The output interval is
    judged against the DATA's own spacing, not the (possibly wrong) header, so
    incomplete headers don't fool the upsample guard.
    """
    header, lines, header_end_idx = parse_rinex(in_path)
    epochs = list(iterate_epochs(lines, header_end_idx))
    if not epochs:
        raise ValueError("No epochs found in file.")

    times = [ep.timestamp for ep in epochs]
    diffs = [(times[i + 1] - times[i]).total_seconds() for i in range(len(times) - 1)]
    diffs = [d for d in diffs if d > 0]
    observed = sorted(diffs)[len(diffs) // 2] if diffs else None   # median spacing
    uneven = bool(diffs) and any(abs(d - observed) > 1e-3 for d in diffs)

    if observed and new_interval < observed - 1e-6:
        raise ValueError(f"Cannot upsample: {new_interval}s is finer than the data "
                         f"(~{observed:.3f}s spacing). The adapter only thins data, "
                         f"it cannot create epochs.")

    if uneven:
        log(f"  note: uneven timestamps (median spacing ~{observed:.3f}s) - "
            f"thinning by minimum {new_interval}s spacing")

    # Greedy minimum-spacing decimation (jitter tolerance guards against an
    # epoch arriving a hair early on irregular data).
    tol = min(0.5, new_interval * 0.5)
    kept, last_kept_t = [], None
    for ep in epochs:
        if last_kept_t is None or \
           (ep.timestamp - last_kept_t).total_seconds() >= new_interval - tol:
            kept.append(ep)
            last_kept_t = ep.timestamp

    _set_header_record(header, 'INTERVAL', f"{new_interval:10.3f}")
    write_rinex(out_path, header, kept,
                first_epoch=(kept[0].timestamp if kept else None),
                last_epoch=(kept[-1].timestamp if kept else None))
    # Report the real spacing, not the header's (which may be wrong/missing).
    if observed is not None and (uneven or header.interval is None
                                 or abs((header.interval or 0) - observed) > 1e-3):
        orig_str = f"~{observed:.3f}s"
    else:
        orig_str = f"{header.interval}s" if header.interval else "unknown"
    log(f"  interval {orig_str} -> {new_interval}s: kept {len(kept)}/{len(epochs)} epochs"
        + (" (uneven input)" if uneven else ""))
    return len(kept)


# --- 4. Merge (design skeleton only) ---------------------------------------

MERGE_CRITICAL_LABELS = ['SYS / # / OBS TYPES', 'SYS / PHASE SHIFT', 'INTERVAL']


def merge_precheck(paths):
    """
    Recommended v1 merge policy: parse each file's header and ABORT if the
    merge-critical records differ. Returns (ok, list_of_conflicts).

    Actual concatenation of the time-sorted epochs is intentionally left for a
    later iteration once this policy is settled.
    """
    headers = []
    for p in paths:
        h, _ = parse_header(open(p, 'r', encoding='ascii', errors='ignore').readlines())
        headers.append((p, h))

    conflicts = []
    ref_path, ref = headers[0]
    for p, h in headers[1:]:
        if h.obs_types != ref.obs_types:
            conflicts.append(f"SYS / # / OBS TYPES differ ({ref_path} vs {p})")
        if abs((h.interval or 0) - (ref.interval or 0)) > 1e-6:
            conflicts.append(f"INTERVAL differs: {ref.interval}s vs {h.interval}s ({p})")
    return (len(conflicts) == 0), conflicts


# --- 5. Batch header editing ------------------------------------------------

FLOAT_LABELS = {'APPROX POSITION XYZ', 'ANTENNA: DELTA H/E/N'}

#: Float labels whose blank sub-fields may safely default to 0.0.
#: An antenna is normally set up with a height offset only, so demanding that
#: the user types "0" into East and North is busywork. APPROX POSITION XYZ is
#: deliberately NOT in here: a blank coordinate is a missing value, and turning
#: it into 0.0 would silently place the station at the centre of the Earth.
BLANK_AS_ZERO_LABELS = {'ANTENNA: DELTA H/E/N'}


def parse_float_fields(label, values):
    """
    Convert a float header record's sub-fields, honouring BLANK_AS_ZERO_LABELS.

    Returns a list of floats. Raises ValueError with a readable message when a
    field is neither a number nor an acceptable blank.
    """
    allow_blank = label in BLANK_AS_ZERO_LABELS
    out = []
    for val in values:
        s = str(val).strip()
        if not s:
            if allow_blank:
                out.append(0.0)
                continue
            raise ValueError(
                f"{label} needs all {len(values)} values. "
                f"Leave the whole record empty to keep the file's own value.")
        try:
            out.append(float(s.replace(',', '.')))
        except ValueError:
            raise ValueError(f"{label}: '{s}' is not a number.") from None
    return out


# --- Non-ASCII input ---------------------------------------------
# RINEX header records are plain ASCII, and the writer opens the output with
# encoding='ascii'. A name such as "Müller" therefore died with a bare
# UnicodeEncodeError from deep inside file.writelines. The value is checked
# up front instead, and the message
# names the field, the character and the spelling RINEX expects.

_ASCII_SUGGESTIONS = {
    'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
    'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue',
    'á': 'a', 'à': 'a', 'â': 'a', 'å': 'a', 'ã': 'a',
    'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
    'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
    'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o', 'ø': 'o',
    'ú': 'u', 'ù': 'u', 'û': 'u',
    'ñ': 'n', 'ç': 'c', 'å': 'a', 'æ': 'ae',
    'Á': 'A', 'À': 'A', 'Â': 'A', 'É': 'E', 'È': 'E', 'Ê': 'E',
    'Í': 'I', 'Ó': 'O', 'Ô': 'O', 'Ú': 'U', 'Ñ': 'N', 'Ç': 'C', 'Æ': 'AE',
    '–': '-', '—': '-', '‘': "'", '’': "'", '“': '"', '”': '"',
    '°': 'deg', '·': '.', ' ': ' ',
}


#: Letters whose ASCII spelling is two characters, so the second one has to
#: follow the case of the surrounding word: BÖRJ -> BOERJ, not "BOeRJ"
#: while Österreich -> Oesterreich stays mixed.
#: Each entry is (mixed-case form, all-caps form).
_CASED_DIGRAPHS = {
    'Ä': ('Ae', 'AE'), 'Ö': ('Oe', 'OE'), 'Ü': ('Ue', 'UE'),
    'ẞ': ('Ss', 'SS'), 'ß': ('ss', 'SS'), 'Æ': ('Ae', 'AE'),
}


def _in_upper_run(text, i):
    """True when position `i` sits inside an upper-case word."""
    nxt = next((c for c in text[i + 1:] if c.isalpha()), '')
    if nxt:
        return nxt.isupper()
    prev = next((c for c in reversed(text[:i]) if c.isalpha()), '')
    return prev.isupper()


def to_ascii(text):
    """
    Best-effort ASCII spelling of `text` (ö -> oe, é -> e, – -> -).

    Two-letter replacements follow the case of the word they sit in, because
    MARKER NAME and similar records are usually written in capitals and
    "BOeRJ" is not a spelling anyone wants in a header.
    """
    s = str(text)
    out = []
    for i, ch in enumerate(s):
        if ch in _CASED_DIGRAPHS:
            mixed, caps = _CASED_DIGRAPHS[ch]
            out.append(caps if _in_upper_run(s, i) else mixed)
        else:
            out.append(_ASCII_SUGGESTIONS.get(ch, ch if ord(ch) < 128 else '?'))
    return ''.join(out)


def find_non_ascii(updates):
    """
    Every non-ASCII value in an `updates` mapping.

    Returns [(label, subfield_index, value, ascii_suggestion, [chars]), ...],
    empty when the whole set can be written as RINEX.
    """
    problems = []
    for label, value in updates.items():
        values = value if isinstance(value, (list, tuple)) else [value]
        for k, val in enumerate(values):
            s = str(val)
            bad = sorted({ch for ch in s if ord(ch) > 127})
            if bad:
                problems.append((label, k, s, to_ascii(s), bad))
    return problems


def describe_non_ascii(problems):
    """A message a user can act on, listing each field and its ASCII spelling."""
    lines = ["RINEX header records can only hold plain ASCII text, so letters "
             "such as ö, ä, ü and ß cannot be written.", ""]
    for label, k, value, suggestion, chars in problems:
        where = f"{label}" if k == 0 else f"{label}, field {k + 1}"
        lines.append(f"  {where}")
        lines.append(f"      you typed:  {value}")
        lines.append(f"      use instead: {suggestion}")
        lines.append(f"      not allowed: {' '.join(chars)}")
        lines.append("")
    lines.append("Replace those characters and apply again.")
    return "\n".join(lines)


def num_subfields(label):
    """How many input boxes a header label needs (1 for unknown labels)."""
    spec = FIELD_SPECS.get(label)
    return len(spec) if spec else 1


def build_batch_updates(files, defaults, differing_labels, cell_values, log=print):
    """
    Resolve per-file header updates for batch processing.

    Design: enter default values once, tick which fields
    differ per file, then fill only those per file. A blank per-file cell falls
    back to the default value for that sub-field.

    Args:
        files            : list of file paths
        defaults         : {label: [subvalue_str, ...]} defaults for every file
        differing_labels : iterable of labels that vary between files
        cell_values      : {(filepath, label, subidx): str} per-file overrides
        log              : message sink

    Returns:
        {filepath: {label: value_or_list}} ready to pass to set_header_fields().
    """
    differing = set(differing_labels)
    resolved = {}
    for fp in files:
        updates = {}
        for label in set(defaults.keys()) | differing:
            n = num_subfields(label)
            dflt = [str(s) for s in defaults.get(label, [])]
            dflt += [''] * (n - len(dflt))
            if label in differing:
                subs = []
                for k in range(n):
                    cell = (cell_values.get((fp, label, k), '') or '').strip()
                    subs.append(cell if cell else dflt[k])
            else:
                subs = [dflt[k] for k in range(n)]
            subs = [s.strip() for s in subs]
            if not any(subs):
                continue
            if label in FLOAT_LABELS:
                # A blank East/North next to a filled height is normal,
                # not an error - parse_float_fields fills those with 0.0 for the
                # labels where that is meaningful.
                try:
                    updates[label] = parse_float_fields(label, subs)
                except ValueError as exc:
                    log(f"  {os.path.basename(fp)}: skipping {label} - {exc}")
                    continue
            else:
                updates[label] = subs if n > 1 else subs[0]
        resolved[fp] = updates
    return resolved


def batch_apply_headers(resolved, out_suffix="adapted", subfolder=None, log=print):
    """
    Apply resolved per-file header updates (from build_batch_updates) and write
    one output file per input.

    With `subfolder` each file keeps its own name and is written to
    `<its folder>/<subfolder>/`; otherwise the name gains `_<out_suffix>`.
    Files coming from different folders therefore each get their own
    sub-folder, next to the input they came from.

    Returns the list of output paths.
    """
    outputs = []
    for fp, updates in resolved.items():
        out = resolve_output_path(fp, suffix=out_suffix, subfolder=subfolder)
        name = os.path.basename(fp)
        log(f"[{name}]")
        if updates:
            set_header_fields(fp, out, updates, log=log)
        else:
            log("  (no header changes for this file — writing a copy)")
            set_header_fields(fp, out, {}, log=log)
        outputs.append(out)
    return outputs


# --- CLI --------------------------------------------------------------------

def _parse_dt(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def main():
    ap = argparse.ArgumentParser(description="RINEX-ADAPTER")
    sub = ap.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("header", help="set/insert header fields")
    h.add_argument("infile"); h.add_argument("outfile")
    h.add_argument("--set", action="append", default=[], metavar="LABEL=VALUE",
                   help="e.g. --set 'MARKER NAME=NOV2' (repeatable). "
                        "Multi-field labels take '|'-separated values, e.g. "
                        "--set 'ANT # / TYPE=13_M|NOV850          NONE'")

    t = sub.add_parser("timefilter", help="keep epochs in a time window")
    t.add_argument("infile"); t.add_argument("outfile")
    t.add_argument("--start", type=_parse_dt, default=None)
    t.add_argument("--end", type=_parse_dt, default=None)

    iv = sub.add_parser("interval", help="decimate to a coarser interval")
    iv.add_argument("infile"); iv.add_argument("outfile")
    iv.add_argument("seconds", type=float)

    args = ap.parse_args()
    if args.cmd == "header":
        updates = {}
        for item in args.set:
            label, _, value = item.partition("=")
            parts = value.split("|")
            updates[label.strip()] = parts if len(parts) > 1 else value
        set_header_fields(args.infile, args.outfile, updates)
    elif args.cmd == "timefilter":
        apply_time_filter(args.infile, args.outfile, args.start, args.end)
    elif args.cmd == "interval":
        change_interval(args.infile, args.outfile, args.seconds)


if __name__ == "__main__":
    main()
