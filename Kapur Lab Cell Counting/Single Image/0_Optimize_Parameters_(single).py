# 0_Optimize_Parameters_(single).py
#
# Fiji / ImageJ Jython script. Sweeps one pipeline parameter across a range
# of values on ONE image and shows the results side by side, so you can
# choose a value. Single-image version of Batch > 0 Optimize Parameters.
#
# Menu:   Plugins > Kapur Lab Cell Counting > Single image >
#         0 Optimize Parameters (single)
# Reads:  one .tif / .tiff image: raw (tifs/) for the rolling ball radius,
#         ilastik probability (probabilities/) for the threshold, probability
#         or thresholded (particle_counts/thresholded/) for size and circularity.
# Writes: into a new folder (default "optimization") one level above the
#         folder holding the image (as the batch version), a parameter record
#         (every run) and, with "Save results to disk" ticked, the results:
#           <image>_sweep_<param>_montage.tif / _stack.tif
#           <image>_live_<param>_<value>.tif        (Live preview)
#           _run_0_Optimize_Parameters_single_<timestamp>.txt
#                                                   (parameter record)
#           _sweep_<param>_log_<image stem>.csv     (optional debug log)
#
# Output: Montage (labelled panels), Stack (scrollable) or Live preview.
#
# The stage check (see PROBABILITY_MARKER) is advisory: a folder named
# "thresholded" or "_thresh" in the filename marks a thresholded image.
#
# The FIXED values are part of the answer (Log and parameter record). Images
# are processed as in the later stages (8-bit on stage 3's fixed scale,
# threshold maximum 255, rolling ball on the whole image). With a crop,
# counts are for the crop only; use "Whole image" to compare with stage 3.
#
# Usage: Plugins > Kapur Lab Cell Counting > Single image >
#        0 Optimize Parameters (single), or open this file in the Script
#        Editor (File > New > Script..., or Plugins > Scripting > Script
#        Editor) with Language = Python (Jython) and press Run.

#@ File    (label="Slide folder (the scripts find its subfolders)", style="directory") slideDir
#@ String  (label="Region (its MBF folder; blank = choose from a list)", value="", required=false) regionName
#@ String  (label="Section (e.g. Region0011; blank = choose from a list)", value="", required=false) sectionKey
#@ String  (label="Parameter to sweep", choices={"Background subtraction: rolling ball radius", "Threshold: manual 8-bit value", "Analyze Particles: minimum size", "Analyze Particles: maximum size", "Analyze Particles: minimum circularity", "Analyze Particles: maximum circularity"}, style="listBox") sweepParam
#@ String  (label="Output", choices={"Montage", "Scrollable stack", "Montage and stack", "Live preview"}, style="listBox") outputMode
#@ Integer (label="Channel (probability: 1 = signal; 0 = first/only)", value=1, min=0) channel
#@ String  (label="Region to show", choices={"Densest area (auto)", "Centre of image", "Whole image"}, style="listBox") cropMode
#@ Integer (label="   crop size (pixels)", value=512, min=64) cropSize
#@ File    (label="Output location (blank = beside the folder that holds the input file)", style="directory", required=false) outParentDir
#@ String  (label="Name for the new output folder", value="optimization") outFolderName
#@ Boolean (label="Save results to disk", value=true) saveResults
#@ Boolean (label="Overwrite existing output files", value=false) overwrite
#@ Boolean (label="Write a debug log CSV", value=false) writeLog


# =========================================================================
# ===  USER CONFIGURATION  ================================================
# =========================================================================
# Everything you may want to change is between these banners; nothing below
# the END banner needs editing for routine use.

# ---- SLIDERS ------------------------------------------------------------
# Parameters given a slider instead of a numeric field: key -> (min, max),
# values clamped. Keys: rolling, threshold, minsize, maxsize, mincirc, maxcirc
SLIDER_RANGES = {
    "rolling": (0, 2000),
}

# Live preview of these updates when the slider is RELEASED (slow ones).
SLIDER_RELEASE_ONLY = ["rolling"]


# ---- SENSIBLE SWEEP RANGES ---------------------------------------------
# Starting (from, to, steps, spacing) offered when generating values.
DEFAULT_RANGES = {
    "rolling":  (10.0,  200.0, 9, "logarithmic"),
    "threshold": (60.0, 240.0, 9, "linear"),
    "minsize":  (2.0,   200.0, 9, "logarithmic"),
    "maxsize":  (50.0, 5000.0, 9, "logarithmic"),
    "mincirc":  (0.0,     0.9, 9, "linear"),
    "maxcirc":  (0.2,     1.0, 9, "linear"),
}

# Starting values for the parameters held fixed.
DEFAULT_FIXED = {
    "rolling": 50.0,
    "threshold": 128,
    "minsize": 10.0,
    "maxsize": 0.0,        # 0 = no limit
    "mincirc": 0.0,
    "maxcirc": 1.0,
    "holes": False,
    "edges": False,
    "watershed": False,
}

# Values that must be whole numbers are rounded on generation.
INTEGER_PARAMS = ["threshold"]


# ---- BACKGROUND SUBTRACTION --------------------------------------------
# Other Subtract Background options for the rolling ball panels. Keep them
# identical to 2b's, or the radius chosen here behaves differently.
BG_LIGHT_BACKGROUND = False      # True for dark objects on a light field
BG_SLIDING_PARABOLOID = False    # True copes better with uneven illumination
BG_DISABLE_SMOOTHING = False     # True preserves noise; usually leave False


# ---- LABELS -------------------------------------------------------------
# Labels are drawn INTO the panel pixels. Font size 0 = from the panel
# width, never below LABEL_FONT_MIN.
LABEL_FONT_SIZE = 0
LABEL_FONT_MIN = 36
LABEL_FONT_DIVISOR = 10.0

LABEL_TEXT_COLOR = (255, 255, 255)
LABEL_BOX_COLOR = (0, 0, 0)

LABEL_INCLUDES_COUNT = True


# ---- MONTAGE ------------------------------------------------------------

MONTAGE_BORDER = 4
MONTAGE_SCALE = 1.0
MONTAGE_COLUMNS = 0          # 0 = roughly square

OUTLINE_COLOR = (255, 255, 0)


# ---- INPUT --------------------------------------------------------------

TIF_EXTENSIONS = [".tif", ".tiff"]
# A probability image is in a folder named with "probabilit" (any case), or
# its filename has PROBABILITY_MARKER (e.g. "_Probabilities"; blank = off).
PROBABILITY_MARKER = ""
SIZE_IN_PIXELS = True


# ---- OUTPUT LOCATION ----------------------------------------------------
#
# With "Output location" blank, optimization/ goes one level above the
# folder holding the image (the slide folder), after stepping out of these
# stage 3 subfolders: particle_counts/thresholded/ still gives
# <slide>/optimization/.
NESTED_INPUT_FOLDERS = ["thresholded", "watershed", "QC", "particle_rois"]


# ---- PARAMETER RECORD ---------------------------------------------------
# Every run writes _run_0_Optimize_Parameters_single_<timestamp>.txt (all
# settings), even with "Save results to disk" off.
WRITE_PARAMETER_RECORD = True


# ---- SAFETY CHECKS ------------------------------------------------------
# Show the "Check settings" window first. False skips it (warnings logged).
CONFIRM_BEFORE_RUN = True

# ---- SECTION KEYS ----
# Used to list a slide's sections (RegionXXXX) when the slide folder is given.
KEY_PATTERN = r"^(Region\d+)"
CASE_INSENSITIVE_KEYS = True
REQUIRE_IN_NAME = ""
EXCLUDE_IN_NAME = ""

# =========================================================================
# ===  END OF USER CONFIGURATION  =========================================
# =========================================================================

SCRIPT_NAME = "0_Optimize_Parameters_(single)"
SCRIPT_VERSION = "2.0"

# Upper threshold bound of every sweep; keep stage 3's "Threshold: maximum
# (8-bit)" at 255 too, or the values found here will not transfer.
THRESHOLD_MAX = 255


import os
import re
import math

