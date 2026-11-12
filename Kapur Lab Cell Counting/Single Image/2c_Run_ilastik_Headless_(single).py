# 2c_Run_ilastik_Headless_(single).py
#
# Fiji / ImageJ Jython script - Kapur Lab Cell Counting suite, step 2c.
#
# Runs ilastik headless (no ilastik window) from Fiji: applies a pixel
# classifier you trained in ilastik to the background-subtracted images of
# a slide, and writes the probability maps the way stage 3 expects them.
#
# Menu  : Plugins > Kapur Lab Cell Counting > Single image > 2c Run ilastik Headless (single)
# Reads : the ilastik project (.ilp) you trained and saved (looked for in the
#         region's MBF folder, then the slide folder); one .tif image from
#         processed_bgsub_cleared/.
# Writes: probabilities/<image name>.tif (ilastik's {nickname}.tif), one per
#         image, as 8-bit integers with probability 0-1 renormalized to
#         0-255 (128 = p 0.50), whatever export settings the project was
#         saved with; ilastik's own messages in probabilities/
#         _ilastik_log_<time>.txt; and a parameter record
#         _run_2c_Run_ilastik_Headless_single_<time>.txt in probabilities/.
#
# Before running it:
#   1. Train the classifier in ilastik (Pixel Classification) on a few of
#      the slide's processed_bgsub_cleared images. Label 1 must be the
#      cells: stage 3 counts channel 1 of the probability map
#      (SIGNAL_CHANNEL).
#   2. Make sure the classifier is trained (Live Update on, or after a
#      prediction), then save the project (Project > Save) into the
#      region's MBF folder (or the slide folder), and quit ilastik.
#   The images used for training are processed here too, as the protocol
#   asks. If a project has labels but no trained classifier saved, ilastik
#   retrains it from the labels, which needs the training images where the
#   project expects them.
#
# The export settings are given to ilastik on the command line
# (--export_source=Probabilities --output_format=tif --export_dtype=uint8
# --pipeline_result_drange=(0.0,1.0) --export_drange=(0,255)), so they do
# not depend on what was set in the ilastik window. The project is opened
# read-only and is never changed.
#
# Before it runs, the Check settings window lists the project, the
# ilastik program, the images and the output folder. Press Run to go ahead
# or Cancel to stop. ilastik can take a minute or more per image; the Log
# shows its progress. Press Esc to stop ilastik at once: finished maps are
# kept, and a later run (Overwrite off) does the rest. With "Show the
# result" ticked, the map opens in Fiji (channel 1 = label 1, the cells).
#
# Usage: Plugins > Kapur Lab Cell Counting > Single image > 2c Run ilastik
# Headless (single), or open this file in the Script Editor (File > New
# > Script..., or Plugins > Scripting > Script Editor) with Language = Python
# (Jython) and press Run.

#@ File    (label="Slide folder (the scripts find its subfolders)", style="directory") slideDir
#@ String  (label="Region (its MBF folder; blank = choose from a list)", value="", required=false) regionName
#@ String  (label="Section (e.g. Region0011; blank = choose from a list)", value="", required=false) sectionKey
#@ Boolean (label="Overwrite existing probability maps", value=false) overwrite
#@ File    (label="ilastik program (blank = find it)", style="file", required=false) ilastikExe
#@ Boolean (label="Show the result (the probability map) when done", value=true) showResult

# =========================================================================
# ===  USER CONFIGURATION  ================================================
# =========================================================================
# Nothing below the END OF USER CONFIGURATION banner needs editing for
# routine use.

# ---- ILASTIK EXPORT (given to ilastik for every run) ----
EXPORT_SOURCE = "Probabilities"
EXPORT_DTYPE = "uint8"                 # integer 8-bit
PIPELINE_RESULT_DRANGE = "(0.0,1.0)"   # probabilities before renormalizing
EXPORT_DRANGE = "(0,255)"              # ... and after: 0-255
OUTPUT_FORMAT = "tif"                  # "tif" writes .tif ("tiff" would write .tiff)
OUTPUT_NAME = "{nickname}.tif"         # {nickname} = input name without .tif

