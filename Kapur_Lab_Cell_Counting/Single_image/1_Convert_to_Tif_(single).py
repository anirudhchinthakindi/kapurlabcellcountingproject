# 1_Convert_to_Tif_(single).py
#
# Fiji / ImageJ Jython script - Kapur Lab Cell Counting suite, step 1,
# single-image version.
#
# Converts ONE microscope file to TIFF, with optional z-projection and
# channel selection. Same processing, settings and output names as the
# batch version (Batch > 1 Convert to Tif), so a file converted here lands
# where, and under the name, a batch run would have put it. Each output
# keeps the whole input name and only adds the projection and channel to
# the end of it:
#
#   Region0011_ChannelFITCTRITC_Seq0011.nd2
#       ->  Region0011_ChannelFITCTRITC_Seq0011_MAX_C1.tif
#           Region0011_ChannelFITCTRITC_Seq0011_MAX_C2.tif
#
# Menu  : Plugins > Kapur Lab Cell Counting > Single image >
#         1 Convert to Tif (single)
# Reads : one microscope file in any format Bio-Formats reads (.nd2, .ims,
#         .czi, .tif, ...).
# Writes: a NEW folder (default name "tifs"; with 'Output location' blank
#         it goes one level above the folder holding the file, or inside
#         that folder when it holds a "<region> MBF" folder; see OUTPUT
#         LOCATION) holding one .tif per channel (or one
#         .tif), plus a parameter record
#         _run_1_Convert_to_Tif_single_<time>.txt and, if asked for, a debug
#         log _conversion_log_<input name>.csv (_conversion_log_<RegionXXXX>.csv
#         with OUTPUT_STEM = "region").
#
# The later stages pair files by the leading RegionXXXX token, so anything
# after it in the name is ignored. See OUTPUT NAMING in the configuration
# block (OUTPUT_STEM = "region" names the outputs by that token only).
#
# Before it runs, the script shows a Check settings window that lists the
# input, the output folder, each channel of the file (with the name
# and wavelength the file stores) and the output file it goes to, plus
# warnings about likely mistakes. Press Run to go ahead or Cancel to stop
# with nothing written. CONFIRM_BEFORE_RUN in the configuration block
# turns the window off.
#
# Usage: Plugins > Kapur Lab Cell Counting > Single image >
#        1 Convert to Tif (single), or open this file in the Script Editor
#        (File > New > Script..., or Plugins > Scripting > Script Editor)
#        with Language = Python (Jython) and press Run.

#@ File    (label="Slide folder (the scripts find its subfolders)", style="directory") slideDir
#@ String  (label="Section (e.g. Region0011; blank = choose from a list)", value="", required=false) sectionKey
#@ String  (label="File type to convert", choices={".ims", ".nd2"}, style="radioButtonHorizontal") fileType
#@ File    (label="Output location (blank = beside the folder that holds the input file)", style="directory", required=false) outParentDir
#@ String  (label="Name for the new output folder", value="tifs") outFolderName
#@ Boolean (label="Run a z-projection", value=true) doProject
#@ String  (label="   projection type", choices={"Maximum intensity", "Average intensity", "Sum slices", "Minimum intensity", "Standard deviation", "Median"}, style="listBox") projectionType
#@ Integer (label="   first z slice (0 = first)", value=0, min=0) zStart
#@ Integer (label="   last z slice (0 = last)", value=0, min=0) zStop
#@ Boolean (label="Save only certain channels", value=false) selectChannels
#@ String  (label="   channels to save, e.g. 1,3-4", value="1") channelList
#@ Boolean (label="Save each channel as its own file", value=true) splitChannels
#@ Boolean (label="Overwrite existing output files", value=false) overwrite
#@ Boolean (label="Write a debug log CSV to the output folder", value=false) writeLog
#@ Boolean (label="Show the result (open the saved TIFFs)", value=true) showResult


# =========================================================================
# ===  USER CONFIGURATION  ================================================
# =========================================================================
#
# Everything a user may need to change lives between these two banners.
# Nothing below the END OF USER CONFIGURATION banner needs editing for
# routine use. These settings mean the same as in the batch version; keep
# the two in step if you change one.
#
# (No FILE FORMAT section here: this version converts whichever file you
# pick, in any format Bio-Formats can read.)

# ---- SERIES -------------------------------------------------------------
#
# Imaris (.ims) files store a resolution pyramid, and Bio-Formats presents
# the levels as separate series. Series 0 is full resolution, which is
# almost always what you want. Raise this only if you deliberately want a
# downsampled level.
#
# A multi-point (multi-position) .nd2 stores each XY position as its own
# series of the same size. Only SERIES_INDEX is converted, so such a file
# is flagged in the Log, in the completion message ("with problems") and
# in the Check settings window.
SERIES_INDEX = 0


# ---- OUTPUT NAMING ------------------------------------------------------
#
# OUTPUT_STEM sets how each output name starts:
#   "full"    (default) the whole input name. The outputs keep the input
#             name and only add to the end of it (the version 1 names):
#               Region0011_ChannelFITCTRITC_Seq0011.nd2
#                 -> Region0011_ChannelFITCTRITC_Seq0011_MAX_C1.tif
#                    Region0011_ChannelFITCTRITC_Seq0011_MAX_C2.tif
#   "region"  only the leading RegionXXXX token of the input name (found
#             with KEY_PATTERN), the same name as the NeuroInfo files
#             (Region0011.xml):
#               Region0011_ChannelFITCTRITC_Seq0011.nd2
#                 -> Region0011_MAX_C1.tif, Region0011_MAX_C2.tif
#             A file whose name has no RegionXXXX token keeps its whole
#             name, and the Log flags it. In the batch version, two input
#             files with the same token (Region0011_A.nd2, Region0011_B.nd2)
#             stop the run before anything is converted, so one can never
#             overwrite the other.
# Either way the later stages pair files by the leading RegionXXXX token.
OUTPUT_STEM = "full"

# The region token (OUTPUT_STEM = "region" only). The bracketed part is
# used, with its upper/lower case exactly as in the file name.
KEY_PATTERN = r"^(Region\d+)"

# The channel suffix. With OUTPUT_STEM = "full" it is added to every file
# saved one channel per file, and whenever only one channel is kept:
#   all channels, each its own file     -> <name>_MAX_C1.tif, <name>_MAX_C2.tif
#   channel 2 only (split or not)       -> <name>_MAX_C2.tif
#   all channels in one file            -> <name>_MAX.tif
#   channels 1,3 in one file            -> <name>_MAX_Csel.tif
# With OUTPUT_STEM = "region" it is added only when one input file gives
# MORE THAN ONE TIFF ("Save each channel as its own file" ticked and more
# than one channel kept):
#   all channels, each its own file     -> Region0011_MAX_C1.tif, Region0011_MAX_C2.tif
#   channel 2 only                      -> Region0011_MAX.tif
#   all channels (or 1,3) in one file   -> Region0011_MAX.tif
CHANNEL_SUFFIX_TEMPLATE = "_C%d"

# OUTPUT_STEM = "full" only: added when several channels are kept together
# in ONE file and that is a subset of what the original had. Blank to add
# nothing. With OUTPUT_STEM = "region" it is never added; the Log and the
# parameter record say which channels each file holds.
CHANNEL_SUBSET_SUFFIX = "_Csel"

# True (default): add the projection suffix below before the channel
# suffix (Region0011_ChannelFITCTRITC_Seq0011_MAX_C2.tif). It is added
# only when a projection was actually made.
# False: leave it out; the Log and the parameter record still say which
# projection was used.
ADD_PROJECTION_SUFFIX = True

PROJECTION_SUFFIX = {
    "Maximum intensity": "_MAX",
    "Average intensity": "_AVG",
    "Sum slices": "_SUM",
    "Minimum intensity": "_MIN",
    "Standard deviation": "_SD",
    "Median": "_MED",
}

OUTPUT_EXTENSION = ".tif"


# ---- SAFETY CHECKS ------------------------------------------------------
#
# True (default): before anything is converted, show a "Check settings"
# window that lists what is about to happen (which files, which channels
# go to which output files, the output folder) and any warnings, with Run
# and Cancel. False: skip the window and start straight away, e.g. for
# unattended runs. The warnings are written to the Log either way.
CONFIRM_BEFORE_RUN = True