from ij import IJ, ImagePlus, ImageStack, Prefs, WindowManager
from java.lang import Exception as JavaException
ANY_ERROR = (Exception, JavaException)
from ij.gui import GenericDialog, NonBlockingGenericDialog, DialogListener
from ij.measure import ResultsTable, Calibration, Measurements
from ij.plugin import Duplicator, ChannelSplitter, MontageMaker
from ij.plugin.filter import ParticleAnalyzer, ThresholdToSelection
from ij.process import ImageProcessor, ColorProcessor
from java.awt import Color, Font
from java.awt.event import AdjustmentListener

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
	if globals().get("_UNATTENDED"):
		return _UNATTENDED.pick_region(slide, typed)
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
	if globals().get("_UNATTENDED"):
		return _UNATTENDED.confirm(title, slide, region, fields)
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
	_REGION = layout_pick_region(_SLIDE, regionName)
	if _REGION is None:
		raise SystemExit
	_sub = "tifs" if sweepParam.startswith("Background") else "probabilities"
	_KEYS = layout_keys(layout_find(_SLIDE, _REGION, _sub), ('.tif', '.tiff'))
	_SEC = layout_pick_section(_KEYS, sectionKey)
	if _SEC is None:
		raise SystemExit
	_K = key_from(_SEC)
	_HINTS = layout_files_for(layout_find(_SLIDE, _REGION, "processed_bgsub_cleared"), _K, (".tif", ".tiff"))
	_c_inputFile = layout_files_for(layout_find(_SLIDE, _REGION, _sub), _K, ('.tif', '.tiff'))
	_got = layout_confirm(SCRIPT_NAME + " - " + _SEC, _SLIDE, _REGION, [
	    ('Image to optimise on (from tifs/ or probabilities/)', "choice", layout_default(_c_inputFile, _HINTS), _c_inputFile, True),
	])
	if _got is None:
		raise SystemExit
	inputFile = _F(_got[0]) if _got[0] else None


IN_FILE = inputFile.getAbsolutePath()
IN_DIR = os.path.dirname(IN_FILE)

PARAM_KEYS = {
    "Background subtraction: rolling ball radius": "rolling",
    "Threshold: manual 8-bit value": "threshold",
    "Analyze Particles: minimum size": "minsize",
    "Analyze Particles: maximum size": "maxsize",
    "Analyze Particles: minimum circularity": "mincirc",
    "Analyze Particles: maximum circularity": "maxcirc",
}
PKEY = PARAM_KEYS[sweepParam]

STAGE_RAW = (PKEY == "rolling")

PARAM_LABEL = {
    "rolling": "radius",
    "threshold": "thr",
    "minsize": "min size",
    "maxsize": "max size",
    "mincirc": "min circ",
    "maxcirc": "max circ",
}[PKEY]

MODE_LIVE = (outputMode == "Live preview")
MODE_MONTAGE = outputMode in ("Montage", "Montage and stack")
MODE_STACK = outputMode in ("Scrollable stack", "Montage and stack")


# ---- SHARED: errors -- keep identical ----
class StepError(Exception):
	"""A per-file failure with a message already written for a human."""
	pass
# ---- END SHARED: errors ----


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
	if globals().get("_UNATTENDED"):         # Run Stages for an Animal
		return _UNATTENDED.check(script_name, lines)
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


# ---- SHARED: prob8 -- keep identical ----
# Probability maps go to 8-bit on a FIXED scale (16-bit 0-65535; 32-bit 0-1,
# or 0-255 when values exceed 1), so 128 means p = 0.50 in every image.
def probability_to_8bit(imp, file_max=None):
	"""imp (one channel) to 8-bit in place on a fixed scale; returns a Log
	note. StepError for RGB, or 32-bit outside 0-1 and 0-255. file_max: the
	largest value in the whole map (all channels), so that a cell channel
	with no value above 1 is not read as the 0-1 scale."""
	from ij.process import ImageConverter, StackStatistics
	bd = imp.getBitDepth()
	if bd == 8:
		return "8-bit, used as it is"
	if bd == 24:
		raise StepError("the image is RGB colour, not an ilastik probability map.")
	if bd == 16:
		lo, hi = 0.0, 65535.0
		note = "16-bit: 0-65535 mapped onto 0-255 (fixed scale)"
	else:
		# ilastik writes 32-bit 0-1, or 0-255 floats ("renormalize" only).
		st = StackStatistics(imp)
		top = max(st.max, file_max or 0.0)
		if st.min < -1e-6 or top > 255.0 + 1e-3:
			raise StepError(
			    "the image is 32-bit with values from %.4g to %.4g, outside "
			    "both probability scales (0-1 and 0-255), so the threshold "
			    "cannot be applied safely. Export the probabilities from "
			    "ilastik as integer 8-bit (renormalize 0.00-1.00 to 0-255)."
			    % (st.min, top))
		if top <= 1.0 + 1e-6:
			lo, hi = 0.0, 1.0
			note = "32-bit: probability 0-1 mapped onto 0-255 (fixed scale)"
		else:
			lo, hi = 0.0, 255.0
			note = ("32-bit on the 0-255 scale (values up to %.4g): used on "
			        "0-255 directly (fixed scale)" % top)
	old = ImageConverter.getDoScaling()
	try:
		ImageConverter.setDoScaling(True)
		imp.setDisplayRange(lo, hi)
		if imp.getStackSize() > 1:
			from ij.process import StackConverter
			StackConverter(imp).convertToGray8()
		else:
			ImageConverter(imp).convertToGray8()
	finally:
		ImageConverter.setDoScaling(old)
	if imp.getBitDepth() != 8:
		raise StepError("the conversion to 8-bit did not take effect.")
	return note
# ---- END SHARED: prob8 ----


# ================================================== pre-flight validation
if not HAVE_BIOFORMATS:
	IJ.error("Bio-Formats not available",
	         "This script opens images with Bio-Formats, which was not found."
	         "\n\nInstall it via Help > Update... > Manage update sites "
	         "('Bio-Formats'), then restart Fiji.")
	raise SystemExit

if not os.path.isfile(IN_FILE):
	IJ.error("Input image",
	         "The image file does not exist:\n%s\n\n"
	         "Choose one image (from tifs/ for the rolling ball radius, from "
	         "probabilities/ for everything else)." % IN_FILE)
	raise SystemExit

if os.path.splitext(IN_FILE)[1].lower() not in TIF_EXTENSIONS:
	IJ.error("Input image",
	         "This is not a %s file:\n%s\n\n"
	         "Choose a .tif image (from tifs/ or probabilities/). Convert "
	         "other formats with 1 Convert to Tif first."
	         % (" / ".join(TIF_EXTENSIONS), IN_FILE))
	raise SystemExit


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


# ------------------------------------------------------------ output anchor
# A region folder (Set Up Slide Folders) has the word MBF in its name.
MBF_FOLDER_RE = re.compile(r"(^|[^A-Za-z0-9])MBF([^A-Za-z0-9]|$)", re.IGNORECASE)


def mbf_output_parent(anchor):
	"""Where a blank 'Output location' sends the output (a File), or None for
	one level above anchor: into the slide's only "<region> MBF" folder when
	the slide has one MBF folder and no protocol-layout subfolders."""
	from java.io import File
	if not anchor:
		return None
	parent = os.path.dirname(os.path.normpath(anchor))
	if not parent or MBF_FOLDER_RE.search(os.path.basename(parent)):
		return None
	try:
		names = sorted(os.listdir(parent))
	except OSError:
		return None
	if [d for d in names if d.lower() in ("xml", "rois", "probabilities",
	                                      "processed_bgsub_cleared",
	                                      "particle_counts")]:
		return None
	mbfs = layout_regions(parent)
	if len(mbfs) == 1:
		return File(os.path.join(parent, mbfs[0]))
	return None


def output_anchor(folder):
	"""The input folder after stepping out of NESTED_INPUT_FOLDERS."""
	nested = [n.lower() for n in NESTED_INPUT_FOLDERS]
	a = os.path.normpath(folder)
	while os.path.basename(a).lower() in nested:
		up = os.path.dirname(a)
		if not up or up == a:
			break
		a = up
	return a


OUT_ANCHOR = output_anchor(IN_DIR)
OUT_PARENT = (outParentDir if outParentDir is not None
              else mbf_output_parent(OUT_ANCHOR))
if outParentDir is None and globals().get("_REGION") not in (None, globals().get("_SLIDE")):
	OUT_PARENT = _F(_REGION)       # slide mode: the region chosen


# ------------------------------------------------------------ stage check
def folder_parts(path):
	"""Lower-case names of the folders above path."""
	return [p.lower() for p in
	        re.split(r"[\\/]+", os.path.dirname(os.path.abspath(path)))]


def looks_like_probability(path):
	fname = os.path.basename(path)
	if PROBABILITY_MARKER and PROBABILITY_MARKER.lower() in fname.lower():
		return True
	return any(["probabilit" in p for p in folder_parts(path)])


