# adapter_gui.py
"""
RINEX-ADAPTER graphical user interface.
Built with tkinter/ttkbootstrap, matching the RINEX-Masker / PCC-Suite style
(darkly theme, IfE + LUH branding, Info/Contact dialogs).

Three panels over the reusable core in rinex_adapter.py:
  1. Edit header fields   2. Time filter   3. Change interval

Deliberately small: it demonstrates the "easy core" of the adapter.
Batch mode and file merging are noted as future work.
"""

import os
import sys
import threading
from datetime import datetime

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *          # noqa: F401,F403
from tkinter import filedialog, messagebox

import rinex_adapter as A

# Shared opt-in dialog for the IfE software mailing list. Never let a missing
# copy stop the program from starting; the canonical file is in shared/.
try:
    import mailing_list
except Exception:
    mailing_list = None

# Version and release date, from this tool's own tool_version.py. The same pair
# sits in the README tag that the PCC-Suite launcher reads, so the launcher no
# longer has to guess a release from a file timestamp.
try:
    import tool_version
    import version_info
    VERSION_TEXT = version_info.about_line(tool_version)
except Exception:
    VERSION_TEXT = "Version: unknown"


# --- PATH HELPER FOR EXE ---
def resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


# Header labels offered in the GUI, with how many sub-fields each takes and a
# hint shown to the user.
HEADER_LABELS = [
    ('MARKER NAME', 1, ['name']),
    ('MARKER NUMBER', 1, ['number']),
    ('MARKER TYPE', 1, ['e.g. Geodetic']),
    ('OBSERVER / AGENCY', 2, ['observer', 'agency']),
    ('REC # / TYPE / VERS', 3, ['number', 'type', 'version']),
    ('ANT # / TYPE', 3, ['number', 'antenna', 'radome']),
    ('APPROX POSITION XYZ', 3, ['X [m]', 'Y [m]', 'Z [m]']),
    ('ANTENNA: DELTA H/E/N', 3, ['H [m]', 'E [m]', 'N [m]']),
]

# Unit shown next to the label (display only; the RINEX label stays the key).
UNIT_SUFFIX = {
    'APPROX POSITION XYZ': '  [m]',
    'ANTENNA: DELTA H/E/N': '  [m]',
}