# ---- ILASTIK PROGRAM ----
# Where to look when "ilastik program" is blank. The newest version found is
# used. On Windows this is ilastik.exe in the install folder; on a Mac the
# program is inside the .app (Contents/MacOS/ilastik).
ILASTIK_SEARCH = ["C:/Program Files/ilastik-*/ilastik.exe",
                  "D:/Program Files/ilastik-*/ilastik.exe",
                  "/Applications/ilastik-*.app",
                  "~/Applications/ilastik-*.app",
                  "~/ilastik-*/run_ilastik.sh",
                  "/opt/ilastik-*/run_ilastik.sh"]
FILES_PER_RUN = 10        # images per ilastik call (each call reloads it)
THREADS = 0               # LAZYFLOW_THREADS; 0 = ilastik decides
RAM_MB = 0                # LAZYFLOW_TOTAL_RAM_MB; 0 = ilastik decides, else >= 500

# ---- INPUT / OUTPUT FOLDERS (found in the slide / region folder) ----
INPUT_FOLDER = "processed_bgsub_cleared"
OUTPUT_FOLDER = "probabilities"
IMAGE_EXTENSIONS = [".tif", ".tiff"]

# ---- PAIRING ----
KEY_PATTERN = r"^(Region\d+)"
CASE_INSENSITIVE_KEYS = True
REQUIRE_IN_NAME = ""
EXCLUDE_IN_NAME = ""

# ---- SAFETY CHECKS ----
CONFIRM_BEFORE_RUN = True
WRITE_PARAMETER_RECORD = True

# =========================================================================
# ===  END OF USER CONFIGURATION  =========================================
# =========================================================================

SCRIPT_NAME = "2c_Run_ilastik_Headless_single"
SCRIPT_VERSION = "2.0"

import os
import re
import glob
import time
from ij import IJ
from java.lang import Exception as JavaException

# ---- SHARED: errors -- keep identical ----
class StepError(Exception):
	"""A per-file failure with a message already written for a human."""
	pass
# ---- END SHARED: errors ----


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


# ---------------------------------------------------------------- helpers
def version_key(path):
	m = re.search(r"ilastik-(\d+)\.(\d+)\.?(\d*)", path)
	return tuple([int(x or 0) for x in m.groups()]) if m else (0, 0, 0)


def program_in(path):
	"""The ilastik executable for a path the user gave or found: an .app,
	an install folder, or the program itself. None if there is none."""
	p = os.path.expanduser(path)
	if p.lower().endswith(".app") or os.path.isdir(p):
		for sub in ("Contents/MacOS/ilastik", "Contents/ilastik-release/run_ilastik.sh",
		            "run_ilastik.sh", "ilastik.exe"):
			q = os.path.join(p, sub)
			if os.path.isfile(q):
				return q
		return None
	return p if os.path.isfile(p) else None


def find_ilastik():
	found = []
	for pat in ILASTIK_SEARCH:
		for p in glob.glob(os.path.expanduser(pat)):
			q = program_in(p)
			if q:
				found.append(q)
	found.sort(key=version_key)
	return found[-1] if found else None


def find_projects(slide, region):
	"""The .ilp files of the region folder, the slide folder and the animal
	folder above it (one project trained for all of an animal's slides)."""
	out = []
	for d in ([region] if region != slide else []) + [slide, os.path.dirname(slide)]:
		try:
			out += [os.path.join(d, f) for f in sorted(os.listdir(d))
			        if f.lower().endswith(".ilp") and not f.startswith(".")]
		except OSError:
			pass
	return out


def output_for(img, out_dir):
	stem = os.path.splitext(os.path.basename(img))[0]
	return os.path.join(out_dir, OUTPUT_NAME.replace("{nickname}", stem))


def literal_path(path):
	"""ilastik reads * ? [ in an input path as a file pattern; this makes
	them match only themselves (a name like 'slide [2]' otherwise fails)."""
	return re.sub(r"([*?[])", r"[\1]", path)