def looks_like_thresholded(path):
	return ("_thresh" in os.path.basename(path).lower()
	        or "thresholded" in folder_parts(path))


def prob_rule_text():
	"""How a probability image is recognised, for the warnings."""
	text = "no folder above them has 'probabilit' in its name (e.g. probabilities/)"
	if PROBABILITY_MARKER:
		text += " and no filename contains '%s'" % PROBABILITY_MARKER
	return text


def stage_warning_for(paths):
	"""Warning text when the images look like the wrong stage."""
	looks_prob = [looks_like_probability(p) for p in paths]
	looks_thr = [looks_like_thresholded(p) for p in paths]
	if STAGE_RAW:
		if any(looks_prob):
			return ("The rolling ball radius applies to RAW images, before "
			        "ilastik, but these look like ilastik probability images "
			        "(a folder above them has 'probabilit' in its name%s). "
			        "Point this at the raw images (tifs/)."
			        % (", or the filename contains '%s'" % PROBABILITY_MARKER
			           if PROBABILITY_MARKER else ""))
		return None
	if PKEY == "threshold":
		if any(looks_thr):
			return ("The threshold applies to ilastik PROBABILITY images, but "
			        "these look like images already thresholded by stage 3 "
			        "(a folder named 'thresholded' or '_thresh' in the "
			        "filename). A black-and-white mask has nothing left to "
			        "threshold. Point this at probabilities/.")
		if not any(looks_prob):
			return ("'%s' applies to ilastik PROBABILITY images, but %s. If "
			        "these are raw images the result will be meaningless."
			        % (sweepParam, prob_rule_text()))
		return None
	if not any([a or b for a, b in zip(looks_prob, looks_thr)]):
		return ("'%s' applies to ilastik PROBABILITY images or to images "
		        "already thresholded by stage 3, but %s, and none is in a "
		        "folder named 'thresholded' or has '_thresh' in its name. If "
		        "these are raw images the result will be meaningless."
		        % (sweepParam, prob_rule_text()))
	return None


# =========================================================================
# ===  SECOND DIALOG  =====================================================
# =========================================================================
# Only the fields this sweep needs. Fixed particle settings: (key, label, decimals)
FIXED_FIELDS = [("threshold", "Threshold (8-bit)", 0),
                ("minsize", "Minimum size", 2),
                ("maxsize", "Maximum size (0 = no limit)", 2),
                ("mincirc", "Minimum circularity", 2),
                ("maxcirc", "Maximum circularity", 2)]


def slider_or_number(gd, key, label, default, decimals):
	rng = SLIDER_RANGES.get(key)
	if rng is not None:
		lo, hi = rng
		val = min(max(default, lo), hi)
		gd.addSlider(label, lo, hi, val)
		return True
	gd.addNumericField(label, default, decimals)
	return False


def show_settings_dialog():
	"""Returns a settings dict, or None if cancelled."""
	gd = GenericDialog("Settings - %s" % sweepParam)
	order = []

	d_from, d_to, d_steps, d_spacing = DEFAULT_RANGES[PKEY]
	dec = 0 if PKEY in INTEGER_PARAMS else 2

	if MODE_LIVE:
		gd.addMessage("Live preview: move the control and the image follows.\n"
		              "The chosen image is used.")
	else:
		gd.addMessage("Values to compare. Fill in the list, or leave it blank\n"
		              "and a range will be generated below.")
		gd.addStringField("Values (comma separated)", "", 34)
		slider_or_number(gd, PKEY, "Generate from", d_from, dec)
		slider_or_number(gd, PKEY, "Generate to", d_to, dec)
		gd.addNumericField("How many", d_steps, 0)
		gd.addChoice("Spacing", ["linear", "logarithmic"], d_spacing)
		order += [("str", "values"), ("num", "gen_from"), ("num", "gen_to"),
		          ("num", "gen_steps"), ("choice", "spacing")]

	if not STAGE_RAW:
		gd.addMessage("Held fixed while %s is swept:" % PARAM_LABEL)

		if PKEY == "threshold":
			gd.addCheckbox("Skip particle analysis "
			               "(show the thresholded area only)", False)
			order.append(("bool", "skip"))
		for key, label, dec_ in FIXED_FIELDS:
			if key != PKEY:
				slider_or_number(gd, key, label, DEFAULT_FIXED[key], dec_)
				order.append(("num", key))
		for key, label in (("holes", "Include holes"),
		                   ("edges", "Exclude particles on edges"),
		                   ("watershed", "Watershed")):
			gd.addCheckbox(label, DEFAULT_FIXED[key])
			order.append(("bool", key))

		gd.addChoice("Render as",
		             ["Particle outlines on image", "Binary mask"],
		             "Particle outlines on image")
		order.append(("choice", "render"))
	else:
		gd.addMessage("The rolling ball radius acts on raw images (before\n"
		              "ilastik): no threshold or particle settings apply.")

	gd.showDialog()
	if gd.wasCanceled():
		return None

	S = dict(DEFAULT_FIXED)
	S["skip"] = False
	S["render"] = "Particle outlines on image"
	get = {"num": gd.getNextNumber, "str": gd.getNextString,
	       "bool": gd.getNextBoolean, "choice": gd.getNextChoice}
	for kind, key in order:
		S[key] = get[kind]()

	if PKEY in INTEGER_PARAMS:
		for k in ("gen_from", "gen_to"):
			if k in S:
				S[k] = float(int(round(S[k])))
	if "threshold" in S:
		S["threshold"] = int(round(S["threshold"]))
	S["skip"] = bool(S.get("skip", False)) and PKEY == "threshold"
	return S


# ------------------------------------------------------- sweep values
def build_values(S):
	txt = (S.get("values") or "").strip()
	if txt:
		raw = [t.strip() for t in re.split(r"[,;\s]+", txt) if t.strip()]
		vals = []
		for t in raw:
			try:
				vals.append(float(t))
			except ValueError:
				raise StepError("'%s' in the Values list is not a number.\n"
				                "      Use e.g. 20, 50, 100, 200." % t)
		if len(vals) < 2:
			raise StepError("at least two values are needed to compare "
			                "(got %d)." % len(vals))
		return vals, "from the Values list"

	start = S.get("gen_from", 0.0)
	stop = S.get("gen_to", 0.0)
	steps = int(S.get("gen_steps", 9))
	spacing = S.get("spacing", "linear")

	if stop <= start:
		raise StepError("the generate range is empty: 'to' (%s) must be "
		                "greater than 'from' (%s)." % (stop, start))
	if steps < 2:
		raise StepError("'How many' must be at least 2 (got %d)." % steps)

	if spacing == "logarithmic":
		if start <= 0:
			raise StepError("logarithmic spacing needs a 'from' value above "
			                "zero (got %s)." % start)
		lo, hi = math.log(start), math.log(stop)
		vals = [math.exp(lo + (hi - lo) * i / float(steps - 1))
		        for i in range(steps)]
	else:
		vals = [start + (stop - start) * i / float(steps - 1)
		        for i in range(steps)]

	if PKEY in INTEGER_PARAMS:
		uniq = []
		for iv in [float(int(round(v))) for v in vals]:
			if iv not in uniq:
				uniq.append(iv)
		vals = uniq

	return vals, "generated"


def fmt_value(v):
	if PKEY in INTEGER_PARAMS or abs(v - round(v)) < 1e-9:
		return "%d" % int(round(v))
	if abs(v) < 10:
		return "%.2f" % v
	return "%.1f" % v


# ------------------------------------------------------------ image prep
def open_image(path):
	imp, n_series = bf_open(path)

	if imp.getBitDepth() == 24:
		imp.close()
		raise StepError("this is an RGB image, not single- or multi-channel "
		                "data.")

	nch = imp.getNChannels()
	want = channel if channel > 0 else 1
	if nch > 1:
		if nch < want:
			imp.close()
			raise StepError("channel %d was requested but the image has only "
			                "%d channel(s)." % (want, nch))
		chans = ChannelSplitter.split(imp)
		picked = chans[want - 1]
		close_quietly(*[c for j, c in enumerate(chans) if j != want - 1] + [imp])
		imp = picked
	elif imp.getStackSize() > 1:
		picked = Duplicator().run(imp, 1, 1, want, want, 1, 1)
		imp.close()
		imp = picked

	if SIZE_IN_PIXELS:
		imp.setCalibration(Calibration())
	return imp