# ---- PARAMETER RECORD ---------------------------------------------------
#
# True: save _run_1_Convert_to_Tif_single_<date-time>.txt in the output folder,
# listing every setting this run used, so the TIFFs can be traced back to
# exactly how they were made. False: do not write it.
WRITE_PARAMETER_RECORD = True

# ---- OUTPUT LOCATION ----
# Where tifs/ goes when 'Output location' is blank. Normally one level above
# the input folder (the protocol: tifs/ next to nd2/). When the input folder
# itself holds a region folder made by Set Up Slide Folders (a subfolder
# whose name has the word MBF, e.g. "hippocampus MBF"), it is a slide folder
# holding its raw files directly, and tifs/ is made inside it. Set this to
# False to always use one level above. The Check settings window shows the
# folder that will be used.
TIFS_INSIDE_SLIDE_FOLDER = True

# ---- SECTION KEYS ----
# Used to list a slide's sections (RegionXXXX) when the slide folder is given.
CASE_INSENSITIVE_KEYS = True
REQUIRE_IN_NAME = ""
EXCLUDE_IN_NAME = ""

# =========================================================================
# ===  END OF USER CONFIGURATION  =========================================
# =========================================================================

SCRIPT_NAME = "1_Convert_to_Tif_(single)"
SCRIPT_VERSION = "2.0"


import os
import re

from ij import IJ, ImagePlus, ImageStack, CompositeImage
from java.lang import Exception as JavaException
from ij.plugin import ZProjector, ChannelSplitter

try:
	from loci.plugins import BF
	HAVE_BIOFORMATS = True
except ImportError:
	HAVE_BIOFORMATS = False

# ---- SHARED: keys -- keep identical ----
# Needs KEY_PATTERN, CASE_INSENSITIVE_KEYS, REQUIRE_IN_NAME and
# EXCLUDE_IN_NAME from the configuration block.
def key_from(filename):
	"""Pairing key = the leading Region token; everything after is ignored."""
	import os
	import re
	stem = os.path.splitext(os.path.basename(filename))[0]
	m = re.search(KEY_PATTERN, stem, re.IGNORECASE if CASE_INSENSITIVE_KEYS else 0)
	if not m:
		return None
	key = m.group(1)
	return key.lower() if CASE_INSENSITIVE_KEYS else key


def name_allowed(filename):
	"""Apply the REQUIRE_IN_NAME / EXCLUDE_IN_NAME filename filters."""
	if REQUIRE_IN_NAME and REQUIRE_IN_NAME not in filename:
		return False
	if EXCLUDE_IN_NAME and EXCLUDE_IN_NAME in filename:
		return False
	return True
# ---- END SHARED: keys ----


# ---- SHARED: slide_layout -- keep identical ----
# A stage's folders from ONE slide folder. A region folder: named with the
# word MBF and holding a pipeline subfolder (Set Up's rule).
LAYOUT_MBF_RE = r"(^|[^A-Za-z0-9])MBF([^A-Za-z0-9]|$)"
LAYOUT_SLIDE_LEVEL = ("tifs", "jpx", "nd2", "ims")
LAYOUT_REGION_SUBS = ("xml", "rois", "processed_bgsub_cleared", "probabilities",
                      "particle_counts", "optimization", "pipeline_composites")


def layout_is_region(path):
	import os
	import re
	if not re.search(LAYOUT_MBF_RE, os.path.basename(path), re.IGNORECASE):
		return False
	try:
		return bool([d for d in os.listdir(path) if d.lower() in
		             LAYOUT_REGION_SUBS and os.path.isdir(os.path.join(path, d))])
	except OSError:
		return False


def layout_regions(slide):
	"""Names of the slide's region (MBF) folders, sorted."""
	import os
	try:
		names = sorted(os.listdir(slide))
	except OSError:
		return []
	return [d for d in names if layout_is_region(os.path.join(slide, d))]


def layout_match_region(regions, typed):
	"""Regions matching the typed name: exactly, as name + " MBF", else
	those starting with it."""
	t = (typed or "").strip().lower()
	for ok in (lambda r: r.lower() == t, lambda r: r.lower() == t + " mbf",
	           lambda r: r.lower().startswith(t)):
		hits = [r for r in regions if ok(r)]
		if hits:
			return hits
	return []


def layout_record():
	"""Parameter-record lines for the slide, region and section fields."""
	import os
	g = globals()
	if g.get("_SLIDE") is None:
		return []
	reg = g.get("_REGION") or g["_SLIDE"]
	out = [("Slide folder (the scripts find its subfolders)", g["_SLIDE"])]
	if "regionName" in g:
		out.append(("Region (its MBF folder; blank = choose from a list)", "%s (used: %s)"
		            % (g.get("regionName") or "", reg != g["_SLIDE"] and
		               os.path.basename(reg) or "the slide folder")))
	if "sectionKey" in g:
		out.append(("Section (e.g. Region0011; blank = choose from a list)",
		            g.get("_SEC") or g.get("sectionKey") or ""))
	return out


def layout_pick_region(slide, typed):
	"""Region folder (or the slide); several: chosen from a list with file
	counts, typed name, last choice or most files preselected. None if
	cancelled."""
	import os
	from ij import Prefs
	from ij.gui import GenericDialog
	regions = layout_regions(slide)
	typed = (typed or "").strip()
	hits = typed and layout_match_region(regions, typed) or []
	here = [d for d in LAYOUT_REGION_SUBS if os.path.isdir(os.path.join(slide, d))]
	if not regions or (len(regions) == 1 and not here and (not typed or hits)):
		return regions and os.path.join(slide, regions[0]) or slide
	own = "(none: the folders directly in the slide folder)"
	opts = regions + (here and [own] or [])

	def info(d):
		n = []
		for s, t in (("xml", "xml"), ("rois", "rois"), ("probabilities", "maps")):
			if os.path.isdir(os.path.join(d, s)):
				n.append((t, len([f for f in os.listdir(
				    os.path.join(d, s)) if f[:1] not in "._"])))
		return ("%s   (%s)" % (d != slide and os.path.basename(d) or own,
		                       ", ".join(["%s %d" % x for x in n]) or "empty"),
		        sum([x[1] for x in n]))
	got = [info(o == own and slide or os.path.join(slide, o)) for o in opts]
	shown = [g[0] for g in got]
	most = [g[1] for g in got].index(max([g[1] for g in got]))
	last = len(hits) == 1 and hits[0] or Prefs.get("kapurcellcount.region", "")
	gd = GenericDialog("Choose the region")
	gd.addMessage("%s%s holds %d region folders: choose the one to analyse."
	              % (typed and not len(hits) == 1 and "'%s' does not match one "
	                 "region folder.\n" % typed or "", os.path.basename(slide), len(regions)))
	gd.addChoice("Region folder", shown, shown[opts.index(last)] if last in opts else shown[most])
	gd.showDialog()
	if gd.wasCanceled():
		return None
	pick = opts[shown.index(gd.getNextChoice())]
	Prefs.set("kapurcellcount.region", pick)
	return slide if pick == own else os.path.join(slide, pick)


def layout_find(slide, region, name):
	"""Path of subfolder name: slide-level names in the slide (then region),
	others in the region only; missing: where it belongs."""
	import os
	top = name.split("/")[0].lower()
	if top in LAYOUT_SLIDE_LEVEL:
		order = [slide, region]
		if layout_is_region(slide):     # the region folder itself was chosen
			order.append(os.path.dirname(slide))
	else:
		order = [region]
	for base in order:
		p = os.path.join(base, *name.split("/"))
		if os.path.isdir(p):
			return p
	return os.path.join(order[0], *name.split("/"))