def command(exe, project, out_dir, images):
	return [exe, "--headless", "--readonly", "--project=" + project,
	        "--export_source=" + EXPORT_SOURCE,
	        "--output_format=" + OUTPUT_FORMAT,
	        "--output_filename_format=" + os.path.join(out_dir, OUTPUT_NAME),
	        "--export_dtype=" + EXPORT_DTYPE,
	        "--pipeline_result_drange=" + PIPELINE_RESULT_DRANGE,
	        "--export_drange=" + EXPORT_DRANGE] + [literal_path(i) for i in images]


def stop_process(proc):
	"""Stop ilastik. run_ilastik.sh (Linux) and ilastik.exe (Windows) start
	ilastik's Python as a second process, which must be stopped too."""
	from java.lang import ProcessBuilder
	kids = []
	try:
		kids = list(proc.descendants().toArray())      # Java 9 and later
	except (Exception, JavaException):
		from java.lang import System
		try:
			if System.getProperty("os.name", "").lower().startswith("win"):
				# Java 8, Windows: ilastik.exe starts python.exe; end the tree.
				from com.sun.jna import Pointer
				from com.sun.jna.platform.win32 import Kernel32, WinNT
				f = proc.getClass().getDeclaredField("handle")
				f.setAccessible(True)
				pid = Kernel32.INSTANCE.GetProcessId(WinNT.HANDLE(Pointer(f.getLong(proc))))
				ProcessBuilder(["taskkill", "/T", "/F", "/PID", str(pid)]).start().waitFor()
			else:                                      # Java 8, Mac / Linux
				f = proc.getClass().getDeclaredField("pid")
				f.setAccessible(True)
				ProcessBuilder(["pkill", "-TERM", "-P", str(f.getInt(proc))]).start().waitFor()
		except (Exception, JavaException):
			pass
	for k in kids:
		try:
			k.destroy()
		except (Exception, JavaException):
			pass
	proc.destroy()


def run_ilastik(cmd, log_fh):
	"""Run one ilastik call; its output goes to the log file, and progress
	and error lines to the Log. Esc stops it at once. Returns (exit code,
	or -1 when stopped with Esc; info): info["exported"] = the paths ilastik
	says it wrote, info["error"] = its last error line, info["retrained"] =
	True when the project had no trained classifier."""
	from java.lang import ProcessBuilder, Runnable, Thread as JThread
	from java.io import BufferedReader, InputStreamReader
	from java.util.concurrent import ConcurrentLinkedQueue
	pb = ProcessBuilder(cmd)
	pb.redirectErrorStream(True)
	env = pb.environment()
	if THREADS:
		env.put("LAZYFLOW_THREADS", str(THREADS))
	if RAM_MB:
		env.put("LAZYFLOW_TOTAL_RAM_MB", str(RAM_MB))
	proc = pb.start()
	lines = ConcurrentLinkedQueue()

	class Reader(Runnable):
		def run(self):
			rd = BufferedReader(InputStreamReader(proc.getInputStream(), "UTF-8"))
			try:
				while True:
					ln = rd.readLine()
					if ln is None:
						break
					lines.add(ln)
			except (Exception, JavaException):
				pass

	reader = JThread(Reader(), "ilastik output")
	reader.setDaemon(True)
	reader.start()
	info = {"exported": [], "error": "", "retrained": False}

	def take_lines():
		line = lines.poll()
		while line is not None:
			log_fh.write(line.encode("utf-8") + "\n")
			low = line.lower()
			m = re.search(r"Exporting to (.+)$", line)
			if m:
				info["exported"].append(m.group(1).strip())
			if "has no classifier" in low:
				info["retrained"] = True
			m = re.match(r"^\s*([A-Za-z_][\w.]*(Error|Exception)): (.*)$", line)
			if m:
				info["error"] = "%s: %s" % (m.group(1).split(".")[-1], m.group(3).strip()[:200])
			if ("error" in low or "exception" in low or "export" in low or "%" in line
			        or "no classifier" in low):
				IJ.log("      ilastik: " + line[:160])
			line = lines.poll()

	while True:
		finished = not reader.isAlive()
		take_lines()
		if finished:
			return proc.waitFor(), info
		if IJ.escapePressed():
			stop_process(proc)
			reader.join(15000)
			take_lines()
			return -1, info
		JThread.sleep(200)


def file_state(path):
	try:
		st = os.stat(path)
		return (st.st_mtime, st.st_size)
	except OSError:
		return None


