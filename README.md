# RINEX-Adapter

Repair, trim and resample RINEX observation files.

> **Version 1.0, released 8 September 2026.** Download the Windows package
> from [Releases](https://github.com/J-kroeger/rinex-adapter/releases/latest), unzip it and start
> `RINEX-Adapter.exe`. No installation and no Python required. The full source code is in
> this repository.

## What it does

Fixes the practical problems that stop a RINEX file being usable: header records
that are wrong, missing or inconsistent, a session longer than you want, or a
sampling interval that does not match the rest of your data.

Changes can be applied to one file or to a whole folder at once.

## Why it exists

Observation files arrive from receivers, from campaigns and from students, and
they rarely arrive ready to process. An antenna type spelled differently from
the calibration file, a marker number written twice, or a 1 Hz file where the
processing expects 30 s: each is trivial to describe and tedious to fix by hand
across a folder of files.

## Features

- Corrects and completes RINEX header records
- Cuts a time window from a longer session
- Changes the sampling interval, including for unevenly sampled files
- Applies the same header changes to many files in one run
- Writes to a separate output folder, so the input files are never overwritten


## Running from source

The program is written in Python and was built with Python 3.12.

```
python -m pip install -r requirements.txt
python adapter_gui.py
```

On Windows, `launch_gui.bat` does the same when no packaged executable is next to it.
The full user guide is in [`README.txt`](README.txt).

Example RINEX files are in `samples/`.

## Part of PCC-Suite

This program is one of seven released together as
[PCC-Suite](https://github.com/J-kroeger/pcc-suite), a collection of open-source programs for GNSS antenna
calibration values from the Institut für Erdmessung (IfE), Leibniz University
Hannover. Each is a standalone Windows executable, released and versioned
separately, so you can take only the one you need. No installation, no Python
required.

Archived releases and DOIs are gathered in the Zenodo community
[Open Source Software Packages for GNSS Data Processing](https://zenodo.org/communities/gnss-open-source-solutions).

## Licence

GNU General Public License v3.0 or later. Free to use, share and modify. See
[LICENSE](LICENSE).

## Citation

The method behind the suite and its validation against real PPP solutions are
described in:

> Kröger, J., Kersten, T. & Schön, S. (2026). PCC-Explorer: an open-source
> software tool to assess the impact of GNSS antenna phase center corrections on
> geodetic parameters. *GPS Solutions* **30**, 93. [https://doi.org/10.1007/s10291-026-02056-2](https://doi.org/10.1007/s10291-026-02056-2)

## Stay informed

Release announcements, and warnings when an external data source moves, go to
the institute software mailing list:

```
SOFTWARE-IFE@LISTSERV.UNI-HANNOVER.DE
```

The program offers to subscribe you on first start. You can decline, and you can
ask not to be reminded again.

## Contact

**Dr.-Ing. Johannes Kröger**
Institut für Erdmessung (IfE), Leibniz Universität Hannover
Schneiderberg 50, D-30167 Hannover

Email: [kroeger@ife.uni-hannover.de](mailto:kroeger@ife.uni-hannover.de)
Web: [www.ife.uni-hannover.de](https://www.ife.uni-hannover.de)