def layout_confirm(title, slide, region, fields):
	"""Folders/files found, for checking. fields: (label, "dir"/"choice",
	value, options, required). Paths ("" = none) or None."""
	import os
	from ij import IJ
	from ij.gui import GenericDialog
	pick_one = "(choose one)"
	vals = [f[2] or "" for f in fields]
	for _try in range(3):
		gd = GenericDialog(title)
		gd.addMessage("Slide: %s\nRegion folder: %s\nCheck the folders and files "
		              "found below; change any that are wrong."
		              % (slide, os.path.basename(region) if region != slide
		                 else "(none: everything is in the slide folder)"))
		for (label, kind, _v, options, required), v in zip(fields, vals):
			if kind == "dir":
				gd.addDirectoryField(label, v, 45)
				continue
			names = [os.path.basename(o) for o in options]
			if not required:
				names = ["(none)"] + names
			elif len(names) > 1 and not v:
				names = [pick_one] + names
			names = names or ["(none found)"]
			gd.addChoice(label, names, os.path.basename(v) if v else names[0])
		gd.showDialog()
		if gd.wasCanceled():
			return None
		out, unpicked = [], []
		for label, kind, _v, options, required in fields:
			if kind == "dir":
				out.append(gd.getNextString().strip())
				continue
			pick = gd.getNextChoice()
			if pick == pick_one:
				unpicked.append(label)
			out.append(([o for o in options if os.path.basename(o) == pick]
			            or [""])[0])
		if unpicked:
			IJ.error(title, "Several files fit this section. Choose the one to "
			         "use in:\n%s" % "\n".join(unpicked))
			vals = out
			continue
		for (label, kind, _v, _o, required), v in zip(fields, out):
			if required and (not v or (kind == "dir" and not os.path.isdir(v))):
				IJ.error(title, "%s:\n%s\n\nThis is needed and was not found. "
				         "Check the slide and region, or run the earlier stage "
				         "first." % (label, v or "(none found)"))
				return None
		return out
	return None
# ---- END SHARED: slide_layout ----


# ---- SHARED: slide_files -- keep identical ----
# Single-image scripts: the files of one section in a folder. Needs the
# keys block (key_from, KEY_PATTERN, CASE_INSENSITIVE_KEYS).
def layout_files_for(folder, key, exts):
	"""Files in folder whose RegionXXXX key is key, sorted."""
	import os
	try:
		names = sorted(os.listdir(folder))
	except OSError:
		return []
	return [os.path.join(folder, n) for n in names if not n.startswith(".")
	        and os.path.splitext(n)[1].lower() in exts and key_from(n) == key]


def layout_keys(folder, exts):
	"""RegionXXXX keys of the files in folder (as written), sorted."""
	import os
	import re
	out = {}
	try:
		names = sorted(os.listdir(folder))
	except OSError:
		return []
	for n in names:
		if os.path.splitext(n)[1].lower() in exts and key_from(n) is not None:
			m = re.search(KEY_PATTERN, os.path.splitext(n)[0],
			              re.IGNORECASE if CASE_INSENSITIVE_KEYS else 0)
			out.setdefault(key_from(n), m.group(1) if m else key_from(n))
	return [out[k] for k in sorted(out)]


def layout_pick_section(keys, typed):
	"""The section to use: the typed one, or a choice (None: told why)."""
	from ij import IJ
	from ij.gui import GenericDialog
	typed = (typed or "").strip()
	if not keys:
		IJ.error("Section", "No RegionXXXX files were found for this stage.")
		return None
	if typed:
		hits = [k for k in keys if key_from(k) == key_from(typed)]
		if hits:
			return hits[0]
		IJ.error("Section", "'%s' was not found. Sections here: %s"
		         % (typed, ", ".join(keys[:30])))
		return None
	gd = GenericDialog("Choose the section")
	gd.addChoice("Section", keys, keys[0])
	gd.showDialog()
	if gd.wasCanceled():
		return None
	return gd.getNextChoice()


def layout_default(cands, hints):
	"""The only candidate, or the only one starting alike with a hint (the
	section's bgsub image); else "" (the user chooses)."""
	import os
	if len(cands) == 1:
		return cands[0]
	st = lambda p: os.path.splitext(os.path.basename(p))[0]
	hit = [c for c in cands if [h for h in hints if st(h).startswith(st(c))
	                            or st(c).startswith(st(h))]]
	return hit[0] if len(hit) == 1 else ""
# ---- END SHARED: slide_files ----


# ---- SHARED: experiment_layout -- keep identical ----
# The slide's row in experiment_layout.csv (Map Experiment Folders). Text
# is UTF-8 (or Excel's Windows-1252), so accented folder names match.
def layout_text(x):
	if isinstance(x, unicode):
		return x
	try:
		return x.decode("utf-8")
	except UnicodeError:
		return x.decode("cp1252", "replace")


def layout_read_csv(path):
	import csv
	raw = open(path, "rb").read()
	if raw.startswith("\xef\xbb\xbf"):
		raw = raw[3:]
	raw = layout_text(raw).encode("utf-8")
	lines = [l for l in raw.replace("\r", "\n").split("\n") if l.strip()]
	if not lines:
		return [], []
	rows = [[layout_text(c) for c in r] for r in csv.reader(lines, delimiter=";"
	        if lines[0].count(";") > lines[0].count(",") else ",")]
	head = [h.strip().lower() for h in rows[0]]
	return head, [dict([(h, r[i].strip() if i < len(r) else "")
	                    for i, h in enumerate(head)]) for r in rows[1:]]


def layout_csvs(folder):
	"""[(experiment_layout.csv, folders below it)], folder and <= 8 up."""
	import os
	d, parts, out = os.path.abspath(layout_text(folder)), [], []
	for _k in range(9):
		p = os.path.join(d, "experiment_layout.csv")
		if os.path.isfile(p):
			out.append((p, list(parts)))
		parts.insert(0, os.path.basename(d))
		d = os.path.dirname(d)
	return out


def layout_csv_up(folder):
	return (layout_csvs(folder) or [(None, [])])[0]


def layout_csv_row(folder):
	"""(csv, level columns, row) of the slide holding folder, from the
	nearest table that has a row for it, or (None, [], None). Never raises."""
	try:
		for p, parts in layout_csvs(folder):
			head, rows = layout_read_csv(p)
			best, n = None, 0
			for r in rows:
				sp = [c for c in r.get("slide_path", "").replace("\\", "/")
				      .split("/") if c not in ("", ".")]
				if len(sp) > n and sp == parts[:len(sp)]:
					best, n = r, len(sp)
			if best:
				return p, [h for h in head if h not in ("include", "slide",
				           "slide_path", "region_folders", "sections", "notes")], best
	except:   # Java errors too
		pass
	return None, [], None


def experiment_lines(folder):
	p, levels, row = layout_csv_row(folder)
	if row is None:
		p = layout_csv_up(folder)[0]
		return p and ["! %s has no row for this slide; run Map Experiment "
		              "Folders again." % p] or []
	out = ["Experiment: %s (from %s)" % (" / ".join(
	    [row.get(l, "") for l in levels] + [row.get("slide", "")]), p)]
	if row.get("include", "").lower() in ("no", "n", "0", "false"):
		out.append("! This slide is marked include = no in %s: it is left "
		           "out of the experiment's analysis." % p)
	return out
# ---- END SHARED: experiment_layout ----


# ---- slide folder -> this stage's folders and files ---------------------
# The dialog asks for the slide folder only; the folders below are found in
# it (slide_layout block) and shown for checking before anything runs. When
# the script is given the folder parameters directly (headless tests), this
# part is skipped.
if globals().get("slideDir") is not None:
	from java.io import File as _F
	_SLIDE = slideDir.getAbsolutePath()
	_REGION = _SLIDE
	_T = (globals().get("fileType") or ".ims").strip(". ").lower()
	_RAWS = [os.path.join(_SLIDE, n) for n in (_T,) if os.path.isdir(os.path.join(_SLIDE, n))] + [_SLIDE]
	_X = ("." + _T,)            # only the file type chosen in the dialog
	_KEYS = sorted(set(sum([layout_keys(d, _X) for d in _RAWS], [])))
	if not _KEYS:
		_O = _T == "ims" and "nd2" or "ims"
		_N = sum([layout_keys(d, ("." + _O,)) for d in (os.path.join(_SLIDE, _O), _SLIDE)
		          if os.path.isdir(d)], [])
		IJ.error(SCRIPT_NAME, "No .%s files were found in %s (or its %s/ folder).%s"
		         % (_T, _SLIDE, _T, _N and "\n\nIt has .%s files: choose that file type "
		            "in the dialog." % _O or ""))
		raise SystemExit
	_SEC = layout_pick_section(_KEYS, sectionKey)
	if _SEC is None:
		raise SystemExit
	_c = sum([layout_files_for(d, key_from(_SEC), _X) for d in _RAWS], [])
	_RAWD = _c and os.path.dirname(_c[0]) or _RAWS[0]
	_got = layout_confirm(SCRIPT_NAME + " - " + _SEC, _SLIDE, _SLIDE, [
	    ("Microscope file (.ims, .nd2, ...)", "choice", _c[0] if _c else "", _c, True)])
	if _got is None:
		raise SystemExit
	inputFile = _F(_got[0])
	if outParentDir is None and os.path.normpath(_RAWD) == os.path.normpath(_SLIDE):
		outParentDir = _F(_SLIDE)       # raw files directly in the slide: tifs/ inside it