def densest_origin(ip, size):
	w, h = ip.getWidth(), ip.getHeight()
	if w <= size and h <= size:
		return 0, 0

	factor = max(1, int(max(w, h) / 512))
	small = ip.duplicate()
	small.setInterpolationMethod(ImageProcessor.BILINEAR)
	sw, sh = max(1, w // factor), max(1, h // factor)
	small = small.resize(sw, sh).convertToFloat()
	sigma = max(1.0, (size / float(factor)) / 3.0)
	try:
		small.blurGaussian(sigma)
	except ANY_ERROR:
		pass

	best, bx, by = None, 0, 0
	half = int((size / float(factor)) / 2)
	for y in range(half, max(half + 1, sh - half)):
		for x in range(half, max(half + 1, sw - half)):
			v = small.getf(x, y)
			if best is None or v > best:
				best, bx, by = v, x, y

	cx, cy = bx * factor, by * factor
	return (max(0, min(w - size, cx - size // 2)),
	        max(0, min(h - size, cy - size // 2)))


def crop_box(imp):
	"""((x, y, size) or None for the whole image, label)."""
	if cropMode.startswith("Whole"):
		return None, "whole image"

	w, h = imp.getWidth(), imp.getHeight()
	size = min(cropSize, w, h)
	note_size = "" if size >= cropSize else " (image smaller than the crop)"

	if cropMode.startswith("Densest"):
		x, y = densest_origin(imp.getProcessor(), size)
		label = "densest %dx%d at %d,%d" % (size, size, x, y)
	else:
		x, y = (w - size) // 2, (h - size) // 2
		label = "centre %dx%d" % (size, size)
	return (x, y, size), label + note_size


def cut(imp, box):
	"""A new image holding the box (x, y, size) of imp. imp stays open."""
	x, y, size = box
	ip = imp.getProcessor()
	ip.setRoi(x, y, size, size)
	out = ImagePlus(imp.getTitle(), ip.crop())
	ip.resetRoi()
	if SIZE_IN_PIXELS:
		out.setCalibration(Calibration())
	return out


def crop(imp):
	"""Crop imp to the region to show. Closes imp when it crops."""
	box, label = crop_box(imp)
	if box is None:
		return imp, label
	out = cut(imp, box)
	imp.close()
	return out, label


def crop_count_note():
	"""Why counts in a cropped panel differ from stage 3, or None."""
	if STAGE_RAW or cropMode.startswith("Whole"):
		return None
	return ("Counts are for the crop only: a particle cut by the crop edge "
	        "counts as a smaller piece (it can fall below the minimum size, "
	        "and 'Exclude particles on edges' drops it), while stage 3 counts "
	        "whole particles over the whole image. Choose 'Whole image' to "
	        "compare with stage 3.")


def probability_8bit(imp):
	"""probability_to_8bit(): its note, or None for an 8-bit image."""
	was_8bit = imp.getBitDepth() == 8
	try:
		note = probability_to_8bit(imp)
	except StepError, e:
		raise StepError("cannot convert this image to 8-bit: %s" % str(e))
	return None if was_8bit else note


def file_bit_depth(path):
	"""Bits per pixel from the file header (8, 16, 32), or None."""
	try:
		from loci.formats import ImageReader, FormatTools
		r = ImageReader()
		try:
			r.setId(path)
			return 8 * FormatTools.getBytesPerPixel(r.getPixelType())
		finally:
			r.close()
	except ANY_ERROR:
		return None


# ------------------------------------------------------------ processing
def analyze(mask_imp, S, min_size, max_size, min_circ, max_circ):
	ip = mask_imp.getProcessor()
	ip.setThreshold(128, 255, ImageProcessor.NO_LUT_UPDATE)
	mask_imp.setOverlay(None)

	opts = (ParticleAnalyzer.SHOW_OVERLAY_OUTLINES
	        | (S["holes"] and ParticleAnalyzer.INCLUDE_HOLES or 0)
	        | (S["edges"] and ParticleAnalyzer.EXCLUDE_EDGE_PARTICLES or 0))

	rt = ResultsTable()
	pa = ParticleAnalyzer(
	    opts, Measurements.AREA | Measurements.SHAPE_DESCRIPTORS, rt,
	    min_size, max_size if max_size > 0 else float("inf"),
	    min_circ, max_circ)
	pa.setHideOutputImage(True)
	if not pa.analyze(mask_imp, ip):
		raise StepError("Analyze Particles reported a failure.")

	ov = mask_imp.getOverlay()
	particles = [ov.get(j) for j in range(ov.size())] if ov is not None else []
	mask_imp.setOverlay(None)
	return rt.size(), particles


def outline_threshold(base8, mask):
	mip = mask.getProcessor().duplicate()
	mip.setThreshold(128, 255, ImageProcessor.NO_LUT_UPDATE)
	sel = ThresholdToSelection().convert(mip)
	return render_outlines(base8, [sel] if sel is not None else [])


def render_outlines(base8, particles):
	cp = base8.getProcessor().duplicate().convertToRGB()
	if particles:
		cp.setColor(Color(*OUTLINE_COLOR))
		cp.setLineWidth(1)
		for r in particles:
			try:
				cp.draw(r)
			except ANY_ERROR:
				pass
	return cp


def limits_at(S, v):
	"""(min size, max size, min circ, max circ) with the swept one at v."""
	return [v if PKEY == k else S[k]
	        for k in ("minsize", "maxsize", "mincirc", "maxcirc")]


def one_probability_panel(base8, S, v):
	thr = int(round(v)) if PKEY == "threshold" else int(S["threshold"])
	min_size, max_size, min_circ, max_circ = limits_at(S, v)

	if not S["skip"]:
		if min_circ > max_circ:
			raise StepError("minimum circularity (%.2f) exceeds maximum "
			                "(%.2f) at this value." % (min_circ, max_circ))
		if max_size > 0 and min_size > max_size:
			raise StepError("minimum size (%s) exceeds maximum size (%s) at "
			                "this value." % (min_size, max_size))

	mask = Duplicator().run(base8)
	mask.getProcessor().setThreshold(thr, THRESHOLD_MAX,
	                                 ImageProcessor.NO_LUT_UPDATE)
	IJ.run(mask, "Convert to Mask", "")
	if S["watershed"]:
		IJ.run(mask, "Watershed", "")

	area_pct = 100.0 * mask.getStatistics(Measurements.MEAN).mean / 255.0

	count, particles = None, None
	if not S["skip"]:
		count, particles = analyze(mask, S, min_size, max_size,
		                           min_circ, max_circ)

	if S["render"].startswith("Binary"):
		cp = mask.getProcessor().duplicate().convertToRGB()
	elif S["skip"]:
		cp = outline_threshold(base8, mask)
	else:
		cp = render_outlines(base8, particles)

	mask.close()
	return {"value": v, "count": count, "area": area_pct, "processor": cp}


def bg_options(v):
	"""Subtract Background options for radius v, built the same way as 2b."""
	return "rolling=%s" % v + "".join([s for on, s in (
	    (BG_LIGHT_BACKGROUND, " light"), (BG_SLIDING_PARABOLOID, " sliding"),
	    (BG_DISABLE_SMOOTHING, " disable")) if on])


def subtracted_region(raw_imp, box, v):
	"""Subtract Background at radius v on the WHOLE image, as 2b does, then
	cut out box (None = whole image)."""
	dup = Duplicator().run(raw_imp)
	IJ.run(dup, "Subtract Background...", bg_options(v))
	if box is None:
		return dup
	out = cut(dup, box)
	close_quietly(dup)
	return out


def rolling_panel_from(sub, v, display_range):
	"""Panel for one radius from its subtracted region. Closes sub."""
	lo, hi = display_range
	sub.setDisplayRange(lo, hi)
	if sub.getBitDepth() != 8:
		IJ.run(sub, "8-bit", "")
	cp = sub.getProcessor().duplicate().convertToRGB()
	close_quietly(sub)
	return {"value": v, "count": None, "area": None, "processor": cp}


def rolling_panels(raw_imp, box, values, status):
	"""(panels, (min, max)): every radius, one shared display range."""
	subs = []
	try:
		for j, v in enumerate(values):
			status(j, v)
			subs.append(subtracted_region(raw_imp, box, v))
		gmin, gmax = None, None
		for sub in subs:
			st = sub.getStatistics(Measurements.MIN_MAX)
			gmin = st.min if gmin is None else min(gmin, st.min)
			gmax = st.max if gmax is None else max(gmax, st.max)
		if gmax is None or gmax <= gmin:
			gmax = (gmin or 0) + 1
		panels = []
		while subs:
			sub = subs.pop(0)
			panels.append(rolling_panel_from(sub, values[len(panels)],
			                                 (gmin, gmax)))
		return panels, (gmin, gmax)
	finally:
		close_quietly(*subs)


# ------------------------------------------------------------- labelling
def panel_label(p):
	label = "%s=%s" % (PARAM_LABEL, fmt_value(p["value"]))
	if LABEL_INCLUDES_COUNT:
		if p.get("count") is not None:
			label += "  n=%d" % p["count"]
			if not cropMode.startswith("Whole"):
				label += " (crop)"
		elif p.get("area") is not None:
			label += "  %.1f%%" % p["area"]
	return label


def burn_label(cp, text):
	w = cp.getWidth()
	size = (LABEL_FONT_SIZE if LABEL_FONT_SIZE > 0
	        else max(LABEL_FONT_MIN, int(w / LABEL_FONT_DIVISOR)))
	cp.setAntialiasedText(True)
	while True:
		cp.setFont(Font("SansSerif", Font.BOLD, size))
		pad = max(4, size // 5)
		tw = cp.getStringWidth(text)
		if tw + 2 * pad <= w or size <= 10:
			break
		size -= 2

	box_w = min(w, tw + 2 * pad)
	box_h = size + 2 * pad
	cp.setColor(Color(*LABEL_BOX_COLOR))
	cp.setRoi(0, 0, box_w, box_h)
	cp.fill()
	cp.resetRoi()
	cp.setColor(Color(*LABEL_TEXT_COLOR))
	cp.drawString(text, pad, pad + size)
	return cp


def build_outputs(panels, title):
	w = panels[0]["processor"].getWidth()
	h = panels[0]["processor"].getHeight()
	stack = ImageStack(w, h)

	for p in panels:
		text = panel_label(p)
		burn_label(p["processor"], text)
		stack.addSlice(text, p["processor"])

	simp = ImagePlus(title, stack)
	outputs = []

	if MODE_MONTAGE:
		n = len(panels)
		cols = (MONTAGE_COLUMNS if MONTAGE_COLUMNS > 0
		        else int(math.ceil(math.sqrt(n))))
		rows = int(math.ceil(n / float(cols)))
		try:
			montage = MontageMaker().makeMontage2(
			    simp, cols, rows, MONTAGE_SCALE, 1, n, 1, MONTAGE_BORDER, False)
		except ANY_ERROR:
			montage = None
		if montage is None:
			IJ.run(simp, "Make Montage...",
			       "columns=%d rows=%d scale=%s border=%d"
			       % (cols, rows, MONTAGE_SCALE, MONTAGE_BORDER))
			montage = IJ.getImage()
		montage.setTitle(title + "  montage")
		outputs.append(("montage", montage))

	if MODE_STACK:
		simp.setTitle(title + "  stack")
		outputs.append(("stack", simp))
	else:
		simp.close()

	return outputs


# ------------------------------------------------------- saving + record
def close_quietly(*imps):
	for obj in imps:
		if obj is not None:
			try:
				obj.changes = False
				obj.close()
			except ANY_ERROR:
				pass


def save_output(imp, path, what):
	"""Save imp as a TIFF unless it exists and 'overwrite' is off. Returns
	the path, or None (reason logged)."""
	if os.path.exists(path) and not overwrite:
		IJ.log("      %s NOT saved - the file already exists (tick 'Overwrite "
		       "existing output files'): %s" % (what, path))
		return None
	if IJ.saveAsTiff(imp, path):
		IJ.log("      %s saved: %s" % (what, path))
		return path
	IJ.log("      ! %s could not be saved: %s" % (what, path))
	return None


def dialog_items():
	return [
	    ("Image to optimise on (from tifs/ or probabilities/)", IN_FILE),
	    ("Parameter to sweep", sweepParam),
	    ("Output", outputMode),
	    ("Channel (probability: 1 = signal; 0 = first/only)", channel),
	    ("Region to show", cropMode),
	    ("crop size (pixels)", cropSize),
	    ("Output location (blank = beside the folder that holds the input file)",
	     outParentDir.getAbsolutePath() if outParentDir is not None
	     else "(blank)"),
	    ("Name for the new output folder", outFolderName),
	    ("Save results to disk", saveResults),
	    ("Overwrite existing output files", overwrite),
	    ("Write a debug log CSV", writeLog),
	]


def record_items(S, values, value_source, images, chosen=None):
	"""Everything that shaped the result (images: [(path, note), ...])."""
	items = [("#Dialog", "")] + layout_record() + dialog_items() + [
	    ("#Sweep", ""), ("Swept parameter", "%s  (%s)" % (sweepParam, PKEY))]
	if MODE_LIVE:
		items.append(("Chosen value (live preview)",
		              "" if chosen is None else fmt_value(chosen)))
	else:
		items += [(label, S.get(k, "")) for k, label in (
		    ("values", "Values typed"), ("gen_from", "Generate from"),
		    ("gen_to", "Generate to"), ("gen_steps", "How many"),
		    ("spacing", "Spacing"))]
		items += [("Values swept", ", ".join([fmt_value(v) for v in values])),
		          ("Values source", value_source)]
	items.append(("#Held fixed", ""))
	if STAGE_RAW:
		items.append(("Subtract Background options", bg_options("<swept>")))
	else:
		if PKEY == "threshold":
			items.append(("Skip particle analysis", S["skip"]))
		items += [(label, S[key]) for key, label, _d in FIXED_FIELDS
		          if key != PKEY]
		items += [("Threshold maximum (8-bit, fixed)", THRESHOLD_MAX),
		          ("Include holes", S["holes"]),
		          ("Exclude particles on edges", S["edges"]),
		          ("Watershed", S["watershed"]), ("Render as", S["render"])]
	items += [("#Configuration", "")] + [(n, globals()[n]) for n in (
	    "BG_LIGHT_BACKGROUND BG_SLIDING_PARABOLOID BG_DISABLE_SMOOTHING "
	    "SIZE_IN_PIXELS").split()] + [
	    ("TIF_EXTENSIONS", ", ".join(TIF_EXTENSIONS)),
	    ("NESTED_INPUT_FOLDERS", ", ".join(NESTED_INPUT_FOLDERS)),
	    ("PROBABILITY_MARKER", PROBABILITY_MARKER or "(blank)")] + [
	    (n, globals()[n]) for n in (
	        "MONTAGE_COLUMNS MONTAGE_SCALE MONTAGE_BORDER LABEL_INCLUDES_COUNT "
	        "CONFIRM_BEFORE_RUN").split()]
	items.append(("#Inputs", ""))
	for i, (path, note) in enumerate(images):
		items.append(("image %d" % (i + 1), path))
		items.append(("image %d region / outcome" % (i + 1), note))
	return items


def maybe_write_record(out_dir, S, values, value_source, images, chosen=None):
	if not (WRITE_PARAMETER_RECORD and out_dir):
		return None
	path = write_run_record(out_dir, SCRIPT_NAME, SCRIPT_VERSION,
	                        record_items(S, values, value_source, images,
	                                     chosen))
	if path:
		IJ.log("Parameter record: %s" % path)
	return path


# =========================================================================
# ===  LIVE PREVIEW  ======================================================
# =========================================================================

class LivePreview(DialogListener, AdjustmentListener):

	def __init__(self, base, S, display_range, title, box=None):
		self.base, self.box, self.S, self.display_range = base, box, S, display_range
		self.value = self.scrollbar = self.last = None
		self.release_only = PKEY in SLIDER_RELEASE_ONLY
		self.imp = ImagePlus(title, self.render(self.initial_value()))
		self.imp.show()

	def initial_value(self):
		if PKEY in SLIDER_RANGES:
			lo, hi = SLIDER_RANGES[PKEY]
			return float(min(max(DEFAULT_FIXED.get(PKEY, lo), lo), hi))
		return float(DEFAULT_FIXED.get(PKEY, DEFAULT_RANGES[PKEY][0]))

	def render(self, v):
		try:
			if STAGE_RAW:
				p = rolling_panel_from(subtracted_region(self.base, self.box, v),
				                       v, self.display_range)
			else:
				p = one_probability_panel(self.base, self.S, v)
		except StepError, e:
			src = self.base if self.box is None else cut(self.base, self.box)
			cp = src.getProcessor().duplicate().convertToRGB()
			if src is not self.base:
				src.close()
			burn_label(cp, "invalid: %s" % str(e).split("\n")[0][:60])
			return cp
		self.last = p
		burn_label(p["processor"], panel_label(p))
		IJ.showStatus(panel_label(p))
		return p["processor"]

	def update(self, v):
		if v is None or v == self.value:
			return
		self.value = v
		self.imp.setProcessor(self.render(v))
		self.imp.updateAndDraw()

	def dialogItemChanged(self, gd, e):
		try:
			v = gd.getNextNumber()
		except ANY_ERROR:
			return True
		if v is None or (v != v):          # NaN while the field is empty
			return True
		if (self.release_only and self.scrollbar is not None
		        and self.scrollbar.getValueIsAdjusting()):
			self.value = v
			IJ.showStatus("%s=%s  (release to update)"
			              % (PARAM_LABEL, fmt_value(v)))
			return True
		self.update(v)
		return True

	def adjustmentValueChanged(self, e):
		if e.getValueIsAdjusting():
			return
		try:
			v = float(self.scrollbar.getValue())
		except ANY_ERROR:
			return
		self.value = None
		self.update(v)


def list_images():
	return [IN_FILE]


# =========================================================================
# ===  CHECK SETTINGS  ====================================================
# =========================================================================


def planned_output_dir():
	"""The output folder resolve_output_dir() will use."""
	name = (outFolderName or "").strip() or "optimization"
	name = re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "optimization"
	if OUT_PARENT is not None:
		parent = OUT_PARENT.getAbsolutePath()
	else:
		parent = os.path.dirname(os.path.normpath(OUT_ANCHOR))
	return os.path.join(parent, name)


def looks_processed(path):
	"""True when a file looks background-subtracted already (2b output)."""
	return ("_bgsub" in os.path.basename(path).lower()
	        or any(["bgsub" in p for p in folder_parts(path)]))


def fixed_text(S):
	if STAGE_RAW:
		return ("Held fixed: Subtract Background %s (as in 2b; no threshold "
		        "or particle settings apply)" % bg_options("<value>"))
	parts = []
	nolim = lambda v: "no limit" if v <= 0 else fmt_num(v)
	if S["skip"]:
		return ("Held fixed: threshold maximum %d, particle analysis "
		        "skipped, panels show the thresholded area; watershed %s"
		        % (THRESHOLD_MAX, "on" if S["watershed"] else "off"))
	parts.append("threshold maximum %d" % THRESHOLD_MAX if PKEY == "threshold"
	             else "threshold %s to %d" % (S["threshold"], THRESHOLD_MAX))
	if PKEY not in ("minsize", "maxsize"):
		parts.append("size %s to %s" % (fmt_num(S["minsize"]), nolim(S["maxsize"])))
	elif PKEY == "minsize":
		parts.append("max size %s" % nolim(S["maxsize"]))
	else:
		parts.append("min size %s" % fmt_num(S["minsize"]))
	if PKEY not in ("mincirc", "maxcirc"):
		parts.append("circularity %.2f to %.2f" % (S["mincirc"], S["maxcirc"]))
	elif PKEY == "mincirc":
		parts.append("max circularity %.2f" % S["maxcirc"])
	else:
		parts.append("min circularity %.2f" % S["mincirc"])
	parts += ["holes %s" % ("included" if S["holes"] else "not included"),
	          "edge particles %s" % ("excluded" if S["edges"] else "kept"),
	          "watershed %s" % ("on" if S["watershed"] else "off"),
	          "shown as %s" % S["render"].lower()]
	return "Held fixed: " + ", ".join(parts)


def fmt_num(v):
	return "%d" % int(round(v)) if abs(v - round(v)) < 1e-9 else "%.2f" % v


def crossed_limits(S, values):
	"""Swept values at which a minimum is above its maximum."""
	if STAGE_RAW or S["skip"] or not values:
		return []
	return [v for v, (lo, hi, clo, chi) in [(v, limits_at(S, v)) for v in values]
	        if clo > chi or (hi > 0 and lo > hi)]


def channel_lines(first):
	lines = []
	desc = describe_channels(first)
	name = os.path.basename(first)
	want = channel if channel > 0 else 1
	which = ("channel %d" % want if channel > 0
	         else "channel 1 (0 = first/only)")
	if len(desc) > 1:
		lines.append("Channel used: %s. %s has %d channels:"
		             % (which, name, len(desc)))
		lines.append("   " + "; ".join(desc))
		if want > len(desc):
			lines.append("!Channel %d was asked for, but %s has only %d "
			             "channels, so this image will fail. Change "
			             "'Channel'." % (want, name, len(desc)))
		elif STAGE_RAW:
			lines.append("!%s has %d channels. 2b processes every channel "
			             "by default (or the one set in its 'Channel to "
			             "process'), but this sweep shows only channel %d. "
			             "Check that channel %d holds the stain you will "
			             "count, and change 'Channel' if not."
			             % (name, len(desc), want, want))
	elif len(desc) == 1:
		lines.append("Channel used: the only channel in %s" % name)
		if want > 1:
			lines.append("!Channel %d was asked for, but %s has one channel, "
			             "so that one channel is used. Check that this file "
			             "holds the signal you want to look at."
			             % (want, name))
	else:
		lines.append("Channel used: %s (the channels of %s could not be read)"
		             % (which, name))
	return lines


def common_lines(S, values, value_source, paths):
	lines = ["Parameter swept: %s" % sweepParam]
	if MODE_LIVE:
		lines.append("Values: chosen in a live preview (one control, one "
		             "image)")
	else:
		lines.append("Values: %s  (%s)"
		             % (", ".join([fmt_value(v) for v in values]), value_source))
	lines.append(fixed_text(S))
	if not STAGE_RAW:
		lines.append("The threshold maximum is fixed at %d. Use %d as "
		             "'Threshold: maximum (8-bit)' in stage 3, or these "
		             "values will not transfer." % (THRESHOLD_MAX, THRESHOLD_MAX))
		not8 = []
		for p in paths:
			bits = file_bit_depth(p)
			if bits is not None and bits != 8:
				not8.append("%s (%d-bit)" % (os.path.basename(p), bits))
		if not8:
			lines.append("Not 8-bit: %s. These are converted to 8-bit on a "
			             "fixed scale, as in stage 3: 16-bit 0-65535 and "
			             "32-bit 0-1 (or 0-255) map onto 0-255, so 128 means "
			             "p = 0.50. A 32-bit image with values outside 0-255 "
			             "fails." % ", ".join(not8))

	stage_warning = stage_warning_for(paths)
	if stage_warning:
		lines.append("!" + stage_warning)
	elif STAGE_RAW:
		done = [os.path.basename(p) for p in paths
		        if looks_processed(p) or looks_like_thresholded(p)]
		if done:
			lines.append("!The rolling ball radius applies to RAW images, but "
			             "%s look(s) already processed ('_bgsub' or '_thresh' "
			             "in the name or folder). Point this at the raw images "
			             "(tifs/)." % ", ".join(done))
	bad = crossed_limits(S, values)
	if bad:
		lines.append("!At %s = %s a minimum is above its maximum (see 'Held "
		             "fixed'), so every image will FAIL. Change the values or "
		             "the fixed limit."
		             % (PARAM_LABEL, ", ".join([fmt_value(v) for v in bad])))
	return lines


def output_lines(paths, n_windows):
	lines = []
	if cropMode.startswith("Whole"):
		lines.append("Region shown: whole image")
	else:
		lines.append("Region shown: %s, crop %d x %d pixels"
		             % (cropMode.lower(), cropSize, cropSize))
		if crop_count_note():
			lines.append("   " + crop_count_note())
		elif STAGE_RAW:
			lines.append("   The rolling ball runs on the whole image, as in "
			             "2b; the crop is cut out afterwards.")
	out_dir = planned_output_dir()
	stem = os.path.splitext(os.path.basename(paths[0]))[0]
	if MODE_LIVE:
		lines.append("Output: Live preview of %s" % os.path.basename(paths[0]))
		names = ["%s_live_%s_<value>.tif" % (stem, PKEY)]
	else:
		kinds = (["montage"] if MODE_MONTAGE else []) + (["stack"] if MODE_STACK else [])
		lines.append("Output: %s; %d result window(s) will open"
		             % (outputMode, max(n_windows, len(kinds))))
		names = []
		for p in paths:
			s = os.path.splitext(os.path.basename(p))[0]
			for k in kinds:
				names.append("%s_sweep_%s_%s.tif" % (s, PKEY, k))
	lines.append("Output folder: %s%s" % (out_dir, "" if os.path.isdir(out_dir)
	                                     else "  (will be created)"))
	if saveResults:
		more = "" if len(names) <= 1 else "  (and %d more)" % (len(names) - 1)
		lines.append("Saved: %s%s, plus the parameter record" % (names[0], more))
		if not overwrite and not MODE_LIVE:
			there = [n for n in names if os.path.exists(os.path.join(out_dir, n))]
			if there:
				lines.append("!%d result file(s) already exist in the output "
				             "folder (e.g. %s) and 'Overwrite existing output "
				             "files' is off: they will NOT be saved again."
				             % (len(there), there[0]))
	else:
		lines.append("'Save results to disk' is off: only the parameter "
		             "record is written")
	lines.append("Overwrite existing files: %s;  debug log CSV: %s"
	             % ("yes" if overwrite else "no", "yes" if writeLog else "no"))
	return lines


def settings_lines(S):
	"""The Check settings lines (warnings start with "!")."""
	values, value_source = (None, None) if MODE_LIVE else build_values(S)
	paths = list_images()
	lines = common_lines(S, values, value_source, paths)
	lines.append("Input image: %s" % IN_FILE)
	lines.extend(channel_lines(paths[0]))
	kinds = (1 if MODE_MONTAGE else 0) + (1 if MODE_STACK else 0)
	lines.extend(output_lines(paths, 1 if MODE_LIVE else kinds))
	return lines


def run_live(S):
	path = list_images()[0]
	fname = os.path.basename(path)
	stem = os.path.splitext(fname)[0]
	IJ.log("Live preview on: %s" % fname)
	stage_warning = stage_warning_for([path])

	base = None
	try:
		base = open_image(path)
		display_range, box = None, None
		if STAGE_RAW:
			box, crop_note = crop_box(base)
			IJ.log("  region: %s" % crop_note)
			shown = base if box is None else cut(base, box)
			st = shown.getStatistics(Measurements.MIN_MAX)
			if shown is not base:
				shown.close()
			display_range = (st.min, st.max)
			IJ.log("  display range pinned at %.1f-%.1f so panels stay comparable"
			       % display_range)
			IJ.log("  the rolling ball runs on the whole image (as in 2b): "
			       "slow on a large image")
		else:
			conv_note = probability_8bit(base)
			base, crop_note = crop(base)
			IJ.log("  region: %s" % crop_note)
			if conv_note:
				IJ.log("  probability map %s" % conv_note)
				crop_note += "; " + conv_note
			if crop_count_note():
				IJ.log("  " + crop_count_note())

		title = "%s  [live %s]" % (stem, PARAM_LABEL)
		live = LivePreview(base, S, display_range, title, box)

		gd = NonBlockingGenericDialog("Live - %s" % sweepParam)
		if PKEY in SLIDER_RANGES:
			lo, hi = SLIDER_RANGES[PKEY]
			gd.addSlider(sweepParam, lo, hi, live.initial_value())
			try:
				live.scrollbar = gd.getSliders().elementAt(0)
				if live.release_only:
					live.scrollbar.addAdjustmentListener(live)
			except ANY_ERROR:
				live.scrollbar = None
		else:
			dec = 0 if PKEY in INTEGER_PARAMS else 2
			gd.addNumericField(sweepParam, live.initial_value(), dec)

		if live.release_only:
			gd.addMessage("Updates when you release the slider, or type a value\n"
			              "and press Tab (the rolling ball is too slow to follow\n"
			              "the drag).")
		else:
			gd.addMessage("Updates as you change the value.")
		gd.addMessage("OK keeps the preview open. Cancel closes it.")

		gd.addDialogListener(live)
		live.update(live.initial_value())
		gd.showDialog()

		if gd.wasCanceled():
			close_quietly(live.imp)
			IJ.log("Live preview cancelled.")
			return None

		chosen = live.value
		IJ.log("-" * 64)
		IJ.log("Chose %s = %s" % (PARAM_LABEL, fmt_value(chosen)))
		last = live.last or {}
		if last.get("count") is not None:
			IJ.log("  particles at that value: %d" % last["count"])
		elif last.get("area") is not None:
			IJ.log("  area above threshold: %.1f%%" % last["area"])

		# Created even when nothing is saved (parameter record).
		saved, not_saved, record = None, [], None
		out_dir = resolve_output_dir(OUT_ANCHOR, outFolderName, "optimization",
		                             OUT_PARENT)
		if out_dir:
			if saveResults:
				target = os.path.join(
				    out_dir, "%s_live_%s_%s.tif"
				    % (stem, PKEY, fmt_value(chosen).replace(".", "p")))
				saved = save_output(live.imp, target, "preview")
				if saved is None:
					not_saved.append(target)
			record = maybe_write_record(out_dir, S, None, None,
			                            [(path, crop_note)], chosen)
		elif saveResults:
			not_saved.append("(no output folder)")

		return {"value": chosen, "image": fname, "crop": crop_note,
		        "saved": saved, "not_saved": not_saved, "last": live.last,
		        "warning": stage_warning, "out_dir": out_dir,
		        "record": record}
	finally:
		close_quietly(base)


# =========================================================================
# ===  BATCH (montage / stack)  ===========================================
# =========================================================================
def run_batch(S):
	values, value_source = build_values(S)

	paths = list_images()
	chosen = [os.path.basename(p) for p in paths]
	stage_warning = stage_warning_for(paths)

	# Created even with saving off (parameter record).
	out_dir = resolve_output_dir(OUT_ANCHOR, outFolderName, "optimization",
	                             OUT_PARENT)
	if not out_dir:
		raise SystemExit      # resolve_output_dir already showed the error

	IJ.log("=" * 64)
	IJ.log("Parameter optimisation sweep")
	IJ.log("  parameter : %s" % sweepParam)
	IJ.log("  stage     : %s images" % ("RAW" if STAGE_RAW else "PROBABILITY"))
	IJ.log("  output    : %s" % outputMode)
	IJ.log("  values    : %s   (%s)"
	       % (", ".join([fmt_value(v) for v in values]), value_source))
	IJ.log("  images    : %s" % ", ".join(chosen))
	IJ.log("  region    : %s" % cropMode)
	if STAGE_RAW:
		IJ.log("  held fixed: nothing - the rolling ball runs before ilastik")
	elif S["skip"]:
		IJ.log("  particle analysis SKIPPED; panels show the thresholded area")
		IJ.log("  held fixed: threshold maximum=%d watershed=%s"
		       % (THRESHOLD_MAX, S["watershed"]))
	else:
		IJ.log("  held fixed: thr=%s-%d size=%s-%s circ=%.2f-%.2f holes=%s "
		       "edges=%s watershed=%s" % (
		           S["threshold"], THRESHOLD_MAX, S["minsize"],
		           "inf" if S["maxsize"] <= 0 else S["maxsize"], S["mincirc"],
		           S["maxcirc"], S["holes"], S["edges"], S["watershed"]))
	if crop_count_note() and not S["skip"]:
		IJ.log("  ! " + crop_count_note())
	if STAGE_RAW:
		IJ.log("  the rolling ball runs on the whole image, as in 2b; the "
		       "region shown is cut out afterwards")
	if saveResults:
		IJ.log("  saving to : %s" % out_dir)
	else:
		IJ.log("  saving    : off (parameter record only, in %s)" % out_dir)
	IJ.log("=" * 64)

	summary = ResultsTable()
	made, failed, log_rows, not_saved = [], [], [], []
	notes = {}                       # image index -> region / outcome

	for i, fname in enumerate(chosen):
		stem = os.path.splitext(fname)[0]
		path = paths[i]
		IJ.showStatus("[%d/%d] %s - opening" % (i + 1, len(chosen), fname))
		IJ.showProgress(i, len(chosen))

		imp = None
		try:
			imp = open_image(path)

			if STAGE_RAW:
				box, crop_note = crop_box(imp)
				notes[i] = crop_note

				def status(j, v):
					IJ.showStatus("[%d/%d] %s - radius %s (%d/%d)"
					              % (i + 1, len(chosen), fname,
					                 fmt_value(v), j + 1, len(values)))
				panels, dr = rolling_panels(imp, box, values, status)
				IJ.log("[%d/%d] %s   %s   display range %.1f-%.1f"
				       % (i + 1, len(chosen), fname, crop_note, dr[0], dr[1]))
			else:
				conv_note = probability_8bit(imp)
				imp, crop_note = crop(imp)
				if conv_note:
					crop_note += "; " + conv_note
				notes[i] = crop_note
				panels = []
				for j, v in enumerate(values):
					IJ.showStatus("[%d/%d] %s - %s=%s (%d/%d)"
					              % (i + 1, len(chosen), fname, PARAM_LABEL,
					                 fmt_value(v), j + 1, len(values)))
					panels.append(one_probability_panel(imp, S, v))
				IJ.log("[%d/%d] %s   %s" % (i + 1, len(chosen), fname, crop_note))
				if S["skip"]:
					IJ.log("      area above threshold: %s"
					       % "  ".join(["%s:%.1f%%" % (fmt_value(p["value"]),
					                                   p["area"])
					                    for p in panels]))
				else:
					IJ.log("      counts: %s"
					       % "  ".join(["%s:%d" % (fmt_value(p["value"]),
					                               p["count"])
					                    for p in panels]))

			title = "%s  [%s sweep]" % (stem, PARAM_LABEL)
			for kind, out_imp in build_outputs(panels, title):
				out_imp.show()
				made.append("%s (%s)" % (stem, kind))
				if saveResults:
					mpath = os.path.join(
					    out_dir, "%s_sweep_%s_%s.tif" % (stem, PKEY, kind))
					if save_output(out_imp, mpath, kind) is None:
						not_saved.append(mpath)

			for p in panels:
				summary.incrementCounter()
				summary.addValue("image", stem)
				summary.addValue(PARAM_LABEL, p["value"])
				if p["count"] is not None:
					summary.addValue("particles", p["count"])
				if p.get("area") is not None:
					summary.addValue("area_above_threshold_pct", p["area"])
				log_rows.append([stem, fmt_value(p["value"]),
				                 "" if p["count"] is None else str(p["count"]),
				                 "" if p.get("area") is None
				                 else "%.3f" % p["area"], crop_note])

		except ANY_ERROR, e:
			failed.append(fname)
			if isinstance(e, StepError):
				what, msg = "FAILED", str(e)
				notes[i] = "FAILED: " + msg.replace("\n", " ")
			else:
				what = "UNEXPECTED ERROR"
				msg = "%s: %s" % (type(e).__name__, str(e))
				notes[i] = "UNEXPECTED ERROR: " + msg
			IJ.log("[%d/%d] %s  %s: %s" % (i + 1, len(chosen), fname, what, msg))
			log_rows.append([stem, "", "", "", notes[i]])
		finally:
			close_quietly(imp)

	IJ.showProgress(1.0)
	IJ.showStatus("")

	if summary.size() > 0:
		summary.show("Sweep: %s" % PARAM_LABEL)

	log_path = None
	if writeLog and out_dir:
		target = os.path.join(out_dir, "_sweep_%s_log_%s.csv"
		                      % (PKEY, os.path.splitext(os.path.basename(IN_FILE))[0]))
		if os.path.exists(target) and not overwrite:
			not_saved.append(target)
			IJ.log("Debug log NOT saved - the file already exists (tick "
			       "'Overwrite existing output files' to replace it): %s"
			       % target)
		else:
			try:
				fh = open(target, "w")
				try:
					fh.write("image,%s,particles,area_above_threshold_pct,note\n"
					         % PARAM_LABEL.replace(" ", "_") + "".join(
					             [",".join(['"%s"' % str(c).replace('"', "'")
					                        for c in r]) + "\n" for r in log_rows]))
				finally:
					fh.close()
				log_path = target
				IJ.log("Log written: %s" % log_path)
			except IOError, e:
				not_saved.append(target)
				IJ.log("WARNING: could not write the log CSV: %s" % str(e))

	record = maybe_write_record(out_dir, S, values, value_source,
	                            [(p, notes.get(k, "")) for k, p in enumerate(paths)])

	return {"values": values, "made": made, "failed": failed,
	        "warning": stage_warning, "out_dir": out_dir, "log": log_path,
	        "skip": S["skip"], "not_saved": not_saved, "record": record}


# =========================================================================
# ===  RUN  ===============================================================
# =========================================================================
def finish_live(result):
	if result is None:
		return
	problems = bool(result["warning"] or result["not_saved"])
	body = ["Live preview finished.", "",
	        "%s = %s" % (PARAM_LABEL, fmt_value(result["value"]))]
	last = result["last"] or {}
	if last.get("count") is not None:
		body.append("particles at that value: %d" % last["count"])
	elif last.get("area") is not None:
		body.append("area above threshold: %.1f%%" % last["area"])
	body += ["", "Image: %s" % result["image"], "Region: %s" % result["crop"]]
	if result["saved"]:
		body += ["", "Preview saved:", "   " + result["saved"]]
	if result["not_saved"]:
		body += ["", "The preview was NOT saved (see the Log)."]
	if result["record"]:
		body += ["", "Parameter record: " + result["record"]]
	if result["warning"]:
		body += ["", "WARNING: " + result["warning"]]
	body += ["", "This was one image and one region. Run a montage across "
	         "a few sections before committing, and keep it as the record."]
	if problems:
		body += ["", "Check the Log window for details."]
	IJ.showMessage("Live preview" if not problems
	               else "Live preview - with problems", "\n".join(body))


def finish_batch(result):
	made, failed = result["made"], result["failed"]
	IJ.log("-" * 64)
	IJ.log("Outputs built: %d   failed: %d   not saved: %d"
	       % (len(made), len(failed), len(result["not_saved"])))
	IJ.log("-" * 64)

	body = ["Swept %s across %d value(s)." % (PARAM_LABEL, len(result["values"])),
	        "", "Outputs built: %d" % len(made)]
	if failed:
		body.append("Failed: %d  (see Log)" % len(failed))
	if result["not_saved"]:
		body.append("Not saved: %d  (already exist or could not be written; "
		            "see Log)" % len(result["not_saved"]))
	body.append("")
	if STAGE_RAW:
		body.append("Each panel is labelled with its value.")
	elif result["skip"]:
		body.append("Each panel is labelled with its value and the percentage "
		            "of pixels above threshold.")
	else:
		body += ["Each panel is labelled with its value and particle count "
		         "(also in the counts table).", "", "Look for the plateau: "
		         "where the count stops changing much, the parameter is "
		         "usually doing what you want."]
	if result["warning"]:
		body += ["", "WARNING: " + result["warning"]]
	if result["out_dir"] and saveResults:
		body += ["", "Saved to: " + result["out_dir"]]
	elif result["out_dir"]:
		body += ["", "'Save results to disk' was off: only the parameter "
		         "record was written, in " + result["out_dir"]]
	if result["record"]:
		body += ["", "Parameter record: " + result["record"]]
	if result["log"]:
		body += ["", "Log: " + result["log"]]
	body += ["", "The values held fixed are in the Log: note them with the "
	         "value you choose, they are part of the answer."]
	problems = bool(failed or result["warning"] or result["not_saved"])
	if problems:
		body += ["", "Check the Log window for details."]
	IJ.showMessage("Sweep complete" + (" - with failures" if failed else
	                                   " - with problems" if problems else ""),
	               "\n".join(body))


# Masks here are white-on-black; Prefs.blackBackground is restored below.
_prev_black_background = Prefs.blackBackground
Prefs.blackBackground = True
try:
	S = show_settings_dialog()
	if S is None:
		IJ.log("Cancelled.")
		raise SystemExit

	result = None
	try:
		if not confirm_settings(SCRIPT_NAME, experiment_lines(globals().get("_SLIDE") or IN_DIR) + settings_lines(S),
		                        CONFIRM_BEFORE_RUN):
			IJ.log("%s: cancelled at the settings check; nothing was "
			       "processed." % SCRIPT_NAME)
			raise SystemExit
		if MODE_LIVE:
			result = run_live(S)
		else:
			result = run_batch(S)
	except StepError, e:
		IJ.error("Sweep", str(e))
		raise SystemExit
	except SystemExit:
		raise
	except ANY_ERROR, e:
		IJ.error("Sweep", "Unexpected error: %s: %s" % (type(e).__name__, str(e)))
		raise SystemExit

	IJ.beep()
	if MODE_LIVE:
		finish_live(result)
	else:
		finish_batch(result)
finally:
	Prefs.blackBackground = _prev_black_background