def check_output(path, before="new"):
	"""'' when path is a readable 8-bit probability map, else what is wrong.
	before: file_state(path) taken before ilastik ran ("new" = no check); a
	file still in that state is a map left from an earlier run that ilastik
	did not replace."""
	from loci.formats import ImageReader, FormatTools
	if not os.path.isfile(path):
		return "no output file was written"
	if before != "new" and before is not None and file_state(path) == before:
		return "ilastik did not write a new map (the file is from an earlier run)"
	bad = tiff_truncation_error(path)
	if bad:
		return bad
	r = ImageReader()
	try:
		try:
			r.setId(path)
			if r.getPixelType() != FormatTools.UINT8:
				return "output is %s, not 8-bit" % FormatTools.getPixelTypeString(r.getPixelType())
			return ""
		finally:
			r.close()
	except (Exception, JavaException), e:
		return "output could not be read (%s)" % e


def run_group(exe, project, out_dir, group, fh):
	"""One ilastik call for the images in group. Returns (exit code, info,
	[what is wrong with each image's map, '' when it is fine])."""
	before = [file_state(output_for(i, out_dir)) for i in group]
	cmd = command(exe, project, out_dir, group)
	fh.write("\n$ " + " ".join(['"%s"' % c if " " in c else c for c in cmd]).encode("utf-8") + "\n")
	try:
		code, info = run_ilastik(cmd, fh)
	except (Exception, JavaException), e:
		code, info = None, {"exported": [], "error": "could not start ilastik: %s" % e,
		                    "retrained": False}
		fh.write("could not start ilastik: %s\n" % e)
		IJ.log("  ! could not start ilastik: %s" % e)
	whys = []
	for img, b in zip(group, before):
		out = output_for(img, out_dir)
		why = check_output(out, b)
		if not os.path.isfile(out):
			stem = os.path.splitext(os.path.basename(out))[0]
			other = [p for p in info["exported"]
			         if os.path.splitext(os.path.basename(p.replace("\\", "/")))[0] == stem]
			if other:
				why = "ilastik wrote %s instead" % other[-1]
		if why and code == -1:
			why = "stopped with Esc before its map was finished"
		elif why and code != 0:
			why = "%s (ilastik exit code %s%s)" % (why, code,
			                                       info["error"] and ": " + info["error"] or "")
		whys.append(why)
	return code, info, whys


def stored_classifier(project):
	"""True when the .ilp holds a trained pixel classifier, as saved after
	Live Update (PixelClassification/ClassifierForests/Forest0000)."""
	try:
		fh = open(project, "rb")
	except IOError:
		return False
	try:
		tail = ""
		while True:
			b = fh.read(1 << 20)
			if not b:
				return False
			if "Forest0000" in tail + b:
				return True
			tail = b[-16:]
	finally:
		fh.close()


def image_shape(path):
	"""(channels, bits per pixel) from an image's header, or None."""
	try:
		from loci.formats import ImageReader, FormatTools
		r = ImageReader()
		try:
			r.setId(path)
			return r.getSizeC(), FormatTools.getBytesPerPixel(r.getPixelType()) * 8
		finally:
			r.close()
	except (Exception, JavaException):
		return None