IN_FILE = inputFile.getAbsolutePath()
IN_DIR = os.path.dirname(IN_FILE)

PROJECTION_METHOD = {
    "Maximum intensity": "max",
    "Average intensity": "avg",
    "Sum slices": "sum",
    "Minimum intensity": "min",
    "Standard deviation": "sd",
    "Median": "median",
}


# ---- SHARED: errors -- keep identical ----
class StepError(Exception):
	"""A per-file failure with a message already written for a human."""
	pass
# ---- END SHARED: errors ----

# ---- SHARED: output_dir -- keep identical ----
# The output folder is CREATED, not picked: blank "Output location" puts it
# one level above the input folder (single: above the input file's folder).
def resolve_output_dir(anchor_dir, requested_name, default_name, parent_override):
	"""Create and return the output folder (None after an IJ.error).
	parent_override: a java.io.File from 'Output location', or None."""
	import os
	import re
	from ij import IJ
	name = (requested_name or "").strip() or default_name
	name = re.sub(r'[\\/:*?"<>|]', "_", name).strip() or default_name

	if parent_override is not None:
		parent = parent_override.getAbsolutePath()
		origin = "the chosen output location"
	else:
		norm = os.path.normpath(anchor_dir)
		parent = os.path.dirname(norm)
		origin = "one level above the input folder"
		if not parent or parent == norm:
			IJ.error("Output folder",
			         "Cannot step up one level from:\n%s\n\nThat looks like "
			         "a filesystem root. Fill in 'Output location' to say "
			         "where the output folder should go." % anchor_dir)
			return None

	if not os.path.isdir(parent):
		IJ.error("Output folder",
		         "%s does not exist:\n%s" % (origin[0].upper() + origin[1:], parent))
		return None

	path = os.path.join(parent, name)
	if os.path.exists(path) and not os.path.isdir(path):
		IJ.error("Output folder",
		         "A FILE (not a folder) already exists with the output folder's "
		         "name:\n%s\n\nChoose a different output folder name." % path)
		return None
	if not os.path.isdir(path):
		try:
			os.makedirs(path)
		except OSError, e:
			IJ.error("Output folder",
			         "Could not create:\n%s\n\n%s\n\nCheck write "
			         "permission, or fill in 'Output location' to put it "
			         "somewhere else." % (path, str(e)))
			return None

	if not os.access(path, os.W_OK):
		IJ.error("Output folder", "Not writable:\n%s" % path)
		return None

	return path
# ---- END SHARED: output_dir ----

# ---- SHARED: bioformats -- keep identical ----
# Opens ONE series with Bio-Formats (pyramidal .ims: not every level).
def bf_series_count(path):
	"""Number of series in the file, or 0 if it cannot be determined."""
	from java.lang import Exception as JavaException
	try:
		from loci.formats import ImageReader
		r = ImageReader()
		try:
			r.setId(path)
			return r.getSeriesCount()
		finally:
			r.close()
	except (Exception, JavaException):
		return 0


def tiff_truncation_error(path):
	"""A message if a .tif/.tiff is shorter than its header says (readers
	fill a cut-off file with zeros), else None (also when uncheckable)."""
	import os
	from java.lang import Exception as JavaException
	if os.path.splitext(path)[1].lower() not in (".tif", ".tiff"):
		return None
	try:
		from ij.io import TiffDecoder, FileInfo
		infos = TiffDecoder(os.path.dirname(path),
		                    os.path.basename(path)).getTiffInfo()
		if not infos:
			return None
		need = 0
		for fi in infos:
			if fi.stripOffsets is not None and fi.stripLengths is not None:
				for off, n in zip(fi.stripOffsets, fi.stripLengths):
					need = max(need, off + n)
			# A contiguous stack lists only the first image's strips.
			k = fi.nImages
			if k > 1 and fi.compression == FileInfo.COMPRESSION_NONE:
				need = max(need, fi.getOffset()
				           + fi.width * fi.height * fi.getBytesPerPixel() * k
				           + max(0, fi.getGap()) * (k - 1))
		size = os.path.getsize(path)
	except (Exception, JavaException):
		return None
	if size < need:
		return ("the file is truncated (%d bytes, expected at least %d) - "
		        "re-export it" % (size, need))
	return None


def bf_open(path, series_index=0):
	"""Open one series, no window: (imp, n_series). Raises StepError."""
	from java.lang import Exception as JavaException
	try:
		from loci.plugins import BF
		# 'in' is a keyword: loci.plugins.in needs __import__.
		ImporterOptions = __import__("loci.plugins.in", globals(), locals(),
		                             ["ImporterOptions"]).ImporterOptions
	except (Exception, JavaException), e:
		raise StepError("Bio-Formats is not available (%s). Install it via "
		                "Help > Update... > Manage update sites > "
		                "'Bio-Formats', then restart Fiji." % str(e))

	truncated = tiff_truncation_error(path)
	if truncated:
		raise StepError(truncated)
	n_series = bf_series_count(path)
	if n_series and series_index >= n_series:
		raise StepError(
		    "series %d was requested but the file has only %d series "
		    "(numbered from 0). Use 0 for full resolution."
		    % (series_index, n_series))
	try:
		opts = ImporterOptions()
		opts.setId(path)
		opts.setOpenAllSeries(False)
		opts.clearSeries()
		opts.setSeriesOn(series_index, True)
		opts.setVirtual(False)
		imps = BF.openImagePlus(opts)
	except (Exception, JavaException), e:
		raise StepError(
		    "Bio-Formats could not open it: %s\n"
		    "      Try opening this file by hand (File > Import > "
		    "Bio-Formats) to see the underlying error." % str(e))
	if imps is None or len(imps) == 0:
		raise StepError("Bio-Formats opened the file but returned no image.")
	imp = imps[0]
	for extra in imps[1:]:
		try:
			extra.close()
		except (Exception, JavaException):
			pass
	return imp, n_series
# ---- END SHARED: bioformats ----