def _show_ife_contact(parent):
    """
    IfE contact dialog with clickable e-mail and web links.

    Same content and layout as PCC-Explorer's, so every tool in the suite
    presents its contact details identically.
    """
    import webbrowser

    dialog = tk.Toplevel(parent)
    dialog.title("Contact Information")
    dialog.geometry("460x300")
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()

    frame = ttk.Frame(dialog, padding=20)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="Institut für Erdmessung (IfE)",
              font=("Helvetica", 12, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Leibniz Universität Hannover").pack(anchor="w")
    ttk.Label(frame, text="Schneiderberg 50").pack(anchor="w")
    ttk.Label(frame, text="D-30167 Hannover").pack(anchor="w", pady=(0, 15))

    ttk.Label(frame, text="Contact: Dr.-Ing. Johannes Kröger",
              font=("Helvetica", 10, "bold")).pack(anchor="w")

    email_frame = ttk.Frame(frame)
    email_frame.pack(anchor="w", pady=2)
    ttk.Label(email_frame, text="Email: ").pack(side="left")
    email_link = ttk.Label(email_frame, text="kroeger@ife.uni-hannover.de",
                           foreground="#4da6ff", cursor="hand2")
    email_link.pack(side="left")
    email_link.bind("<Button-1>",
                    lambda e: webbrowser.open("mailto:kroeger@ife.uni-hannover.de"))

    web_frame = ttk.Frame(frame)
    web_frame.pack(anchor="w", pady=2)
    ttk.Label(web_frame, text="Web: ").pack(side="left")
    web_link = ttk.Label(web_frame, text="www.ife.uni-hannover.de",
                         foreground="#4da6ff", cursor="hand2")
    web_link.pack(side="left")
    web_link.bind("<Button-1>",
                  lambda e: webbrowser.open("https://www.ife.uni-hannover.de"))

    def _open_mailing_list():
        # Close first. Two stacked modal dialogs each take the grab, and the
        # inner one releasing it would leave this window unresponsive.
        dialog.destroy()
        try:
            parent._show_mailing_list()
        except Exception:
            pass

    buttons = ttk.Frame(frame)
    buttons.pack(pady=(20, 0))
    ttk.Button(buttons, text="Mailing list", command=_open_mailing_list,
               bootstyle="outline-info").pack(side="left", padx=4)
    ttk.Button(buttons, text="Close", command=dialog.destroy,
               bootstyle="secondary").pack(side="left", padx=4)

    # Size to the content, with 460x300 as the minimum: a fixed size would cut
    # the buttons off on systems with larger fonts or display scaling.
    dialog.update_idletasks()
    dialog.geometry("%dx%d" % (max(460, dialog.winfo_reqwidth()),
                               max(300, dialog.winfo_reqheight())))


class App(ttk.Window):
    def __init__(self):
        super().__init__(themename="darkly")
        self.infile = tk.StringVar()
        # On by default: it is the safer layout, and it is
        # the only one that cannot touch the input files.
        self.use_subfolder = tk.BooleanVar(value=True)
        self.subfolder_name = tk.StringVar(value=A.SUBFOLDER_DEFAULT)
        self.is_running = False
        self.batch_files = []          # RINEX paths for batch mode
        self.batch_cells = {}          # {(path, label, subidx): StringVar}
        self._setup_window()
        self._create_widgets()
        self._fit_top_bar()

    def _setup_window(self):
        self.title("RINEX-ADAPTER")
        self.geometry("820x760")
        self.minsize(720, 680)
        try:
            ico = resource_path(os.path.join('assets', 'ife_logo.ico'))
            if os.path.exists(ico):
                self.iconbitmap(ico)
        except Exception:
            pass

    def _fit_top_bar(self):
        """
        Widen the window if the header row does not fit in it.

        The window size is set in pixels while the fonts follow the system
        text scaling, so with larger system text the header row can run off the
        edge and truncate its buttons. Measuring what the row needs is the only
        thing that holds on any display.
        """
        try:
            bar = getattr(self, "_top_bar", None)
            if bar is None:
                return
            self.update_idletasks()
            need = bar.winfo_reqwidth() + 8
            if need <= self.winfo_width():
                return
            height = self.winfo_height()
            self.geometry("%dx%d" % (need, height))
            min_w, min_h = self.minsize()
            if need > min_w:
                self.minsize(need, min_h)
        except Exception as exc:
            print("[WARNING] Could not fit the header row: %s" % exc)

    # ------------------------------------------------------------------
    def _create_widgets(self):
        self._build_top_bar()
        ttk.Separator(self, orient='horizontal').pack(fill='x', pady=(0, 5))

        # File selector
        top = ttk.Frame(self, padding=(12, 6))
        top.pack(fill="x")
        ttk.Label(top, text="RINEX file:").pack(side="left")
        ttk.Entry(top, textvariable=self.infile).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="Browse…", command=self._browse,
                   bootstyle="outline-info").pack(side="left")

        # Keep the original file
        # name and put the result in a sub-folder, so adapted files can be fed
        # straight into software that expects the RINEX naming convention -
        # without any risk of writing over the originals. Applies to the single
        # file above and to Batch header alike.
        outrow = ttk.Frame(self, padding=(12, 0))
        outrow.pack(fill="x")
        ttk.Checkbutton(outrow, variable=self.use_subfolder,
                        command=self._update_out_hint,
                        text="Keep the original file name and save into sub-folder:"
                        ).pack(side="left")
        ttk.Entry(outrow, textvariable=self.subfolder_name, width=14
                  ).pack(side="left", padx=6)
        self.out_hint = ttk.Label(outrow, text="", bootstyle="secondary")
        self.out_hint.pack(side="left", padx=6)
        self.subfolder_name.trace_add("write", lambda *_: self._update_out_hint())
        self.infile.trace_add("write", lambda *_: self._update_out_hint())
        self._update_out_hint()

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=6)
        nb.add(self._tab_header(nb), text="Edit header")
        nb.add(self._tab_timefilter(nb), text="Time filter")
        nb.add(self._tab_interval(nb), text="Change interval")
        nb.add(self._tab_batch(nb), text="Batch header")

        # Console (same colours as the sibling tools)
        console_frame = ttk.Labelframe(self, text="Log", padding=6)
        console_frame.pack(fill="both", expand=False, padx=12, pady=(0, 10))
        self.log = tk.Text(console_frame, height=8, bg="#1a1a2e", fg="#e0e0e0",
                           font=("Consolas", 9), state="disabled")
        self.log.pack(fill="both", expand=True)

    def _build_top_bar(self):
        top_bar = ttk.Frame(self, padding=10)
        top_bar.pack(fill="x")
        # Kept so the window can be widened if this row does not fit.
        self._top_bar = top_bar

        # Left: IfE logo + title
        left_frame = ttk.Frame(top_bar)
        left_frame.pack(side="left")

        self.logo_img = None
        ife_logo_path = resource_path(os.path.join('assets', 'ife_logo.png'))
        if os.path.exists(ife_logo_path):
            try:
                from PIL import Image, ImageTk
                pil_image = Image.open(ife_logo_path)
                aspect = pil_image.width / pil_image.height
                h = 45
                resized = pil_image.resize((int(h * aspect), h), Image.Resampling.LANCZOS)
                self.logo_img = ImageTk.PhotoImage(resized)
                ttk.Label(left_frame, image=self.logo_img).pack(side="left", padx=(0, 12))
            except Exception:
                pass

        text_frame = ttk.Frame(left_frame)
        text_frame.pack(side="left")
        ttk.Label(text_frame, text="RINEX-ADAPTER", font=("Helvetica", 18, "bold")).pack(anchor="w")
        ttk.Label(text_frame, text="Institut für Erdmessung (IfE)",
                  font=("Helvetica", 10), bootstyle="light").pack(anchor="w")

        # Right: LUH logo
        self.luh_logo_img = None
        luh_logo_path = resource_path(os.path.join('assets', 'luh_logo.png'))
        if os.path.exists(luh_logo_path):
            try:
                from PIL import Image, ImageTk
                pil_luh = Image.open(luh_logo_path)
                h = 50
                aspect = pil_luh.width / pil_luh.height
                resized_luh = pil_luh.resize((int(h * aspect), h), Image.Resampling.LANCZOS)
                self.luh_logo_img = ImageTk.PhotoImage(resized_luh)
                luh_frame = ttk.Frame(top_bar)
                luh_frame.pack(side="right", padx=(10, 0))
                ttk.Label(luh_frame, image=self.luh_logo_img).pack(side="right")
            except Exception:
                pass

        # Info & Contact buttons
        btn_frame = ttk.Frame(top_bar)
        btn_frame.pack(side="right", padx=15)
        ttk.Button(btn_frame, text="Contact", command=self._show_contact,
                   bootstyle="outline-info").pack(side="left", padx=3)
        ttk.Button(btn_frame, text="Information", command=self._show_about,
                   bootstyle="outline-secondary").pack(side="left", padx=3)

    # ------------------------------------------------------------------
    def _tab_header(self, parent):
        f = ttk.Frame(parent, padding=10)
        ttk.Label(f, text="Set or insert header records. Empty rows are left unchanged.",
                  bootstyle="light").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        self.hdr_vars = {}
        for r, (label, n, hints) in enumerate(HEADER_LABELS, start=1):
            disp = label + UNIT_SUFFIX.get(label, '')
            ttk.Label(f, text=disp).grid(row=r, column=0, sticky="w", pady=2)
            vs = []
            for c in range(n):
                v = tk.StringVar()
                e = ttk.Entry(f, textvariable=v, width=22)
                e.grid(row=r, column=1 + c, padx=2, sticky="w")
                vs.append(v)
            self.hdr_vars[label] = vs
        ttk.Button(f, text="Apply header changes", command=self._apply_header,
                   bootstyle="success").grid(row=len(HEADER_LABELS) + 1, column=0,
                                             columnspan=2, pady=10, sticky="w")
        return f

    def _tab_timefilter(self, parent):
        f = ttk.Frame(parent, padding=10)
        ttk.Label(f, text="Keep only epochs within the window; TIME OF FIRST/LAST OBS "
                          "are updated accordingly.", bootstyle="light").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(f, text="Start (YYYY-MM-DD HH:MM:SS, blank = file start):").grid(row=1, column=0, sticky="w")
        self.tf_start = tk.StringVar()
        ttk.Entry(f, textvariable=self.tf_start, width=26).grid(row=1, column=1, padx=4, sticky="w")
        ttk.Label(f, text="End (blank = file end):").grid(row=2, column=0, sticky="w")
        self.tf_end = tk.StringVar()
        ttk.Entry(f, textvariable=self.tf_end, width=26).grid(row=2, column=1, padx=4, sticky="w")
        ttk.Button(f, text="Apply time filter", command=self._apply_timefilter,
                   bootstyle="success").grid(row=3, column=0, pady=10, sticky="w")
        return f

    def _tab_interval(self, parent):
        f = ttk.Frame(parent, padding=10)
        ttk.Label(f, text="Thin to a coarser interval (keeps epochs spaced at least this far "
                          "apart; works with uneven/smartphone timestamps). INTERVAL + epoch "
                          "span are updated.",
                  bootstyle="light", wraplength=560).grid(row=0, column=0, columnspan=2,
                                                          sticky="w", pady=(0, 8))
        ttk.Label(f, text="New interval [s]:").grid(row=1, column=0, sticky="w")
        self.iv_val = tk.StringVar(value="30")
        ttk.Entry(f, textvariable=self.iv_val, width=10).grid(row=1, column=1, padx=4, sticky="w")
        ttk.Button(f, text="Change interval", command=self._apply_interval,
                   bootstyle="success").grid(row=2, column=0, pady=10, sticky="w")
        return f

    # -- Batch header tab ----------------------------------------------
    def _scrollable(self, parent):
        """
        Return an inner ttk.Frame that scrolls both ways inside `parent`.

        The batch header table is up to 17 entry columns wide, so a vertical
        scrollbar alone is not enough. The inner frame is pinned to the canvas
        width only while the content is narrower than the canvas; once it is
        wider, the frame keeps its natural width and the horizontal bar takes
        over, so the right-hand columns stay reachable.
        """
        holder = ttk.Frame(parent)
        holder.pack(fill="both", expand=True)
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)

        canvas = tk.Canvas(holder, highlightthickness=0, bg=self.style.colors.bg)
        vbar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        hbar = ttk.Scrollbar(holder, orient="horizontal", command=canvas.xview)
        inner = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _resize(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Stretch to fill only when there is room; never clip wide content.
            canvas.itemconfigure(
                win, width=max(inner.winfo_reqwidth(), canvas.winfo_width()))

        inner.bind("<Configure>", _resize)
        canvas.bind("<Configure>", _resize)
        canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")

        def _wheel(e):
            canvas.yview_scroll(int(-e.delta / 120), "units")

        def _shift_wheel(e):
            canvas.xview_scroll(int(-e.delta / 120), "units")

        def _bind(_e):
            canvas.bind_all("<MouseWheel>", _wheel)
            canvas.bind_all("<Shift-MouseWheel>", _shift_wheel)

        def _unbind(_e):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Shift-MouseWheel>")

        inner.bind("<Enter>", _bind)
        inner.bind("<Leave>", _unbind)
        return inner

    def _tab_batch(self, parent):
        outer = ttk.Frame(parent)
        pad = ttk.Frame(self._scrollable(outer), padding=10)
        pad.pack(fill="both", expand=True)

        # 1) file selection
        frow = ttk.Frame(pad)
        frow.pack(fill="x")
        ttk.Button(frow, text="Add files…", command=self._batch_add_files,
                   bootstyle="outline-info").pack(side="left")
        ttk.Button(frow, text="Clear", command=self._batch_clear,
                   bootstyle="outline-secondary").pack(side="left", padx=4)
        self.batch_files_var = tk.StringVar(value="No files selected")
        ttk.Label(frow, textvariable=self.batch_files_var,
                  bootstyle="light").pack(side="left", padx=8)

        ttk.Label(pad, text="1) Enter default values (used for every file).  "
                            "2) Tick 'differs' for fields that vary per file.  "
                            "3) Build the table below and fill those per file "
                            "(a blank cell uses the default).",
                  bootstyle="light", wraplength=740).pack(anchor="w", pady=(8, 4))

        # 2) defaults + differs form
        form = ttk.Frame(pad)
        form.pack(fill="x")
        ttk.Label(form, text="differs", width=7, bootstyle="light").grid(row=0, column=0)
        ttk.Label(form, text="field", bootstyle="light").grid(row=0, column=1, sticky="w")
        self.batch_default_vars = {}
        self.batch_differs = {}
        for r, (label, n, hints) in enumerate(HEADER_LABELS, start=1):
            bv = tk.BooleanVar(value=False)
            self.batch_differs[label] = bv
            ttk.Checkbutton(form, variable=bv).grid(row=r, column=0)
            ttk.Label(form, text=label + UNIT_SUFFIX.get(label, '')).grid(
                row=r, column=1, sticky="w", pady=1)
            vs = []
            for c in range(n):
                v = tk.StringVar()
                ttk.Entry(form, textvariable=v, width=18).grid(row=r, column=2 + c, padx=2)
                vs.append(v)
            self.batch_default_vars[label] = vs

        ttk.Button(pad, text="Build / refresh per-file table",
                   command=self._batch_build_table, bootstyle="info").pack(anchor="w", pady=8)

        self.batch_table_holder = ttk.Labelframe(
            pad, text="Per-file values (blank cell = default)", padding=8)
        self.batch_table_holder.pack(fill="both", expand=True)
        ttk.Label(self.batch_table_holder,
                  text="Add files and tick 'differs' fields, then build the table.",
                  bootstyle="light").grid(row=0, column=0, sticky="w")

        ttk.Button(pad, text="Apply to all files", command=self._batch_apply,
                   bootstyle="success").pack(anchor="w", pady=10)
        return outer

    def _batch_add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select RINEX files",
            filetypes=[("RINEX obs", "*.rnx *.*o *.obs"), ("All files", "*.*")])
        for p in paths:
            if p not in self.batch_files:
                self.batch_files.append(p)
        self._batch_refresh_files()
        self._batch_build_table()

    def _batch_clear(self):
        self.batch_files = []
        self._batch_refresh_files()
        self._batch_build_table()

    def _batch_refresh_files(self):
        n = len(self.batch_files)
        if not n:
            self.batch_files_var.set("No files selected")
        else:
            names = ", ".join(os.path.basename(f) for f in self.batch_files[:4])
            self.batch_files_var.set(f"{n} file(s): {names}" + (" …" if n > 4 else ""))

    def _batch_build_table(self):
        for w in self.batch_table_holder.winfo_children():
            w.destroy()
        self.batch_cells = {}
        differing = [(l, n, h) for (l, n, h) in HEADER_LABELS if self.batch_differs[l].get()]
        if not self.batch_files:
            ttk.Label(self.batch_table_holder, text="Add files first.",
                      bootstyle="warning").grid(row=0, column=0, sticky="w")
            return
        if not differing:
            ttk.Label(self.batch_table_holder,
                      text="Tick at least one 'differs' field, then build the table.",
                      bootstyle="light").grid(row=0, column=0, sticky="w")
            return
        ttk.Label(self.batch_table_holder, text="File",
                  font=("Helvetica", 9, "bold")).grid(row=0, column=0, padx=4, sticky="w")
        colmap, col = [], 1
        for (label, n, hints) in differing:
            short = label.split(':')[0].split('/')[0].strip()
            for k in range(n):
                head = short if n == 1 else f"{short}·{hints[k]}"
                ttk.Label(self.batch_table_holder, text=head,
                          font=("Helvetica", 8, "bold")).grid(row=0, column=col, padx=2)
                colmap.append((label, k))
                col += 1
        for r, fp in enumerate(self.batch_files, start=1):
            ttk.Label(self.batch_table_holder, text=os.path.basename(fp)).grid(
                row=r, column=0, padx=4, sticky="w")
            for c, (label, k) in enumerate(colmap, start=1):
                v = tk.StringVar()
                self.batch_cells[(fp, label, k)] = v
                ttk.Entry(self.batch_table_holder, textvariable=v, width=15).grid(
                    row=r, column=c, padx=2, pady=1)

    def _batch_apply(self):
        if not self.batch_files:
            messagebox.showerror("No files", "Add RINEX files first.")
            return
        defaults = {l: [v.get() for v in vs] for l, vs in self.batch_default_vars.items()}
        differing = {l for l, bv in self.batch_differs.items() if bv.get()}
        cells = {key: v.get() for key, v in self.batch_cells.items()}
        files = list(self.batch_files)

        # Catch ö/ä/ü/ß before a background thread turns it into a
        # one-line "ERROR: ..." in the log, where it is easy to miss entirely.
        checked = dict(defaults)
        for (fp, label, k), value in cells.items():
            if value.strip():
                checked[f"{os.path.basename(fp)} — {label}"] = [value]
        problems = A.find_non_ascii(checked)
        if problems:
            messagebox.showerror("Characters RINEX cannot store",
                                 A.describe_non_ascii(problems))
            return

        sub = self._subfolder()

        # Applying the same lesson as the non-ASCII check: an impossible output
        # to be a dialog *before* the run starts. Inside the worker thread it
        # would only become an "ERROR:" line in the log, which is exactly the
        # kind of message that would otherwise be invisible.
        try:
            for fp in files:
                A.resolve_output_path(fp, suffix="adapted", subfolder=sub,
                                      create=False)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Cannot write there", str(exc))
            self._logln(f"ERROR: {exc}")
            return

        def run():
            try:
                resolved = A.build_batch_updates(files, defaults, differing, cells,
                                                 log=self._logln)
                outs = A.batch_apply_headers(resolved, subfolder=sub, log=self._logln)
                # Say which layout was used - the whole point of the
                # option is knowing where the files went and under which name.
                where = (f"into '{sub}\\', file names unchanged" if sub
                         else "next to the originals, suffix '_adapted'")
                self._logln(f"Batch done: {len(outs)} file(s) written {where}.")
            except Exception as e:
                self._logln(f"ERROR: {e}")
        threading.Thread(target=run, daemon=True).start()

    # -- helpers -------------------------------------------------------
    def _browse(self):
        p = filedialog.askopenfilename(
            title="Select RINEX observation file",
            filetypes=[("RINEX obs", "*.rnx *.*o *.obs"), ("All files", "*.*")])
        if p:
            self.infile.set(p)

    def _subfolder(self):
        """The sub-folder to write into, or None for the suffix layout."""
        if not self.use_subfolder.get():
            return None
        return self.subfolder_name.get().strip() or A.SUBFOLDER_DEFAULT

    def _out_path(self, suffix):
        return A.resolve_output_path(self.infile.get(), suffix=suffix,
                                     subfolder=self._subfolder())

    def _out_path_or_warn(self, suffix):
        """_out_path, but a bad sub-folder name reports itself instead of raising."""
        try:
            return self._out_path(suffix)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Cannot write there", str(exc))
            self._logln(f"ERROR: {exc}")
            return None

    def _update_out_hint(self):
        """
        Show where the next result will land, before anything is written.

        A sub-folder that resolves onto the input file (".", "./", the folder
        the file already sits in) is called out here in red, so the warning
        arrives while typing rather than at the Apply button.
        """
        sub = self._subfolder()
        path = self.infile.get()

        if sub and path:
            try:
                A.resolve_output_path(path, suffix="hdr", subfolder=sub,
                                      create=False)
            except (ValueError, OSError):
                self.out_hint.config(
                    text="→ this would overwrite the input file — choose another sub-folder",
                    bootstyle="danger")
                return

        if sub:
            self.out_hint.config(
                text=f"→ {os.path.join(sub, os.path.basename(path) or 'same name')}",
                bootstyle="secondary")
        else:
            self.out_hint.config(text="→ same folder, name gets a suffix (…_hdr)",
                                 bootstyle="secondary")

    def _logln(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.update_idletasks()

    def _require_file(self):
        if not self.infile.get() or not os.path.exists(self.infile.get()):
            messagebox.showerror("No file", "Please choose a valid RINEX file first.")
            return False
        return True

    # -- actions -------------------------------------------------------
    def _apply_header(self):
        if not self._require_file():
            return
        updates = {}
        for label, vs in self.hdr_vars.items():
            vals = [v.get() for v in vs]
            if not any(s.strip() for s in vals):
                continue
            if label in A.FLOAT_LABELS:
                # An antenna usually has a height offset only, so a
                # blank East/North is filled with 0.0 rather than rejected.
                try:
                    vals = A.parse_float_fields(label, vals)
                except ValueError as exc:
                    messagebox.showerror("Bad value", str(exc))
                    return
            updates[label] = vals if len(vs) > 1 else vals[0]
        if not updates:
            messagebox.showinfo("Nothing to do", "No header fields filled in.")
            return

        # Check before writing, so ö/ä/ü/ß produce a message that says
        # which field is wrong and what to type instead - not a UnicodeEncodeError.
        problems = A.find_non_ascii(updates)
        if problems:
            messagebox.showerror("Characters RINEX cannot store",
                                 A.describe_non_ascii(problems))
            return

        out = self._out_path_or_warn("hdr")
        if out is None:
            return
        try:
            A.set_header_fields(self.infile.get(), out, updates, log=self._logln)
        except (ValueError, OSError, UnicodeEncodeError) as exc:
            messagebox.showerror("Could not write the file", str(exc))
            self._logln(f"ERROR: {exc}")
            return
        self._logln(f"Done -> {out}")

    def _apply_timefilter(self):
        if not self._require_file():
            return

        def pdt(s):
            s = s.strip()
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S") if s else None
        try:
            ts, te = pdt(self.tf_start.get()), pdt(self.tf_end.get())
        except ValueError:
            messagebox.showerror("Bad time", "Use format YYYY-MM-DD HH:MM:SS")
            return
        out = self._out_path_or_warn("timefiltered")
        if out is None:
            return
        threading.Thread(target=lambda: (
            A.apply_time_filter(self.infile.get(), out, ts, te, log=self._logln),
            self._logln(f"Done -> {out}")), daemon=True).start()

    def _apply_interval(self):
        if not self._require_file():
            return
        try:
            iv = float(self.iv_val.get())
        except ValueError:
            messagebox.showerror("Bad value", "Interval must be a number.")
            return
        out = self._out_path_or_warn(f"{int(iv)}s")
        if out is None:
            return

        def run():
            try:
                A.change_interval(self.infile.get(), out, iv, log=self._logln)
                self._logln(f"Done -> {out}")
            except ValueError as e:
                self._logln(f"ERROR: {e}")
        threading.Thread(target=run, daemon=True).start()

    # -- Info & Contact dialogs ---------------------------------------
    def _show_about(self):
        messagebox.showinfo("Information - RINEX-ADAPTER",
                            "RINEX-ADAPTER\n" + VERSION_TEXT + "\n\n"
                            "Adapts RINEX 3.x observation file headers and epochs:\n"
                            "edit/insert header records, apply a time filter, and\n"
                            "change the sampling interval. Shares the RINEX engine\n"
                            "used by RINEX-Masker.\n\n"
                            "Institut für Erdmessung (IfE)\n"
                            "Leibniz Universität Hannover\n\n"
                            "License: GNU General Public License v3 (GPLv3)\n\n"
                            "Developers:\n"
                            "  Amr Fawzy, M.Sc.\n"
                            "  Dr.-Ing. Johannes Kröger")

    def _show_contact(self):
        _show_ife_contact(self)

    def _show_mailing_list(self):
        """The mailing list dialog, on request, whatever was answered before."""
        if mailing_list is None:
            messagebox.showwarning(
                "IfE software mailing list",
                "This installation is missing mailing_list.py, so the "
                "subscription dialog cannot be shown. Please report it to "
                "the IfE, the Contact button has the address.")
            return
        mailing_list.show_on_request(self, "RINEX-Adapter")


if __name__ == "__main__":
    app = App()
    if mailing_list is not None:
        mailing_list.maybe_show(app, "RINEX-Adapter")
    app.mainloop()