def looks_like_map(path):
	"""(channels, total) when the image looks like an ilastik probability
	map (2+ channels adding up to the same total, 1 or 255, everywhere),
	else None. A background-subtracted image never does."""
	try:
		imp, _n = bf_open(path, 0)
	except (StepError, Exception, JavaException):
		return None
	try:
		nc, w, h = imp.getNChannels(), imp.getWidth(), imp.getHeight()
		if nc < 2 or imp.getNSlices() * imp.getNFrames() != 1:
			return None
		ips = [imp.getStack().getProcessor(c) for c in range(1, nc + 1)]
		sums = [sum([ip.getf(k % w, k // w) for ip in ips])
		        for k in range(0, w * h, max(1, w * h // 4000))]
		for top in (1.0, 255.0):
			if min(sums) >= top * 0.985 and max(sums) <= top * 1.001:
				return nc, int(top)
		return None
	finally:
		imp.close()


# ------------------------------------------------------------------ main
def main():
	from java.io import File as _F
	slide = slideDir.getAbsolutePath()
	region = layout_pick_region(slide, regionName)
	if region is None:
		return
	project_choices = find_projects(slide, region)
	in_dir = layout_find(slide, region, INPUT_FOLDER)
	sec = layout_pick_section(layout_keys(in_dir, tuple(IMAGE_EXTENSIONS)), sectionKey)
	if sec is None:
		return
	cands = layout_files_for(in_dir, key_from(sec), tuple(IMAGE_EXTENSIONS))
	got = layout_confirm(SCRIPT_NAME + " - " + sec, slide, region, [
	    ("Background-subtracted image (from processed_bgsub_cleared/)", "choice",
	     cands[0] if cands else "", cands, True),
	    ("Output folder for probability maps (probabilities/)", "dir",
	     layout_find(slide, region, OUTPUT_FOLDER), None, False),
	    ("ilastik project (.ilp)", "choice", project_choices[0] if project_choices else "",
	     project_choices, True)])
	if got is None:
		return
	img, out_dir, project = got
	out_dir = out_dir or os.path.join(region, OUTPUT_FOLDER)
	in_dir = os.path.dirname(img)
	if os.path.normcase(os.path.abspath(out_dir)) == os.path.normcase(os.path.abspath(in_dir)):
		IJ.error(SCRIPT_NAME, "The output folder is the input folder:\n%s\n\nEach map is named "
		         "like its input image, so the background-subtracted images would be "
		         "replaced by probability maps. Choose another output folder (usually "
		         "probabilities/)." % in_dir)
		return
	images = [img]
	record_items = [("#Dialog", ""), ("Slide folder (the scripts find its subfolders)", slide),
	                ("Region (its MBF folder; blank = choose from a list)", region),
	                ("Section (e.g. Region0011; blank = choose from a list)", sec),
	                ("Overwrite existing probability maps", overwrite),
	                ("ilastik program (blank = find it)",
	                 ilastikExe.getAbsolutePath() if ilastikExe is not None else "(blank)"),
	                ("Show the result (the probability map) when done", showResult),
	                ("image", img), ("output folder", out_dir)]
	exe = program_in(ilastikExe.getAbsolutePath()) if ilastikExe is not None else find_ilastik()
	if not exe:
		IJ.error(SCRIPT_NAME, "ilastik was not found.\n\nFill in 'ilastik program' "
		         "with ilastik.exe in the ilastik folder (on Windows usually "
		         "C:\\Program Files\\ilastik-<version>\\ilastik.exe), or add its location to "
		         "ILASTIK_SEARCH in the script.")
		return
	if 0 < RAM_MB < 500:
		IJ.error(SCRIPT_NAME, "RAM_MB is %d. ilastik refuses less than 500 MB "
		         "(the value is in MB, not GB). Set RAM_MB to 0 or to 500 or more "
		         "in the script." % RAM_MB)
		return
	exe, project, out_dir = [os.path.abspath(x) for x in (exe, project, out_dir)]
	if not stored_classifier(project):
		IJ.error(SCRIPT_NAME, "%s\nholds no trained classifier.\n\nOpen it in ilastik, go to "
		         "Training, turn on Live Update and wait until the predictions appear, "
		         "then save it (Project > Save) and close ilastik.\n\nWithout a saved "
		         "classifier, ilastik would train a new random forest from the labels on "
		         "every call, so maps made in different calls would come from different "
		         "classifiers." % project)
		return
	images = [os.path.abspath(x) for x in images]
	have = [i for i in images if os.path.exists(output_for(i, out_dir))]
	bad = [i for i in have if check_output(output_for(i, out_dir))]
	todo = [i for i in images if overwrite or i not in have or i in bad]
	skipped = len(images) - len(todo)
	lines = ["ilastik project: %s%s" % (project, os.path.normpath(os.path.dirname(project))
	         == os.path.normpath(os.path.dirname(slide)) and " (the animal's project, "
	         "shared by all its slides)" or ""),
	         "ilastik program: %s" % exe,
	         "Images: %d in %s%s" % (len(images), in_dir,
	                                ("; %d already have a probability map and are skipped"
	                                 % skipped) if skipped else ""),
	         "Output: %s (%s, %s, probability 0-1 renormalized to 0-255)"
	         % (out_dir, OUTPUT_NAME, EXPORT_DTYPE),
	         "Classifier: the trained one saved in the project (as after Live Update); "
	         "it is not retrained",
	         "Stage 3 counts channel 1 of each map: label 1 in ilastik must be the cells."]
	mapish = todo and looks_like_map(todo[0])
	shapes = {}
	for i in images:
		shapes.setdefault(image_shape(i), []).append(os.path.basename(i))
	shapes.pop(None, None)
	if len(shapes) > 1:
		lines.append("! The images differ in channels or bit depth (%s). ilastik needs "
		             "every image to have the channels the project was trained on; the "
		             "others fail or give wrong maps. Make them alike in 2b ('Channel to "
		             "process')." % "; ".join(["%d with %d channel(s), %d-bit (e.g. %s)"
		             % (len(v), c, b, v[0]) for (c, b), v in sorted(shapes.items())]))
	elif shapes:
		lines.append("Images: %d channel(s), %d-bit; the project must be trained on "
		             "images with the same channels" % list(shapes)[0])
	if mapish:
		lines.append("! %s looks like a probability map, not a background-subtracted "
		             "image: its %d channels add up to %d everywhere, so ilastik would "
		             "run on probabilities instead of the images. Check the input "
		             "folder (2b writes processed_bgsub_cleared/)." % (os.path.basename(todo[0]), mapish[0],
		                                             mapish[1]))
	if bad and not overwrite:
		lines.append("%d existing map(s) cannot be read or are not 8-bit (e.g. %s) and "
		             "are made again." % (len(bad), os.path.basename(output_for(bad[0], out_dir))))
	odd = [i for i in todo if os.pathsep in i]
	if odd:
		lines.append("! %d image path(s) contain '%s' (e.g. %s); ilastik may read it as a "
		             "list of files and fail. Rename the folder or file."
		             % (len(odd), os.pathsep, odd[0]))
	if len(project_choices) > 1:
		lines.append("! %d .ilp projects were found; check that this is the one "
		             "trained for this region." % len(project_choices))
	if not todo:
		lines.append("! Nothing to do: every image already has a probability map. "
		             "Tick 'Overwrite existing probability maps' to make them again.")
	if not confirm_settings(SCRIPT_NAME, experiment_lines(slide) + lines, CONFIRM_BEFORE_RUN):
		IJ.log("%s: cancelled at the settings check; nothing was processed." % SCRIPT_NAME)
		return
	if not os.path.isdir(out_dir):
		os.makedirs(out_dir)
	IJ.log("=" * 64)
	IJ.log("%s v%s" % (SCRIPT_NAME, SCRIPT_VERSION))
	for ln in lines:
		IJ.log("  " + ln)
	stamp = time.strftime("%Y%m%d-%H%M%S")
	log_path = os.path.join(out_dir, "_ilastik_log_%s.txt" % stamp)
	ok, failed, stopped, retrained = [], [], False, False
	IJ.resetEscape()
	fh = open(log_path, "w")
	try:
		run_start = time.time()
		groups = [todo[k:k + FILES_PER_RUN] for k in range(0, len(todo), FILES_PER_RUN)]
		for g, group in enumerate(groups):
			IJ.showStatus("ilastik: group %d of %d (%d image(s))" % (g + 1, len(groups), len(group)))
			IJ.showProgress(g, len(groups))
			IJ.log("  group %d/%d: %s" % (g + 1, len(groups),
			                              ", ".join([os.path.basename(x) for x in group])))
			code, info, whys = run_group(exe, project, out_dir, group, fh)
			retrained = retrained or (code == 0 and info["retrained"])
			stopped = code == -1
			if not stopped and code != 0 and len(group) > 1 and [w for w in whys if w]:
				# One unreadable image stops the whole call: retry one by one,
				# unless two in a row fail the same way (then it is the project).
				IJ.log("  ! ilastik stopped with exit code %s%s; the images without a "
				       "map are run again one at a time" % (code, info["error"] and
				                                             ": " + info["error"] or ""))
				last, same = None, 0
				for k, img in enumerate(group):
					if not whys[k] or stopped:
						continue
					if same >= 2:
						whys[k] = last
						continue
					c1, info1, w1 = run_group(exe, project, out_dir, [img], fh)
					retrained = retrained or (c1 == 0 and info1["retrained"])
					whys[k], stopped = w1[0], c1 == -1
					same = same + 1 if whys[k] and whys[k] == last else (1 if whys[k] else 0)
					last = whys[k]
			if retrained:
				# ilastik trained its own forest: these maps are not from the
				# saved classifier, so they are removed and the run stops.
				whys = ["ilastik found no saved classifier and trained a new one; "
				        "the map was removed"] * len(group)
				for img in group:
					out = output_for(img, out_dir)
					try:
						if os.path.isfile(out) and os.path.getmtime(out) >= run_start - 2:
							os.remove(out)
					except OSError:
						pass
			for img, why in zip(group, whys):
				if why:
					failed.append((os.path.basename(img), why))
					IJ.log("  %s  FAILED: %s" % (os.path.basename(img), why))
				else:
					ok.append(os.path.basename(img))
					IJ.log("  %s  -> %s" % (os.path.basename(img),
					                        os.path.basename(output_for(img, out_dir))))
			if stopped:
				IJ.log("  ! stopped with Esc during group %d" % (g + 1))
				break
			if retrained:
				break
	finally:
		fh.close()
	IJ.showProgress(1.0)
	rec = None
	if WRITE_PARAMETER_RECORD:
		items = record_items + [
		    ("#Configuration", ""), ("ilastik program", exe), ("ilastik project", project),
		    ("EXPORT_SOURCE", EXPORT_SOURCE), ("EXPORT_DTYPE", EXPORT_DTYPE),
		    ("PIPELINE_RESULT_DRANGE", PIPELINE_RESULT_DRANGE), ("EXPORT_DRANGE", EXPORT_DRANGE),
		    ("OUTPUT_FORMAT", OUTPUT_FORMAT), ("OUTPUT_NAME", OUTPUT_NAME),
		    ("FILES_PER_RUN", FILES_PER_RUN), ("THREADS", THREADS), ("RAM_MB", RAM_MB),
		    ("CONFIRM_BEFORE_RUN", CONFIRM_BEFORE_RUN),
		    ("#Result", ""), ("written", len(ok)), ("failed", len(failed)),
		    ("skipped (map existed)", skipped), ("stopped with Esc", stopped),
		    ("no trained classifier in project", retrained), ("ilastik log", log_path)]
		items += [("#Inputs", "")] + [("%d" % (k + 1), x) for k, x in enumerate(todo)]
		if failed:
			items += [("#Failed", "")] + [(a, b) for a, b in failed]
		rec = write_run_record(out_dir, SCRIPT_NAME, SCRIPT_VERSION, items)
	body = ("Probability maps written: %d\nFailed: %d\nSkipped (already there): %d\n"
	        "\nOutput folder: %s\nilastik log: %s\n" % (len(ok), len(failed), skipped,
	                                                   out_dir, log_path))
	if failed:
		body += ("\nCheck the Log window and the ilastik log. Common causes: a project "
		         "with no labels, images with other channels or dimensions than the "
		         "training images, or a project saved without a trained classifier "
		         "whose training images have since been moved.\n")
	if retrained:
		body += ("\nilastik found no saved classifier in the project and trained a new "
		         "one, so its maps were removed and the run stopped. Open the project in "
		         "ilastik, turn on Live Update, save it, and run this again.\n")
	if stopped:
		body += "\nStopped with Esc; run again to do the rest (finished maps are skipped).\n"
	if rec:
		body += "\nParameter record:\n%s" % rec
	shown = output_for(images[0], out_dir)
	if showResult and os.path.isfile(shown) and not check_output(shown):
		try:
			imp, _n = bf_open(shown)
			imp.show()
		except StepError, e:
			IJ.log("  could not show %s: %s" % (os.path.basename(shown), e))
	IJ.beep()
	IJ.showMessage(SCRIPT_NAME + (" - with failures" if failed or stopped else ""), body)


main()