# ---- SHARED: run_record -- keep identical ----
# The parameter record: every setting a run used, saved with the outputs.
# A failure to write it is only logged.
def write_run_record(out_dir, script_name, script_version, items):
	"""Write _run_<script>_<time>.txt (path or None). items: (label, value);
	a label starting with '#' is a section heading."""
	import os
	import re
	import time
	from ij import IJ
	from java.lang import Exception as JavaException
	stamp = time.strftime("%Y%m%d-%H%M%S")
	tag = re.sub(r"[^A-Za-z0-9]+", "_", script_name).strip("_")
	path = os.path.join(out_dir, "_run_%s_%s.txt" % (tag, stamp))
	def text(x):
		# Paths and names may hold non-ASCII characters; write UTF-8.
		if isinstance(x, unicode):
			return x
		if isinstance(x, str):
			try:
				return x.decode("utf-8")
			except UnicodeError:
				return x.decode("latin-1")
		return text(str(x))

	try:
		fh = open(path, "w")
		try:
			def w(line):
				fh.write(text(line).encode("utf-8"))
			w("Kapur Lab Cell Counting - parameter record\n")
			w("script   : %s  (version %s)\n" % (script_name, script_version))
			w("run at   : %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
			try:
				w("ImageJ   : %s\n" % IJ.getFullVersion())
			except (Exception, JavaException):
				pass
			w("\n")
			for label, value in items:
				label, value = text(label), text(value)
				if label.startswith("#"):
					w(u"\n[%s]\n" % label[1:].strip())
				else:
					w(u"%-32s = %s\n" % (label, value))
		finally:
			fh.close()
		return path
	except (Exception, JavaException), e:
		IJ.log("WARNING: could not write the parameter record: %s" % str(e))
		return None
# ---- END SHARED: run_record ----

# ---- SHARED: user_checks -- keep identical ----
def confirm_settings(script_name, lines, enabled):
	"""Run / Cancel window; True = go ahead. "!" lines: warnings, logged."""
	from ij import IJ
	warn = ["WARNING: " + ln[1:].strip() for ln in lines if ln.startswith("!")]
	info = [ln for ln in lines if not ln.startswith("!")]
	for w in warn:
		IJ.log(w)
	if not enabled:
		return True
	try:
		from java.awt import GraphicsEnvironment
		if GraphicsEnvironment.isHeadless():
			return True
	except Exception:
		pass
	from ij.gui import GenericDialog
	gd = GenericDialog("Check settings - " + script_name)
	gd.addMessage("Please check these settings before the run starts.\n"
	              "Press Run to go ahead, or Cancel to stop without processing anything.\n"
	              "(To skip this window, set CONFIRM_BEFORE_RUN = False in the script.)")
	body = warn + [""] * (len(warn) > 0 < len(info)) + info
	rows = max(8, (GraphicsEnvironment.getLocalGraphicsEnvironment()
	               .getMaximumWindowBounds().height - 320) // 17)
	if len(body) > rows or max([len(b) for b in body] + [0]) > 110:
		from java.awt import TextArea, Panel
		ta = TextArea("\n".join(body), min(rows, len(body) + 9), 105, TextArea.SCROLLBARS_VERTICAL_ONLY)
		ta.setEditable(False)
		pn = Panel()
		pn.add(ta)
		gd.addMessage("Scroll the box to read everything; warnings come first.")
		gd.addPanel(pn)
	elif body:
		gd.addMessage("\n".join(body))
	gd.setOKLabel("Run")
	gd.setCancelLabel("Cancel")
	gd.showDialog()
	return not gd.wasCanceled()
# ---- END SHARED: user_checks ----


# ---- SHARED: channel_names -- keep identical ----
def describe_channels(path, series_index=0):
	"""["channel 1: FITC (emission 525 nm)", ...] from the file's own
	names; [] if unreadable. Never raises."""
	from java.lang import Exception as JavaException
	out = []
	try:
		from loci.formats import ImageReader, MetadataTools
		r = ImageReader()
		meta = MetadataTools.createOMEXMLMetadata()
		r.setMetadataStore(meta)
		try:
			r.setId(path)
			if series_index < r.getSeriesCount():
				r.setSeries(series_index)
			n = r.getSizeC()
			for c in range(n):
				label = None
				try:
					label = meta.getChannelName(series_index, c)
				except (Exception, JavaException):
					label = None
				extra = ""
				try:
					em = meta.getChannelEmissionWavelength(series_index, c)
					if em is not None:
						extra = " (emission %s nm)" % int(round(em.value().doubleValue()))
				except (Exception, JavaException):
					extra = ""
				text = "channel %d: %s%s" % (c + 1, label or "(no name stored)", extra)
				out.append(text)
		finally:
			r.close()
	except (Exception, JavaException):
		return []
	return out
# ---- END SHARED: channel_names ----


# ================================================== pre-flight validation
if not HAVE_BIOFORMATS:
	IJ.error("Bio-Formats not available",
	         "This script reads microscope files with Bio-Formats, but "
	         "the loci.plugins classes could not be found.\n\n"
	         "Install it via Help > Update... > Manage update sites and tick "
	         "'Bio-Formats', then restart Fiji.")
	raise SystemExit

if not os.path.isfile(IN_FILE):
	IJ.error("Input file",
	         "The input file does not exist (or is a folder):\n%s\n\n"
	         "Choose one microscope file, e.g. "
	         "Region0011_ChannelFITCTRITC_Seq0011.nd2." % IN_FILE)
	raise SystemExit

if zStart and zStop and zStart > zStop:
	IJ.error("Z range",
	         "The first z slice (%d) is after the last (%d).\n\n"
	         "Swap them, or set either to 0 to mean the first / last slice."
	         % (zStart, zStop))
	raise SystemExit

STEM_MODE = str(OUTPUT_STEM).strip().lower()
if STEM_MODE not in ("region", "full"):
	IJ.error("OUTPUT_STEM",
	         "OUTPUT_STEM is '%s'; it must be 'region' or 'full'.\n\n"
	         "'region' names the outputs by the RegionXXXX token only "
	         "(Region0011.tif); 'full' keeps the whole input name. Fix it "
	         "in the configuration block." % OUTPUT_STEM)
	raise SystemExit

try:
	KEY_RE = re.compile(KEY_PATTERN)
except (re.error, TypeError), e:
	IJ.error("KEY_PATTERN",
	         "KEY_PATTERN is not a valid regular expression:\n%s\n\n%s\n\n"
	         "Fix it in the configuration block; the usual value is\n"
	         "    KEY_PATTERN = r\"^(Region\\d+)\"" % (KEY_PATTERN, str(e)))
	raise SystemExit


def output_stem(fname):
	"""Start of the output names for one input file. Returns (stem, note).

	note is None, or a message for the Log when the name has no region
	token and the whole input name was kept.
	"""
	full = os.path.splitext(fname)[0]
	if STEM_MODE == "full":
		return full, None
	m = KEY_RE.search(full)
	token = None
	if m:
		token = m.group(1) if KEY_RE.groups else m.group(0)
	if not token:
		return full, "no RegionXXXX token in the name; kept the full name"
	return token, None


def channel_text(chans):
	"""[2] -> 'channel 2'; [1, 3] -> 'channels 1, 3'."""
	if len(chans) == 1:
		return "channel %d" % chans[0]
	return "channels " + ", ".join([str(c) for c in chans])


# ------------------------------------------------------- channel parsing
def parse_channels(spec):
	"""'1,3-4' -> [1, 3, 4]. Raises StepError on anything unparseable."""
	out = []
	for part in [p.strip() for p in re.split(r"[,;]", spec) if p.strip()]:
		m = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
		if m:
			a, b = int(m.group(1)), int(m.group(2))
			if a > b:
				raise StepError("channel range '%s' runs backwards." % part)
			out.extend(range(a, b + 1))
			continue
		if re.match(r"^\d+$", part):
			out.append(int(part))
			continue
		raise StepError(
		    "'%s' in the channel list is not a channel number or range.\n"
		    "      Use something like  1  or  1,3  or  1-3  or  1,3-4." % part)

	seen, uniq = set(), []
	for c in out:
		if c < 1:
			raise StepError("channel numbers start at 1 (got %d)." % c)
		if c not in seen:
			seen.add(c)
			uniq.append(c)
	if not uniq:
		raise StepError("the channel list is empty.")
	return uniq


WANTED_CHANNELS = None
if selectChannels:
	try:
		WANTED_CHANNELS = parse_channels(channelList)
	except StepError, e:
		IJ.error("Channel list",
		         "The channel list '%s' could not be read:\n%s\n\n"
		         "Fix 'channels to save' in the dialog, or untick "
		         "'Save only certain channels'." % (channelList, str(e)))
		raise SystemExit


# ------------------------------------------------------------ open / save
def project(imp):
	"""Z-project per the dialog. Returns (imp, note, flagged).

	flagged is True when the note reports something the user should look
	at (projection skipped, z range clamped), False for a plain summary.
	"""
	nz = imp.getNSlices()
	if nz < 2:
		return imp, "only %d z slice(s); projection skipped" % nz, True

	first = zStart if zStart > 0 else 1
	last = zStop if zStop > 0 else nz

	note_bits = []
	if first > nz:
		raise StepError(
		    "the z range starts at slice %d but the image has only %d "
		    "slice(s)." % (first, nz))
	if last > nz:
		note_bits.append("last slice clamped from %d to %d" % (last, nz))
		last = nz
	if first > last:
		raise StepError("the z range %d-%d is empty." % (first, last))

	method = PROJECTION_METHOD[projectionType]
	try:
		out = ZProjector.run(imp, method, first, last)
	except (Exception, JavaException), e:
		raise StepError("z-projection failed: %s" % str(e))
	if out is None:
		raise StepError("z-projection returned nothing.")

	imp.close()
	note = "%s of slices %d-%d of %d" % (projectionType, first, last, nz)
	if note_bits:
		note += " (" + "; ".join(note_bits) + ")"
	return out, note, bool(note_bits)


def subset_channels(channels, wanted, nz, nt, title):
	"""Rebuild one hyperstack from the selected channel ImagePluses."""
	w = channels[0].getWidth()
	h = channels[0].getHeight()
	stack = ImageStack(w, h)

	# ImageJ hyperstack order is XYCZT.
	for t in range(1, nt + 1):
		for z in range(1, nz + 1):
			for c in wanted:
				src = channels[c - 1].getStack()
				idx = (t - 1) * nz + z
				stack.addSlice("C%d" % c, src.getProcessor(idx))

	out = ImagePlus(title, stack)
	out.setDimensions(len(wanted), nz, nt)
	# Keep the pixel size (um/px) and z step of the source.
	out.setCalibration(channels[0].getCalibration().copy())
	if len(wanted) > 1:
		out = CompositeImage(out, CompositeImage.COMPOSITE)
		for k, c in enumerate(wanted):
			try:
				out.setChannelLut(channels[c - 1].getProcessor().getLut(), k + 1)
			except (Exception, JavaException):
				pass
	return out


def save_tif(imp, out_path, src_path):
	"""Save as TIFF. Refuses to write over the input file itself."""
	if os.path.normcase(os.path.abspath(out_path)) == \
	        os.path.normcase(os.path.abspath(src_path)):
		raise StepError(
		    "the output would have the same name as the input file and "
		    "replace it:\n      %s\n      Choose a different output "
		    "folder." % out_path)
	if not IJ.saveAsTiff(imp, out_path):
		raise StepError("could not save %s\n      Check that the output "
		                "folder is writable and has free space." % out_path)


# ------------------------------------------------- settings check (pre-run)
# These read file headers only (no pixels), for the Check settings window.
def positions_in(reader):
	"""Number of XY positions in an open Bio-Formats reader, or 0.

	A multi-point .nd2 stores each position as a series of the same size.
	A resolution pyramid (.ims) also has several series, but series 1 is
	smaller than series 0, so it counts as one position (returns 0).
	"""
	n = reader.getSeriesCount()
	if n < 2:
		return 0
	reader.setSeries(0)
	size0 = (reader.getSizeX(), reader.getSizeY())
	reader.setSeries(1)
	size1 = (reader.getSizeX(), reader.getSizeY())
	reader.setSeries(0)
	return n if size1 == size0 else 0


def file_positions(path):
	"""positions_in() for a file on disk; 0 if the header cannot be read."""
	try:
		from loci.formats import ImageReader
		r = ImageReader()
		try:
			r.setId(path)
			return positions_in(r)
		finally:
			r.close()
	except (Exception, JavaException):
		return 0


def positions_text(n_pos):
	return ("file has %d positions (series of the same size); only series "
	        "%d was converted" % (n_pos, SERIES_INDEX))


def read_layout(path):
	"""(channels, z slices, [channel names], positions) from the file
	header, or None. positions is 0 for a file with one XY position."""
	try:
		from loci.formats import ImageReader, MetadataTools
		r = ImageReader()
		meta = MetadataTools.createOMEXMLMetadata()
		r.setMetadataStore(meta)
		try:
			r.setId(path)
			n_pos = positions_in(r)
			s = SERIES_INDEX
			if s >= r.getSeriesCount():
				s = 0
			r.setSeries(s)
			nc, nz = r.getSizeC(), r.getSizeZ()
			names = []
			for c in range(nc):
				try:
					nm = meta.getChannelName(s, c)
				except (Exception, JavaException):
					nm = None
				names.append(str(nm) if nm else "")
			return nc, nz, names, n_pos
		finally:
			r.close()
	except (Exception, JavaException):
		return None


def channel_layout_text(layout):
	"""(2, 3, ['FITC', 'TRITC']) -> '2 channels: FITC, TRITC'."""
	nc, nz, names = layout[:3]
	text = "%d channel%s" % (nc, "" if nc == 1 else "s")
	if [n for n in names if n]:
		text += ": " + ", ".join([n or "(no name)" for n in names])
	return text


def planned_outputs(stem, nc, nz):
	"""[(output name, [channels])] a file with nc channels and nz z slices
	will give, by the same rules as the run below. [] if it will fail."""
	wanted = WANTED_CHANNELS if WANTED_CHANNELS else range(1, nc + 1)
	if not wanted or [c for c in wanted if c > nc]:
		return []
	suffix = ""
	if doProject and nz > 1:
		first = zStart if zStart > 0 else 1
		if first > nz:
			return []
		if ADD_PROJECTION_SUFFIX:
			suffix = PROJECTION_SUFFIX.get(projectionType, "_PROJ")
	if STEM_MODE == "full":
		per_channel = splitChannels or len(wanted) == 1
	else:
		per_channel = splitChannels and len(wanted) > 1
	if per_channel:
		return [(stem + suffix + (CHANNEL_SUFFIX_TEMPLATE % c) + OUTPUT_EXTENSION, [c])
		        for c in wanted]
	extra = ""
	if STEM_MODE == "full" and 1 < len(wanted) < nc:
		extra = CHANNEL_SUBSET_SUFFIX
	return [(stem + suffix + extra + OUTPUT_EXTENSION, list(wanted))]


def first_file_lines(path, stem, layout, who):
	"""Check-window lines for one input file (who: "the first file" or
	"the file", for the wording): each channel as the file
	names it, the output file it goes to, and warnings ("!") about the
	z range, projection and channel list that this file shows up."""
	lines = []
	name = os.path.basename(path)
	if layout is None:
		lines.append("%s: %s" % (who[4:].capitalize(), name))
		lines.append("!Could not read the header of %s, so the channels and "
		             "output names cannot be shown. The file may fail to "
		             "convert." % name)
		return lines
	nc, nz, names, n_pos = layout
	lines.append("%s: %s  (%d channel(s), %d z slice(s))"
	             % (who[4:].capitalize(), name, nc, nz))
	if n_pos:
		lines.append("!%s has %d XY positions (a multi-point file: %d series "
		             "of the same size). Only series %d is converted; the "
		             "other positions are not. Check that this is the image "
		             "NeuroInfo registered." % (who.capitalize(), n_pos, n_pos,
		                                         SERIES_INDEX))
	desc = describe_channels(path, SERIES_INDEX) or \
	    ["channel %d: (no name stored)" % (c + 1) for c in range(nc)]
	plan = planned_outputs(stem, nc, nz)
	holder = {}
	for nm, chans in plan:
		for c in chans:
			holder[c] = nm
	for k, d in enumerate(desc):
		target = holder.get(k + 1)
		if not plan:
			target = "nothing (this file would fail; see the warnings)"
		lines.append("   %s -> %s" % (d, target or "not saved"))
	for nm, chans in plan:
		if len(chans) > 1:
			lines.append("   (%s holds %s in one file)" % (nm, channel_text(chans)))

	if WANTED_CHANNELS:
		too_high = [c for c in WANTED_CHANNELS if c > nc]
		if too_high:
			lines.append("!'channels to save' asks for %s, but %s "
			             "has only %d channel(s). Files without that channel "
			             "will fail." % (channel_text(too_high), who, nc))
	if doProject:
		if nz < 2:
			lines.append("!%s has only %d z slice, so no projection "
			             "is made for it and its output names get no "
			             "projection suffix." % (who.capitalize(), nz))
		else:
			if zStart > nz:
				lines.append("!The first z slice is set to %d, but %s "
				             "has only %d z slices. Files with fewer slices than "
				             "that will fail." % (zStart, who, nz))
			if zStop > nz:
				lines.append("!The last z slice is set to %d, but %s "
				             "has only %d z slices. The projection will stop at "
				             "slice %d." % (zStop, who, nz, nz))
	else:
		if nz > 1:
			lines.append("!Z-projection is off and %s has %d z "
			             "slices, so each output will be a z stack. The later "
			             "stages expect one plane per image." % (who, nz))
		if zStart or zStop:
			lines.append("!A z range is set (first %d, last %d), but "
			             "z-projection is off, so the range is not used."
			             % (zStart, zStop))
	return lines


def settings_text():
	"""The projection and channel lines of the Check settings window."""
	out = []
	if doProject:
		rng = "all slices" if not (zStart or zStop) else "slices %s-%s" % (
		    zStart if zStart else "first", zStop if zStop else "last")
		out.append("Z-projection: %s over %s" % (projectionType, rng))
	else:
		out.append("Z-projection: off (the outputs keep every z slice)")
	which = channel_text(WANTED_CHANNELS) if WANTED_CHANNELS else "all channels"
	out.append("Save: %s, %s" % (which, "each channel as its own file"
	                             if splitChannels else "kept together in one file"))
	out.append("Output names: %s" % (
	    "RegionXXXX token only (OUTPUT_STEM = region)" if STEM_MODE == "region"
	    else "whole input name (OUTPUT_STEM = full)"))
	out.append("Overwrite existing output files: %s" % ("yes" if overwrite else "no"))
	return out


def existing_lines(planned):
	"""Lines about planned outputs that already exist in OUT_DIR."""
	there = [nm for nm in planned if os.path.exists(os.path.join(OUT_DIR, nm))]
	if not there:
		return []
	if overwrite:
		return ["%d of the %d planned output file(s) already exist and will "
		        "be replaced (overwrite is on)." % (len(there), len(planned))]
	return ["!%d of the %d planned output file(s) already exist in the output "
	        "folder and will be skipped, because 'Overwrite existing output "
	        "files' is off (e.g. %s)." % (len(there), len(planned), there[0])]


# ================================================================= SETUP
fname = os.path.basename(IN_FILE)
stem, stem_note = output_stem(fname)
path = IN_FILE

# Blank 'Output location': tifs/ goes inside a slide folder that holds a
# "<region> MBF" folder (Set Up Slide Folders layout), else one level up.
_MBF_RE = re.compile(r"(^|[^A-Za-z0-9])MBF([^A-Za-z0-9]|$)", re.IGNORECASE)
_OUT_PARENT = outParentDir
if _OUT_PARENT is None and TIFS_INSIDE_SLIDE_FOLDER:
	try:
		_has_mbf = [d for d in os.listdir(IN_DIR) if _MBF_RE.search(d)
		            and os.path.isdir(os.path.join(IN_DIR, d))]
	except OSError:
		_has_mbf = []
	if _has_mbf:
		from java.io import File as _File
		_OUT_PARENT = _File(IN_DIR)
_ON = re.sub(r'[\\/:*?"<>|]', "_", (outFolderName or "").strip() or "tifs").strip() or "tifs"
_OUT_EXISTED = os.path.isdir(os.path.join(_OUT_PARENT is not None and _OUT_PARENT.getAbsolutePath()
                             or os.path.dirname(os.path.normpath(IN_DIR)), _ON))
OUT_DIR = resolve_output_dir(IN_DIR, outFolderName, "tifs", _OUT_PARENT)
if OUT_DIR is None:
	raise SystemExit

# ---- Check settings window (header read only; nothing written yet) -----
LAYOUT = read_layout(IN_FILE)
check = ["Input file: %s" % IN_FILE,
         "Output folder: %s" % OUT_DIR]
check.extend(settings_text())
check.extend(first_file_lines(IN_FILE, stem, LAYOUT, "the file"))
if LAYOUT is not None:
	check.extend(existing_lines(
	    [nm for nm, _c in planned_outputs(stem, LAYOUT[0], LAYOUT[1])]))
if not confirm_settings(SCRIPT_NAME, experiment_lines(globals().get("_SLIDE") or IN_DIR) + check, CONFIRM_BEFORE_RUN):
	if not _OUT_EXISTED and os.path.isdir(OUT_DIR) and not os.listdir(OUT_DIR):
		os.rmdir(OUT_DIR)      # created for this run only
	IJ.log("%s: cancelled at the settings check; nothing was processed."
	       % SCRIPT_NAME)
	raise SystemExit

IJ.log("=" * 64)
IJ.log("Convert to TIFF (single image)")
IJ.log("  input  : %s" % IN_FILE)
IJ.log("  output : %s" % OUT_DIR)
if doProject:
	rng = "all slices" if not (zStart or zStop) else "slices %s-%s" % (
	    zStart if zStart else "first", zStop if zStop else "last")
	IJ.log("  project: %s over %s" % (projectionType, rng))
else:
	IJ.log("  project: no")
if WANTED_CHANNELS:
	IJ.log("  channels: %s" % ", ".join([str(c) for c in WANTED_CHANNELS]))
else:
	IJ.log("  channels: all")
IJ.log("  one file per channel: %s" % splitChannels)
IJ.log("  names  : %s%s" % (
    "RegionXXXX token only (OUTPUT_STEM = region)" if STEM_MODE == "region"
    else "whole input name (OUTPUT_STEM = full)",
    ", projection suffix added" if ADD_PROJECTION_SUFFIX else ""))
IJ.log("=" * 64)


# ================================================================= RUN
written, failed, skipped, noted = [], [], [], []
log_rows = []
result_paths = []      # outputs of this file (written or already there)
outputs = []           # (output name, channels it holds) for the record
fail_msg = None

IJ.showProgress(0, 1)
IJ.log("[1/1] %s" % fname)

imp = None
channels = []
made_here = []
notes = []      # things the user should look at
infos = []      # plain summaries, Log only
if stem_note:
	notes.append(stem_note)

try:
	IJ.showStatus("[1/1] %s - opening" % fname)
	imp, n_series = bf_open(path, SERIES_INDEX)
	if n_series > 1:
		n_pos = file_positions(path)
		if n_pos:
			notes.append(positions_text(n_pos))
		else:
			infos.append("file has %d series (resolution levels); "
			             "used series %d" % (n_series, SERIES_INDEX))

	nc, nz, nt = imp.getNChannels(), imp.getNSlices(), imp.getNFrames()
	IJ.log("      opened: %dx%d  %d channel(s), %d z, %d frame(s), %d-bit"
	       % (imp.getWidth(), imp.getHeight(), nc, nz, nt,
	          imp.getBitDepth()))

	# ---- z-projection ---------------------------------------------------
	suffix = ""
	if doProject:
		IJ.showStatus("[1/1] %s - projecting" % fname)
		imp, pnote, pflag = project(imp)
		if pflag:
			notes.append(pnote)
		else:
			infos.append(pnote)
		if ADD_PROJECTION_SUFFIX and imp.getNSlices() == 1 and nz > 1:
			suffix += PROJECTION_SUFFIX.get(projectionType, "_PROJ")
		nz = imp.getNSlices()
		nt = imp.getNFrames()

	# ---- channels -------------------------------------------------------
	wanted = WANTED_CHANNELS if WANTED_CHANNELS else range(1, nc + 1)
	missing = [c for c in wanted if c > nc]
	if missing:
		raise StepError(
		    "channel(s) %s were requested but the image has only %d "
		    "channel(s).\n      Adjust the channel list, or untick "
		    "'Save only certain channels'."
		    % (", ".join([str(c) for c in missing]), nc))

	if nc > 1:
		IJ.showStatus("[1/1] %s - splitting channels" % fname)
		channels = list(ChannelSplitter.split(imp))
	else:
		channels = [imp]

	# ---- write ----------------------------------------------------------
	IJ.showStatus("[1/1] %s - saving" % fname)
	# Channel suffix: "full" names follow version 1 (one file per channel
	# whenever split, or when only one channel is kept); "region" names add
	# it only when this file gives more than one TIFF. See OUTPUT NAMING in
	# the configuration block.
	made = []       # (output name, channels it holds)
	if STEM_MODE == "full":
		per_channel = splitChannels or len(wanted) == 1
	else:
		per_channel = splitChannels and len(wanted) > 1
	if per_channel:
		for c in wanted:
			out_name = stem + suffix + (CHANNEL_SUFFIX_TEMPLATE % c) \
			           + OUTPUT_EXTENSION
			out_path = os.path.join(OUT_DIR, out_name)
			if os.path.exists(out_path) and not overwrite:
				skipped.append(out_name)
				result_paths.append(out_path)
				notes.append("%s already existed; not overwritten" % out_name)
				continue
			save_tif(channels[c - 1], out_path, path)
			made.append((out_name, [c]))
			result_paths.append(out_path)
	else:
		extra = ""
		if STEM_MODE == "full" and 1 < len(wanted) < nc:
			extra = CHANNEL_SUBSET_SUFFIX
		out_name = stem + suffix + extra + OUTPUT_EXTENSION
		out_path = os.path.join(OUT_DIR, out_name)
		if os.path.exists(out_path) and not overwrite:
			skipped.append(out_name)
			result_paths.append(out_path)
			notes.append("%s already existed; not overwritten" % out_name)
		else:
			built = False
			if len(wanted) == 1:
				combined = channels[wanted[0] - 1]
			elif list(wanted) == range(1, nc + 1):
				# All channels in their own order. Any other order
				# (e.g. "2,1") is rebuilt below, in the order given.
				combined = imp
			else:
				combined = subset_channels(channels, wanted, nz, nt,
				                           stem + suffix)
				built = True
			try:
				save_tif(combined, out_path, path)
			finally:
				if built:
					try:
						combined.changes = False
						combined.close()
					except (Exception, JavaException):
						pass
			made.append((out_name, list(wanted)))
			result_paths.append(out_path)
	made_here = [nm for nm, _c in made]
	outputs.extend(made)

	written.extend(made_here)
	if notes:
		noted.append(fname)
	for nm, chans in made:
		IJ.log("      -> %s  (%s)" % (nm, channel_text(chans)))
	for inf in infos:
		IJ.log("      . %s" % inf)
	for nt_ in notes:
		IJ.log("      ! %s" % nt_)
	IJ.log("      OK: %d TIFF(s) written" % len(made_here))

	log_rows.append([fname, str(nc), str(nz), str(nt),
	                 projectionType if doProject else "none",
	                 " ".join([str(c) for c in wanted]),
	                 str(len(made_here)),
	                 "ok" if not (notes or infos)
	                 else "ok: " + " | ".join(notes + infos)])

except StepError, e:
	failed.append(fname)
	fail_msg = str(e)
	IJ.log("      FAILED: %s" % str(e))
	log_rows.append([fname, "", "", "", "", "", "0",
	                 "FAILED: " + str(e).replace("\n", " ")])

except (Exception, JavaException), e:
	failed.append(fname)
	msg = "%s: %s" % (type(e).__name__, str(e))
	fail_msg = "unexpected error - " + msg
	IJ.log("      UNEXPECTED ERROR: %s" % msg)
	log_rows.append([fname, "", "", "", "", "", "0",
	                 "UNEXPECTED ERROR: " + msg.replace("\n", " ")])

finally:
	for obj in channels:
		try:
			obj.changes = False
			obj.close()
		except (Exception, JavaException):
			pass
	if imp is not None:
		try:
			imp.changes = False
			imp.close()
		except (Exception, JavaException):
			pass
	IJ.showProgress(1.0)
	IJ.showStatus("")


# ------------------------------------------------------------------- log
log_path = None
if writeLog:
	log_path = os.path.join(OUT_DIR, "_conversion_log_%s.csv" % stem)
	if os.path.exists(log_path) and not overwrite:
		IJ.log("Debug log NOT saved - the file already exists (tick "
		       "'Overwrite existing output files' to replace it): %s" % log_path)
		log_path = None
	else:
		try:
			fh = open(log_path, "w")
			try:
				fh.write("file,channels,z_slices,frames,projection,channels_saved,"
				         "files_written,status\n")
				for r in log_rows:
					fh.write(",".join(['"%s"' % str(c).replace('"', "'") for c in r]) + "\n")
			finally:
				fh.close()
			IJ.log("Log written: %s" % log_path)
		except IOError, e:
			log_path = None
			IJ.log("WARNING: could not write the log CSV: %s" % str(e))


# ------------------------------------------------------ parameter record
record_path = None
if WRITE_PARAMETER_RECORD and OUT_DIR and os.path.isdir(OUT_DIR):
	items = [
	    ("#Dialog", "")] + layout_record() + [
	    ("File type to convert", globals().get("fileType") or ""),
	    ("Microscope file (.ims, .nd2, ...)", IN_FILE),
	    ("Output location (blank = beside the folder that holds the input file)",
	     outParentDir.getAbsolutePath() if outParentDir is not None
	     else "(blank)"),
	    ("Name for the new output folder", outFolderName),
	    ("Output folder (resolved)", OUT_DIR),
	    ("Run a z-projection", doProject),
	    ("projection type", projectionType),
	    ("first z slice (0 = first)", zStart),
	    ("last z slice (0 = last)", zStop),
	    ("Save only certain channels", selectChannels),
	    ("channels to save, e.g. 1,3-4", channelList),
	    ("Channels used", ", ".join([str(c) for c in WANTED_CHANNELS])
	     if WANTED_CHANNELS else "all"),
	    ("Save each channel as its own file", splitChannels),
	    ("Overwrite existing output files", overwrite),
	    ("Write a debug log CSV to the output folder", writeLog),
	    ("Show the result (open the saved TIFFs)", showResult),
	    ("#Configuration", ""),
	    ("SERIES_INDEX", SERIES_INDEX),
	    ("OUTPUT_STEM", OUTPUT_STEM),
	    ("TIFS_INSIDE_SLIDE_FOLDER", TIFS_INSIDE_SLIDE_FOLDER),
	    ("KEY_PATTERN", KEY_PATTERN),
	    ("ADD_PROJECTION_SUFFIX", ADD_PROJECTION_SUFFIX),
	    ("PROJECTION_SUFFIX",
	     "(no projection)" if not doProject
	     else PROJECTION_SUFFIX.get(projectionType, "_PROJ")
	     + ("" if ADD_PROJECTION_SUFFIX else "  (not added to names)")),
	    ("CHANNEL_SUFFIX_TEMPLATE", CHANNEL_SUFFIX_TEMPLATE),
	    ("CHANNEL_SUBSET_SUFFIX", CHANNEL_SUBSET_SUFFIX
	     + ("" if STEM_MODE == "full" else "  (not used: OUTPUT_STEM = region)")),
	    ("OUTPUT_EXTENSION", OUTPUT_EXTENSION),
	    ("CONFIRM_BEFORE_RUN", CONFIRM_BEFORE_RUN),
	    ("#Inputs", ""),
	    ("file 1", IN_FILE),
	    ("#Outputs", ""),
	]
	for k, (nm, chans) in enumerate(outputs):
		items.append(("output %d" % (k + 1), "%s  (%s)" % (nm, channel_text(chans))))
	items += [
	    ("#Results", ""),
	    ("TIFFs written", len(written)),
	    ("Skipped (output existed)", len(skipped)),
	    ("Failed", ", ".join(failed) if failed else "none"),
	]
	record_path = write_run_record(OUT_DIR, SCRIPT_NAME, SCRIPT_VERSION, items)
	if record_path:
		IJ.log("Parameter record: %s" % record_path)


# ------------------------------------------------------------ show result
if showResult and not failed:
	for rp in result_paths:
		try:
			shown = IJ.openImage(rp)
		except (Exception, JavaException), e:
			shown = None
			IJ.log("WARNING: could not reopen %s: %s" % (rp, str(e)))
		if shown is None:
			IJ.log("WARNING: could not reopen %s" % rp)
			continue
		shown.show()
		IJ.log("Opened for inspection: %s" % os.path.basename(rp))


# ---------------------------------------------------- completion notice
IJ.log("-" * 64)
summary = ["TIFFs written : %d" % len(written)]
if skipped:
	summary.append("Skipped       : %d  (output existed)" % len(skipped))
if failed:
	summary.append("FAILED        : %s" % fail_msg)
if noted:
	summary.append("With notes    : see the Log window")
for line in summary:
	IJ.log(line)
IJ.log("-" * 64)

IJ.beep()

body = [("Could not convert %s." if failed else "Converted %s.") % fname, ""]
body.extend(summary)
body.append("")
body.append("Output folder:")
body.append("   " + OUT_DIR)
if log_path:
	body.append("")
	body.append("Log: " + log_path)
if record_path:
	body.append("")
	body.append("Parameter record: " + record_path)
if failed or noted:
	body.append("")
	body.append("Check the Log window for details.")
if failed:
	title = "Conversion complete - with failures"
elif noted:
	title = "Conversion complete - with problems"
else:
	title = "Conversion complete"
IJ.showMessage(title, "\n".join(body))
