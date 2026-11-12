# Run_Stages_for_an_Animal.py - Kapur Lab Cell Counting: run batch stages on
# every slide of ONE animal, one slide after another, with one set of
# settings for all of them.
#
# Menu: Plugins > Kapur Lab Cell Counting > Run Stages for an Animal
# You pick the animal folder (it holds the animal's slide folders), the
# region (its MBF folder in each slide), and the stages. Each stage then asks
# its settings once (the same fields as its own dialog, without the slide
# and region), and a Check settings window lists every slide, what will run
# on it, and what is missing, before anything is changed.
# Each slide is processed exactly as the stage's Batch script does it on
# that slide alone: its outputs go into that slide's folders (tifs/ in the
# slide folder, everything else in its region MBF folder), and each slide's
# region folder gets a record of this run (_run_Run_Stages_for_an_Animal_
# <time>.txt: the animal, the slides run together, the settings, what
# happened). Slides are never pooled: counts stay per slide and per section.
# Only these are written in the animal folder: the combined tables of the
# animal's slides after stage 3 (particle_counts_all_slides_<region>.csv and
# ..._by_region_...), and the animal's ilastik project, which you save there.
# ilastik: with "the animal's project", one project trained on images from
# the animal's slides is used for all of them (2c Run ilastik Headless also
# finds a project in the animal folder when run on one slide).
# The stages run without their windows: the region and folders are found in
# each slide, the runner's Check settings window stands for theirs, and their
# closing messages go into the runner's summary and the Log.
# A slide that has no region folder of that name, lacks a stage's input, or
# is marked include = no in experiment_layout.csv is skipped for that stage
# and listed. A stage that fails on a slide stops the later stages for that
# slide only. Esc stops the run when the stage that is running ends (2c stops
# at once).
# 2a.i Review, 0 Optimize, NeuroInfo, ilastik training and Tune stay one at
# a time: they need you.
# Leave Fiji alone while it runs: a window that opens during a stage is
# closed (a question is cancelled), since no stage should ask anything here.

#@ File    (label="Animal folder (holds the animal's slide folders)", style="directory") animalDir
#@ String  (label="Region (its MBF folder in each slide, e.g. hippocampus; blank = the only one)", value="", required=false) regionName
#@ File    (label="Raw data top folder (the tree with the .nd2/.ims files; for stage 1; blank = in the slide folders)", style="directory", required=false) rawRoot
#@ Boolean (label="1 Convert to Tif", value=false) run1
#@ Boolean (label="2a NeuroInfo XML to ROI", value=false) run2a
#@ Boolean (label="2b BG Subtract and Clear", value=false) run2b
#@ Boolean (label="2c Run ilastik Headless", value=false) run2c
#@ Boolean (label="3 Count Particles per ROI", value=false) run3
#@ Boolean (label="4 Build Pipeline Composite", value=false) run4


# =========================================================================
# ===  USER CONFIGURATION  ================================================
# =========================================================================

# Show the Check settings window before anything runs.
CONFIRM_BEFORE_RUN = True

# Write the combined tables of the animal's slides after stage 3.
WRITE_ANIMAL_TABLES = True

# =========================================================================
# ===  END OF USER CONFIGURATION  =========================================
# =========================================================================

SCRIPT_NAME = "Run_Stages_for_an_Animal"
SCRIPT_VERSION = "2.0"

import os
import re
import time
from ij import IJ, Prefs
from java.lang import Exception as JavaException, System, Thread, Runnable
from java.io import File

ANY_ERROR = (Exception, JavaException)
MISSING_VALUE = "NA"
WHOLE = "__WHOLE_IMAGE__"
GROUP_VALS = []

# key, Batch script, its name, folders it reads (none: stage 1's raw files),
# the dialog field naming its output folder
STAGES = [
	("1", "1_Convert_to_Tif.py", "1 Convert to Tif", [], "outFolderName"),
	("2a", "2a_NeuroInfo_XML_to_ROI.py", "2a NeuroInfo XML to ROI", ["xml"], "outFolderName"),
	("2b", "2b_BG_Subtract_and_Clear.py", "2b BG Subtract and Clear", ["tifs", "rois"], "outFolderName"),
	("2c", "2c_Run_ilastik_Headless.py", "2c Run ilastik Headless", ["processed_bgsub_cleared"], None),
	("3", "3_Count_Particles_per_ROI.py", "3 Count Particles per ROI", ["probabilities", "rois"], "outFolderName"),
	("4", "4_Build_Pipeline_Composite.py", "4 Build Pipeline Composite",
	 ["tifs", "processed_bgsub_cleared", "probabilities"], "outFolderName"),
]
MAKES = {"1": "tifs", "2a": "rois", "2b": "processed_bgsub_cleared", "2c": "probabilities",
         "3": "particle_counts", "4": "pipeline_composites"}
# Fields this script fills in for every slide, and fixed values.
GIVEN = ("slideDir", "regionName", "outParentDir", "rawRoot", "sectionKey")
FIXED = {"4": {"showComposites": False}}
ANIMAL_PROJECT = "(the animal's project: an .ilp in the animal folder)"
OWN_PROJECT = "(each slide's own project, in its region folder)"
STATE_NAME = "_paused_Run_Stages_for_an_Animal%s.json"   # in the animal folder; %s = _<region>
REVIEW_NOW = "Review the ROIs of each slide now (2a.i opens on one slide after another)"
REVIEW_SKIP = "Continue without reviewing"
PROJECT_LABEL = "ilastik project (.ilp)"
DONE_TITLES = ("Conversion complete", "Batch complete", "Batch STOPPED", "Counting complete",
               "Composites complete")


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
	with open(path, "rb") as fh:        # closed now: Windows locks open files
		raw = fh.read()
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


# ---- SHARED: raw_tree -- keep identical ----
# The .nd2 / .ims files may sit in another tree that mirrors the slide
# folders (the same day / treatment / animal / slide folders, another top).
def layout_raw(slide, raw_root, strict=True):
	"""The slide's folder in the raw tree: the longest end of the slide's
	path found below raw_root, or raw_root itself when it is named like the
	slide. strict: the folder above must have the same name too, so another
	animal's slide folder of the same name is never taken. None if not found."""
	import os
	if not raw_root:
		return None
	low = lambda p: [x.lower() for x in os.path.normpath(p).replace("\\", "/").split("/") if x]
	parts = [p for p in os.path.normpath(slide).replace("\\", "/").split("/") if p]
	end = low(slide)[-2:]
	for k in range(1, len(parts)):
		cand = os.path.join(raw_root, *parts[k:])
		if os.path.isdir(cand) and (not strict or low(cand)[-2:] == end):
			return cand
	if low(raw_root)[-1:] == end[-1:] and (not strict or low(raw_root)[-2:] == end):
		return raw_root
	return None
# ---- END SHARED: raw_tree ----


# ---- SHARED: region_table -- keep identical ----
# particle_counts_by_region.csv: one row per image and ROI, with its count,
# area and density. Needs MISSING_VALUE, WHOLE, GROUP_VALS.
REGION_TABLE_HEADER = ["roi_file", "region", "side", "roi", "count",
                       "area_px", "area_mm2", "cells_per_mm2"]


def add_in_order(cols, names):
	"""Add the names not in cols, each right after the name before it (or
	at the end), so a column only some sections have stays beside its
	neighbours."""
	prev = None
	for n in names:
		if n not in cols:
			cols.insert(prev in cols and cols.index(prev) + 1 or len(cols), n)
		prev = n


def um_per_px(rois, imp):
	"""(x, y) micrometres per pixel: stored in the ROIs by 2a, else the
	image's calibration in microns; None when unknown."""
	for r in rois.values():
		p = r.getProperty("um_per_px")
		try:
			x, y = [float(v) for v in (p or "").split(",")][:2]
			if x > 0 and y > 0:
				return x, y
		except ValueError:
			pass
	c = imp.getCalibration()
	if (c.getUnit() or "").lower() in ("micron", "microns", "um", u"\u00b5m") \
	    and c.pixelWidth > 0 and c.pixelHeight > 0:
		return c.pixelWidth, c.pixelHeight
	return None


def area_in_image(roi, w, h):
	"""Pixels of roi inside a w x h image."""
	b = roi.getBounds()
	x0, y0 = max(0, b.x), max(0, b.y)
	x1, y1 = min(w, b.x + b.width), min(h, b.y + b.height)
	if x1 <= x0 or y1 <= y0:
		return 0
	m = roi.getMask()
	if m is None:
		return (x1 - x0) * (y1 - y0)
	m.setRoi(x0 - b.x, y0 - b.y, x1 - x0, y1 - y0)
	n = m.crop().getHistogram()[255]
	m.resetRoi()
	return n


def region_rows(image, roi_file, counts, areas, um):
	"""The image's rows of the region table (its ROIs on the image). A name
	ending in -L / -R gives side left / right; any other ROI has no side."""
	out = []
	for name, n in counts.items():
		if name == WHOLE or n == MISSING_VALUE or name not in areas:
			continue
		m = re.match(r"(.*)-([LR])$", name)
		reg, side = m and (m.group(1), m.group(2) == "L" and "left" or "right") or (name, "")
		mm2 = um and areas[name] * um[0] * um[1] / 1e6
		out.append([image] + GROUP_VALS + [roi_file, reg, side, name, n, areas[name],
		           mm2 and "%.6f" % mm2 or MISSING_VALUE,
		           mm2 and "%.2f" % (n / mm2) or MISSING_VALUE])
	return out
# ---- END SHARED: region_table ----


from java.awt import Window, Dialog, FileDialog, Container, Label, TextComponent, TextField, EventQueue
from java.awt.event import WindowEvent
from java.lang import Throwable
from java.awt import Toolkit, AWTEvent
from java.awt.event import AWTEventListener, KeyEvent


def b(x):
	"""UTF-8 bytes of a name or path (tables and records mix both)."""
	return isinstance(x, unicode) and x.encode("utf-8") or str(x)


def read_file(path, mode="r"):
	"""The file's contents, the file closed at once: on Windows a file that is
	still open cannot be renamed or removed, by this run or another program."""
	fh = open(path, mode)
	try:
		return fh.read()
	finally:
		fh.close()


def script_text(path):
	"""A script's source with Unix line ends (a copy made on Windows may have
	CR LF)."""
	return read_file(path, "rb").replace("\r\n", "\n").replace("\r", "\n")


# ------------------------------------------------------- stage scripts
def stage_dir():
	"""The folder of this suite (it holds Batch/), or None."""
	if globals().get("KLCC_DIR"):          # the automated tests
		return KLCC_DIR
	base = os.path.join(IJ.getDirectory("imagej") or "", "scripts", "Plugins")
	hits = []
	for cur, dirs, files in os.walk(base):
		if os.path.isfile(os.path.join(cur, "Batch", "3_Count_Particles_per_ROI.py")):
			hits.append(cur)
		if cur[len(base):].count(os.sep) >= 2:
			dirs[:] = []
	own = [h for h in hits if os.path.isfile(os.path.join(h, SCRIPT_NAME + ".py"))]
	return (sorted(own) or sorted(hits) or [None])[0]


def parse_fields(path):
	"""The #@ fields of a script: (var, type, label, default, choices, style)."""
	out = []
	for line in script_text(path).split("\n"):
		m = re.match(r"#@\s*(\w+)\s*\((.*)\)\s*(\w+)\s*$", line)
		if not m:
			continue
		typ, opts, var = m.group(1), m.group(2), m.group(3)
		lab = re.search(r'label="([^"]*)"', opts)
		ch = re.search(r"choices=\{(.*?)\}", opts)
		choices = ch and re.findall(r'"([^"]*)"', ch.group(1)) or None
		v = re.search(r'value=("([^"]*)"|[^,)\s]+)', opts)
		if v is None:
			default = choices and choices[0] or {"Boolean": False, "Integer": 0.0,
			                                     "Double": 0.0}.get(typ, "")
		elif v.group(2) is not None:
			default = v.group(2)
		elif typ == "Boolean":
			default = v.group(1).lower() == "true"
		elif typ in ("Integer", "Double"):
			default = float(v.group(1))
		else:
			default = v.group(1)
		st = re.search(r'style="([^"]*)"', opts)
		out.append((var, typ, lab and lab.group(1) or var, default, choices,
		            st and st.group(1) or ""))
	return out


def typed_values(key, fields, vals):
	"""Values as the script expects them: int, float, bool, File or None."""
	out = {}
	for var, typ, label, default, choices, style in fields:
		v = vals.get(var, default)
		if typ == "Integer":
			v = int(round(float(v)))
		elif typ == "Double":
			v = float(v)
		elif typ == "Boolean":
			v = v in (True, "true", "True", 1)
		elif typ == "File":
			v = v and File(v) or None
		else:
			v = v is None and u"" or (u"%s" % v)
		out[var] = v
	out.update(FIXED.get(key, {}))
	return out


def pref_text(v):
	"""A setting as remembered in Fiji's preferences (unicode, exact)."""
	if isinstance(v, bool):
		return str(v).lower()
	if isinstance(v, float):
		return repr(v)
	return isinstance(v, unicode) and v or unicode(v)


def ask_settings(key, name, fields):
	"""The stage's settings for every slide (remembered between runs), as
	(values for the script, [(label, value)]); None if cancelled."""
	from ij.gui import GenericDialog
	use = [f for f in fields if f[0] not in GIVEN and f[0] not in FIXED.get(key, {})]
	test = globals().get("RUNNER_SETTINGS")
	if test is not None:                     # the automated tests
		vals = dict([(f[0], f[3]) for f in use])
		vals.update(test.get(key, {}))
	else:
		gd = GenericDialog("%s - settings for every slide" % name)
		gd.addMessage("The same settings are used for every slide of the animal.\n"
		              "The folders are found in each slide, as when the stage runs on one slide.")
		for var, typ, label, default, choices, style in use:
			saved = Prefs.get("kapurcellcount.animal.%s.%s" % (key, var), None)
			if choices:
				gd.addChoice(label, choices, saved in choices and saved or default)
			elif typ == "Boolean":
				gd.addCheckbox(label, saved == "true" if saved is not None else default)
			elif typ in ("Integer", "Double"):
				try:
					x = float(saved)
				except (TypeError, ValueError):
					x = default
				gd.addNumericField(label, x, 0 if typ == "Integer" else 3)
			elif typ == "File" and style == "directory":
				gd.addDirectoryField(label, saved or "", 40)
			elif typ == "File":
				gd.addFileField(label, saved or "", 40)
			else:
				gd.addStringField(label, saved if saved is not None else default, 30)
		gd.showDialog()
		if gd.wasCanceled():
			return None
		if gd.invalidNumber():
			IJ.error(SCRIPT_NAME, "%s: a number field holds something that is not a number." % name)
			return None
		vals = {}
		for var, typ, label, default, choices, style in use:
			if choices:
				v = gd.getNextChoice()
			elif typ == "Boolean":
				v = gd.getNextBoolean()
			elif typ in ("Integer", "Double"):
				v = gd.getNextNumber()
			else:
				v = gd.getNextString().strip()
			vals[var] = v
			Prefs.set("kapurcellcount.animal.%s.%s" % (key, var), pref_text(v))
	got = typed_values(key, use, vals)
	return got, [(f[2].strip(), shown_value(got[f[0]])) for f in use]


def shown_value(v):
	"""A setting as the Check settings window and the records show it."""
	return v is None and "(blank)" or isinstance(v, File) and v.getAbsolutePath() or \
	    v == "" and "(blank)" or v


def choose_project(animal):
	"""2c's ilastik project: ANIMAL_PROJECT (an .ilp in the animal folder, found
	when 2c is reached) or OWN_PROJECT; None if cancelled."""
	if "RUNNER_PROJECT" in globals():        # the automated tests (a mode or a path)
		return RUNNER_PROJECT
	from ij.gui import GenericDialog
	opts = [ANIMAL_PROJECT, OWN_PROJECT]
	last = Prefs.get("kapurcellcount.animal.projectmode", ANIMAL_PROJECT)
	gd = GenericDialog("2c Run ilastik Headless - project")
	gd.addMessage("Which ilastik project 2c uses. The project need not exist yet: when 2b\n"
	              "runs in this run, the run stops before 2c so you can train it.")
	gd.addChoice("ilastik project", opts, last in opts and last or opts[0])
	gd.showDialog()
	if gd.wasCanceled():
		return None
	pick = gd.getNextChoice()
	Prefs.set("kapurcellcount.animal.projectmode", pick)
	return pick


def animal_projects(animal):
	"""[(.ilp path, trained)] in the animal folder."""
	try:
		names = sorted(os.listdir(animal))
	except OSError:
		return []
	return [(os.path.join(animal, n), stored_classifier(os.path.join(animal, n)))
	        for n in names if n.lower().endswith(".ilp") and not n.startswith(".")]


# --------------------------------------------------------- slides of the animal
def raw_files_in(folder, exts):
	"""Raw files of these types in folder, or in its nd2/ or ims/ folder."""
	out = []
	for d in (folder, os.path.join(folder, "nd2"), os.path.join(folder, "ims")):
		try:
			out += [n for n in os.listdir(d) if not n.startswith(".")
			        and os.path.splitext(n)[1].lower() in exts]
		except OSError:
			pass
	return out


def slide_like(path, exts):
	"""A folder with a sign of a slide: a region folder, a pipeline folder
	(tifs, jpx, rois, ...) or raw files."""
	if layout_regions(path):
		return True
	try:
		low = [n.lower() for n in os.listdir(path)]
	except OSError:
		return False
	return bool([n for n in low if n in LAYOUT_SLIDE_LEVEL + LAYOUT_REGION_SUBS
	             or os.path.splitext(n)[1] in exts])


def animal_slides(animal, raw_animal, exts):
	"""The animal's slide folders: its subfolders that look like slides, and
	those of the raw tree (their folder here may not exist yet)."""
	found = {}
	skip = [n.lower() for n in LAYOUT_SLIDE_LEVEL + LAYOUT_REGION_SUBS]
	for base, here in ((animal, True), (raw_animal, False)):
		try:
			names = sorted(os.listdir(base or ""))
		except OSError:
			names = []
		for n in names:
			p = os.path.join(base, n)
			if n.startswith(".") or not os.path.isdir(p) or n.lower() in skip \
			        or n.lower() in found or layout_is_region(p):
				continue
			if (here and slide_like(p, exts)) or (not here and raw_files_in(p, exts)):
				found[n.lower()] = os.path.join(animal, n)
	return sorted(found.values(), key=natural)


def natural(path):
	"""Sort key: slide1, slide 2, ..., slide 10."""
	n = os.path.basename(path).lower()
	return [int(t) if t.isdigit() else re.sub(r"[^a-z]", "", t) for t in re.split(r"(\d+)", n)], n


def region_of(slide, typed):
	"""(region folder, or the slide in the protocol layout; why, when no
	single region folder fits)."""
	regions = layout_regions(slide)
	here = [d for d in LAYOUT_REGION_SUBS if os.path.isdir(os.path.join(slide, d))]
	hits = typed and layout_match_region(regions, typed) or []
	if len(hits) == 1:
		return os.path.join(slide, hits[0]), ""
	if not typed and not regions:
		return slide, ""
	if not typed and len(regions) == 1 and not here:
		return os.path.join(slide, regions[0]), ""
	if not regions:
		return None, ("it has no region (MBF) folder; run Set Up Slide Folders, "
		              "or leave Region blank")
	return None, "%s (it has %s)" % (typed and "no single region folder matches '%s'"
	                                 % typed or "Region is blank", ", ".join(regions + (
	                                     here and ["pipeline folders in the slide folder"] or [])))


def has_files(d):
	try:
		return [n for n in os.listdir(d) if n[:1] not in "._"
		        and os.path.isfile(os.path.join(d, n))]
	except OSError:
		return []


def stored_classifier(project):
	"""True when the .ilp holds a trained classifier (saved after Live Update)."""
	try:
		fh = open(project, "rb")
	except IOError:
		return False
	try:
		tail = ""
		while True:
			chunk = fh.read(1 << 20)
			if not chunk:
				return False
			if "Forest0000" in tail + chunk:
				return True
			tail = chunk[-16:]
	finally:
		fh.close()


def raw_folder(slide, raw_root, ft):
	"""The folder stage 1 reads for this slide (by its own rule), or ""."""
	base = raw_root and layout_raw(slide, raw_root) or (not raw_root and slide) or ""
	order = ft == ".ims" and ("ims", "nd2") or ("nd2", "ims")
	subs = [os.path.join(base, n) for n in order if base and os.path.isdir(os.path.join(base, n))]
	return (subs or [base])[0]


def missing_input(key, slide, region, made, settings, raw_root, project, now=True):
	"""Why the stage cannot run on this slide, or "". now=False: 2c's
	project is checked when 2c is reached (it may be trained at the break)."""
	if key == "1":
		ft = (settings["1"][0].get("fileType") or "").lower()
		d = raw_folder(slide, raw_root, ft)
		if not d:
			return "its folder was not found in the raw data top folder"
		return not [n for n in has_files(d) if n.lower().endswith(ft)] and \
		    "no %s files in %s" % (ft, d) or ""
	for name in [n for n in dict([(s[0], s[3]) for s in STAGES])[key] if n not in made]:
		if not has_files(layout_find(slide, region, name)):
			return "no files in %s/ (run the stage that makes it first)" % name
	if key == "2c" and now and project == OWN_PROJECT and not own_ilp(region, slide):
		return "no trained ilastik project in its region folder"
	return ""


def own_ilp(region, slide):
	"""The trained .ilp files of the slide's region folder (then slide folder)."""
	return [os.path.join(d, f) for d in (region, slide) if d for f in has_files(d)
	        if f.lower().endswith(".ilp") and stored_classifier(os.path.join(d, f))]


# ---------------------------------------------------- running the stages
class Unattended(object):
	"""Stands in for the windows of a stage run on one slide of the animal:
	the region, the folders found and the Check settings window."""

	def __init__(self, typed, folders):
		self.typed, self.folders, self.stop, self.warnings = typed, folders, "", []
		self.messages = []

	def message(self, *args):
		"""Takes the place of IJ.showMessage and IJ.error in the stage."""
		title, text = len(args) > 1 and (args[0], args[1]) or ("", args and args[0] or "")
		self.messages.append((title or "", text or ""))

	def pick_region(self, slide, typed):
		region, why = region_of(slide, self.typed)
		self.stop = why
		return region

	def confirm(self, title, slide, region, fields):
		out = []
		for label, kind, v, options, required in fields:
			v = self.folders.get(label, v) or ""
			if required and (not v or not (kind == "dir" and os.path.isdir(v)
			                                or kind != "dir" and os.path.isfile(v))):
				self.stop = "%s: not found (%s)" % (label, v or "none")
				return None
			out.append(v)
		return out

	def check(self, name, lines):
		w = [ln[1:].strip() for ln in lines if ln.startswith("!")]
		for x in w:
			IJ.log("WARNING: " + x)
		self.warnings += w
		return True


class _Close(Runnable):
	"""Closes a window as its close box would (a question: cancelled)."""
	def __init__(self, w):
		self.w = w

	def run(self):
		self.w.dispatchEvent(WindowEvent(self.w, WindowEvent.WINDOW_CLOSING))
		if self.w.isShowing():
			self.w.dispose()


class Watch(Runnable):
	"""While a stage runs: notes and closes any window it shows that the
	runner did not take over (none is expected)."""

	def __init__(self):
		self.on, self.seen, self.known, self.alive, self.esc = False, [], set(), True, False
		self.listen = False          # Esc counts while unattended stages run, not at a break

	def text(self, c, out):
		from ij.gui import MultiLineLabel
		if isinstance(c, MultiLineLabel):
			try:
				out.append(c.getText())
			except ANY_ERROR:
				try:
					f = MultiLineLabel.getDeclaredField("lines")
					f.setAccessible(True)
					out.append("\n".join([str(x) for x in f.get(c)]))
				except ANY_ERROR:
					pass
		elif isinstance(c, Label):
			out.append(c.getText())
		elif isinstance(c, TextComponent) and not isinstance(c, TextField):
			out.append(c.getText())
		if isinstance(c, Container):
			for k in c.getComponents():
				self.text(k, out)

	def run(self):
		n = 0
		while self.alive:
			# Esc, noted at once: opening a stack clears ImageJ's own flag
			self.esc = self.esc or (self.listen and IJ.escapePressed())
			n += 1
			try:
				for w in (self.on and n % 2 == 0 and Window.getWindows() or []):
					if id(w) in self.known or not w.isShowing() or not isinstance(w, Dialog) \
					        or isinstance(w, FileDialog):
						continue
					self.known.add(id(w))
					out = []
					self.text(w, out)
					self.seen.append((w.getTitle() or "", "\n".join([x for x in out if x])))
					EventQueue.invokeLater(_Close(w))
			except ANY_ERROR:
				pass
			Thread.sleep(25)


class EscKey(AWTEventListener):
	"""Notes Esc pressed in any Fiji window during the run (ImageJ's own Esc
	flag is cleared each time a stack is opened, so it can be missed)."""
	def __init__(self, watch):
		self.watch = watch

	def eventDispatched(self, e):
		if self.watch.listen and e.getID() == KeyEvent.KEY_PRESSED and \
		        e.getKeyCode() == KeyEvent.VK_ESCAPE:
			self.watch.esc = True


def verdict(un, seen, err):
	"""(status, detail) of one stage on one slide."""
	if err:
		return "FAILED", err
	if un.stop:
		return "skipped", un.stop
	if [s for s in seen if "Stopped with Esc" in s[1]]:
		return "stopped", "stopped with Esc"
	done = [s for s in seen if s[0].startswith(DONE_TITLES) or "Probability maps written" in s[1]]
	if not done:
		return "stopped", seen and "%s: %s" % (seen[0][0], " ".join(
		    seen[0][1].split())[:300]) or "it ended before it finished; see the Log"
	title = done[-1][0]
	if "fail" in title.lower() or "STOPPED" in title:
		return "failed", "%s; see the Log" % title
	if "problem" in title.lower() or un.warnings:
		return "done, with warnings", "; ".join(un.warnings[:3]) or "%s; see the Log" % title
	return "done", ""


def stage_code(path):
	"""The stage, compiled with its message windows (IJ.showMessage and
	IJ.error) handed to the runner, which reports them in its summary."""
	src = re.sub(r"\bIJ\.(showMessage|error)\(", "_UNATTENDED.message(", script_text(path))
	return compile(src, path, "exec")


def run_stage(code, key, slide, typed, values, raw_root, project, watch):
	"""Run one Batch stage on one slide, as if started there by hand:
	(status, detail, counting settings stage 3 used, the stage's warnings,
	[results table, region table] stage 3 wrote) and True after a Java Error
	(out of memory and the like), which ends the run."""
	un = Unattended(typed, {})
	if key == "2c" and project and project != OWN_PROJECT:
		un.folders[PROJECT_LABEL] = project
	g = {"__name__": "__main__", "_UNATTENDED": un}
	g.update(values)
	g.update({"slideDir": File(slide), "regionName": typed, "outParentDir": None})
	if key == "1":
		g["rawRoot"] = raw_root and File(raw_root) or None
	watch.seen, watch.on, err, fatal = [], True, "", False
	try:
		try:
			exec code in g
		except SystemExit:
			pass
		except ANY_ERROR, e:
			err = "%s: %s" % (type(e).__name__, e)
		except Throwable, e:
			err, fatal = "%s: %s" % (e.getClass().getSimpleName(), e.getMessage()), True
		Thread.sleep(200)            # let a last window be noted
	finally:
		watch.on = False
	seen = un.messages + list(watch.seen)
	for t, x in seen:
		if not (t.startswith(DONE_TITLES) or "Probability maps written" in x):
			IJ.log("  [%s] %s" % (t, x.replace("\n", "\n  ")))
	res = verdict(un, seen, err)
	used, tables = "", []
	if key == "3" and res[0].startswith("done"):
		used = g.get("USE_TUNED") and "tuned values in %s" % g.get("TUNED_PATH") or \
		    "the values in the dialog"
		tables = [g.get("csv_written") and g.get("CSV_PATH") or None, g.get("REGION_PATH") or None]
	g.clear()
	return res + (used, list(un.warnings), tables), fatal


# ---------------------------------------------------------------- breaks
def tuned_file(slide, region):
	"""The tuned file stage 3 would use for this slide and region folder, or
	None (stage 3's rule: the experiment folder, else up to 8 folders up;
	counting_tuning/ first; a file tuned on another region is not used)."""
	csv_path = layout_csv_row(slide)[0]
	name = region and region != slide and layout_is_region(region) and os.path.basename(region) or ""
	tag = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
	d, dirs = os.path.abspath(slide), []
	for _k in range(9):
		dirs.append(d)
		d = os.path.dirname(d)
	for d in csv_path and [os.path.dirname(csv_path)] or dirs:
		for sub in ("counting_tuning", ""):
			for s in (tag and "_" + tag, ""):
				p = os.path.join(d, sub, "tuned_counting_parameters%s.txt" % s)
				if os.path.isfile(p):
					v = dict([[x.strip() for x in ln.split("=", 1)] for ln in read_file(p)
					          .splitlines() if "=" in ln and ln[:1] != "#"])
					return layout_text(v.get("region", "\0")) in (name, "\0") and p or None
	return None


def experiment_maps(animal, typed):
	"""(slides with probability maps, included slides) in the experiment table
	above the animal folder, for the region; (0, 0) without a table."""
	csv_path = layout_csv_up(animal)[0]
	if not csv_path:
		return 0, 0
	have = total = 0
	for row in layout_read_csv(csv_path)[1]:
		if row.get("include", "").lower() in ("no", "n", "0", "false"):
			continue
		slide = os.path.join(os.path.dirname(csv_path), *[x for x in row.get(
		    "slide_path", "").replace("\\", "/").split("/") if x])
		total += 1
		region = os.path.isdir(slide) and region_of(slide, typed)[0]
		if region and [n for n in has_files(os.path.join(region, "probabilities"))
		               if n.lower().endswith((".tif", ".tiff"))]:
			have += 1
	return have, total


def break_window(title, lines, radios=None, project=None, ok="Continue"):
	"""A window that stays open while the person works in Fiji or ilastik:
	(radio picked, project picked); None for Stop here."""
	from java.awt import GraphicsEnvironment, TextArea, Panel
	from ij.gui import NonBlockingGenericDialog
	gd = NonBlockingGenericDialog("Run Stages for an Animal - break: " + title)
	if len(lines) > 24 or max([len(x) for x in lines] + [0]) > 110:
		rows = max(8, (GraphicsEnvironment.getLocalGraphicsEnvironment()
		               .getMaximumWindowBounds().height - 360) // 17)
		ta = TextArea("\n".join(lines), min(rows, len(lines) + 2), 100,
		              TextArea.SCROLLBARS_VERTICAL_ONLY)
		ta.setEditable(False)
		pn = Panel()
		pn.add(ta)
		gd.addPanel(pn)
	else:
		gd.addMessage("\n".join(lines))
	if project:
		gd.addChoice("Project to use", project, project[0])
	if radios:
		gd.addRadioButtonGroup("", radios, len(radios), 1, radios[0])
	gd.addMessage("Stop here keeps everything done so far. Run this script on the animal\n"
	              "again later and it offers to continue from this break.")
	gd.setOKLabel(ok)
	gd.setCancelLabel("Stop here")
	IJ.log("-" * 64)
	IJ.log("Break: %s. The run waits (%s)." % (title, time.strftime("%H:%M")))
	gd.showDialog()
	if gd.wasCanceled():
		IJ.log("  Stop here pressed at %s." % time.strftime("%H:%M"))
		return None
	pick = project and gd.getNextChoice() or None
	radio = radios and gd.getNextRadioButton() or None
	IJ.log("  Continued at %s%s." % (time.strftime("%H:%M"), radio and ": " + radio or
	                                  pick and ": project " + pick or ""))
	return radio, pick


def review_slide(code, slide, typed, raw_root):
	"""2a.i Review and Edit ROIs on one slide, with its folders filled in;
	its own windows are shown as usual. "" or what went wrong."""
	un = Unattended(typed, {})
	g = {"__name__": "__main__", "_UNATTENDED": un, "slideDir": File(slide),
	     "regionName": typed, "rawRoot": raw_root and File(raw_root) or None,
	     "nameFilter": u"", "startAt": u""}
	err = ""
	try:
		exec code in g
	except SystemExit:
		pass
	except ANY_ERROR, e:
		err = "%s: %s" % (type(e).__name__, e)
	except Throwable, e:
		err = "%s: %s" % (e.getClass().getSimpleName(), e.getMessage())
	g.clear()
	return un.stop or err


def state_path(animal, typed):
	"""The paused run of this region: <animal>/_paused_Run_Stages_for_an_Animal[_<region>].json"""
	tag = re.sub(r"[^A-Za-z0-9]+", "_", typed or "").strip("_")
	return os.path.join(animal, STATE_NAME % (tag and "_" + tag or ""))


def paused_regions(animal):
	"""Regions with a paused run on this animal (from the file names)."""
	pre, post = STATE_NAME.split("%s")
	try:
		names = os.listdir(animal)
	except OSError:
		return []
	return [n[len(pre):-len(post)].lstrip("_") or "(blank)" for n in sorted(names)
	        if n.startswith(pre) and n.endswith(post)]


def save_state(animal, typed, info):
	"""The paused run, so that the next run on this animal can continue it."""
	import json
	def plain(v):
		return isinstance(v, File) and {"file": v.getAbsolutePath()} or v
	info, sets = dict(info), info["settings"]
	info["settings"] = dict([(k, dict([(n, plain(x)) for n, x in v[0].items()]))
	                         for k, v in sets.items()])
	info["shown"] = dict([(k, [[a, u"%s" % x] for a, x in v[1]]) for k, v in sets.items()])
	p = state_path(animal, typed)
	try:
		fh = open(p, "w")
		fh.write(json.dumps(info, indent=1))
		fh.close()
		return p
	except IOError, e:
		IJ.log("WARNING: the paused run could not be saved (%s)" % e)
		return None


def load_state(animal, typed):
	"""The paused run of this region, or None (an unreadable file is ignored
	and named in the Log)."""
	import json
	p = state_path(animal, typed)
	if not os.path.isfile(p):
		return None
	try:
		info = json.loads(read_file(p))
		def back(v):
			return isinstance(v, dict) and "file" in v and File(v["file"]) or v
		info["settings"] = dict([(k, (dict([(n, back(x)) for n, x in v.items()]),
		                              [tuple(y) for y in info.get("shown", {}).get(k, [])]))
		                         for k, v in info["settings"].items()])
		info["stages"] = [k for k in info["stages"] if k in info["settings"]]
		for k in ("broken", "done", "tables", "used"):
			info[k] = dict(info.get(k) or {})
		info["reviewed"] = list(info.get("reviewed") or [])
		return info["stages"] and info or None
	except (ANY_ERROR, Throwable), e:
		IJ.log("WARNING: %s could not be read (%s); it is ignored" % (p, e))
		return None


def forget_state(animal, typed):
	p = state_path(animal, typed)
	try:
		if os.path.isfile(p):
			os.remove(p)
	except OSError, e:
		IJ.log("WARNING: %s could not be removed (%s)" % (p, e))


# ------------------------------------------------------------- outputs
def read_table(path):
	import csv
	raw = read_file(path, "rb")
	if raw.startswith("\xef\xbb\xbf"):
		raw = raw[3:]
	first = raw.split("\n")[0]
	rows = [r for r in csv.reader(raw.splitlines(), delimiter=first.count(";") >
	        first.count(",") and ";" or ",") if r]
	return rows[0], [dict(zip(rows[0], r)) for r in rows[1:]]


def animal_tables(animal, plan, tag):
	"""<table>_all_slides_<region>.csv in the animal folder: the tables stage
	3 wrote in this run, slide after slide, with animal_folder and
	slide_folder columns first; a ROI column a slide lacks is NA there (an
	earlier combined table is kept as _previous_<time>). Paths written."""
	written = []
	for i, name in enumerate(("particle_counts", "particle_counts_by_region")):
		parts = []
		for r in plan:
			got = r["stages"].get("3", ("",))
			p = got[0].startswith("done") and len(got[4]) > i and got[4][i]
			if p and os.path.isfile(p):
				try:
					parts.append((b(r["name"]),) + read_table(p))
				except ANY_ERROR, e:
					IJ.log("  ! %s could not be read: %s" % (p, e))
		if not parts:
			continue
		cols = []
		for _s, head, _d in parts:
			add_in_order(cols, head)
		rois = "channel_means" in cols and cols[cols.index("channel_means") + 1:] or []
		path = os.path.join(animal, "%s_all_slides_%s.csv" % (name, tag))
		if os.path.exists(path):
			keep, n = "%s_previous_%s" % (path[:-4], time.strftime("%Y%m%d-%H%M%S")), 1
			while os.path.exists(keep + (n > 1 and "_%d" % n or "") + ".csv"):
				n += 1
			try:
				os.rename(path, keep + (n > 1 and "_%d" % n or "") + ".csv")
			except OSError:
				IJ.log("  ! the earlier %s could not be renamed; it is replaced" % path)
		fh = open(path, "w")
		try:
			fh.write(",".join(['"%s"' % c for c in ["animal_folder", "slide_folder"] + cols]) + "\n")
			for s, _head, data in parts:
				for d in data:
					fh.write(",".join(['"%s"' % x.replace('"', "'") for x in [b(os.path.basename(animal)), s] + [
					    d.get(c, c in rois and MISSING_VALUE or "") for c in cols]]) + "\n")
		finally:
			fh.close()
		written.append(path)
	return written


def show_summary(title, lines):
	from java.awt import GraphicsEnvironment, TextArea, Panel
	from ij.gui import GenericDialog
	if len(lines) <= 22 and max([len(x) for x in lines] + [0]) <= 110:
		IJ.showMessage(title, "\n".join(lines))
		return
	gd = GenericDialog(title)
	rows = max(8, (GraphicsEnvironment.getLocalGraphicsEnvironment()
	               .getMaximumWindowBounds().height - 300) // 17)
	ta = TextArea("\n".join(lines), min(rows, len(lines) + 2), 105, TextArea.SCROLLBARS_VERTICAL_ONLY)
	ta.setEditable(False)
	pn = Panel()
	pn.add(ta)
	gd.addPanel(pn)
	gd.hideCancelButton()
	gd.showDialog()



# --------------------------------------------------------------- the run
def plan_slides(slides, typed, chosen, settings, raw_root, project, paused):
	"""Per slide: its region folder and the stages that can run on it (an
	input made by an earlier stage of this run counts as there). paused: the
	paused run being continued ({} for a new run): broken {slide: why}, done
	{slide: [stages]}, and stage 3's tables and settings used {slide: ...}."""
	keys, plan = [s[0] for s in chosen], []
	broken, done = paused.get("broken", {}), paused.get("done", {})
	for slide in slides:
		r = {"slide": slide, "name": os.path.basename(slide), "region": None, "todo": [],
		     "stages": {}, "excluded": "", "broken": broken.get(os.path.basename(slide), "")}
		csv_path, _lv, row = layout_csv_row(slide)
		if row is not None and row.get("include", "").lower() in ("no", "n", "0", "false"):
			r["excluded"] = csv_path
			plan.append(r)
			continue
		region, why = os.path.isdir(slide) and region_of(slide, typed) or (
		    None, "its folder does not exist yet (the slide is only in the raw data)")
		r["region"], made = region, set()
		for key, script, name, reads, outf in chosen:
			if key in done.get(r["name"], []):
				r["stages"][key] = ("done before the pause", "", key == "3" and paused.get(
				    "used", {}).get(r["name"]) or "", [], key == "3" and list(paused.get(
				    "tables", {}).get(r["name"]) or []) or [])
				made.add(MAKES[key])
				continue
			miss = r["broken"] or key != "1" and region is None and why or missing_input(
			    key, slide, region, made, settings, raw_root, project, "2b" not in keys)
			if miss:
				r["stages"][key] = ("skipped", miss, "", [], [])
			else:
				r["todo"].append(key)
				made.add(MAKES[key])
		plan.append(r)
	return plan


def outcomes(r, keys):
	"""'2c, 3, 4 skipped (why)': stages with the same outcome together."""
	out = []
	for k in keys:
		st = r["stages"][k][:2]
		if out and out[-1][1] == st:
			out[-1][0].append(k)
		else:
			out.append(([k], st))
	return "; ".join(["%s %s%s" % (", ".join(ks), s, d and " (%s)" % d or "") for ks, (s, d) in out])


def where(r):
	if not r["region"]:
		return "(no region folder)"
	return r["region"] == r["slide"] and "the slide folder" or os.path.basename(r["region"])


def check_lines(animal, typed, raw_animal, chosen, settings, project, plan, resumed):
	"""The runner's Check settings window ("!" lines: warnings)."""
	warn, out, regions, keys = [], [], {}, [s[0] for s in chosen]
	for r in plan:
		if r["excluded"]:
			continue
		skipped = [s[0] for s in chosen if r["stages"].get(s[0], ("done before the pause",))[0]
		           != "done before the pause"]
		if skipped:
			warn.append("!%s: %s" % (r["name"], outcomes(r, skipped)))
		if r["todo"] and r["region"]:
			regions.setdefault(where(r).lower(), (where(r), []))[1].append(r["name"])
	if len(regions) > 1:
		warn.append("!The region folders differ between slides: %s. Check that they hold "
		            "the same brain regions." % "; ".join(["%s (%s)" % (k, ", ".join(v))
		                                                   for k, v in sorted(regions.values())]))
	if "2c" in settings and not settings["2c"][0].get("overwrite"):
		for r in plan:
			maps = "2c" in r["todo"] and [n for n in has_files(layout_find(
			    r["slide"], r["region"], "probabilities")) if n.lower().endswith((".tif", ".tiff"))]
			if maps:
				warn.append("!%s: probabilities/ already holds %d map(s). With 'Overwrite "
				            "existing probability maps' off they are kept, and they may come "
				            "from another ilastik project." % (r["name"], len(maps)))
	for i, (key, script, name, reads, outf) in enumerate(chosen):
		v = outf and settings[key][0].get(outf)
		if v and v != MAKES[key] and [s for s in chosen[i + 1:] if MAKES[key] in s[3]]:
			warn.append("!%s writes to '%s/', but the later stages read '%s/'." % (name, v, MAKES[key]))
	excl = [r["name"] for r in plan if r["excluded"]]
	if resumed:
		out.append("Continuing the run paused on %s (at the break: %s%s), with its settings."
		           % (resumed.get("time"), resumed.get("break"), resumed.get("error") and
		              "; it ended there with an error: %s" % resumed["error"] or ""))
		before = [(r["name"], [k for k in keys if r["stages"].get(k, ("",))[0] ==
		                       "done before the pause"]) for r in plan]
		if [x for x in before if x[1]]:
			out.append("Done before the pause (not run again): %s" % "; ".join(
			    ["%s: %s" % (n, ", ".join(ks)) for n, ks in before if ks]))
	out += ["Animal folder: %s" % animal,
	        "Region: %s" % (typed or "(blank: each slide's only region folder)")]
	if "1" in settings:
		out.append("Raw data for stage 1: %s" % (raw_animal and "%s (its slide folders of the "
		           "same names)" % raw_animal or "in the slide folders"))
	out.append("Stages: %s" % ", ".join([s[2] for s in chosen]))
	if "2c" in settings:
		out.append("ilastik project (2c): %s" % (project == OWN_PROJECT and "each slide's own, "
		           "in its region folder" or project == ANIMAL_PROJECT and "the animal's, an .ilp in "
		           "the animal folder, used for every slide" or "%s (the animal's project, used for "
		           "every slide)" % project))
	bks = ("2a" in keys and "2b" in keys or resumed and resumed.get("break") == "review ROIs") and [
	    "before 2b, to review the ROIs (optional)"] or []
	bks += "2c" in keys and ("2b" in keys or project == ANIMAL_PROJECT) and [
	    "before 2c, to train ilastik%s" % ("2b" not in keys and " (only if the animal folder "
	                                       "does not hold exactly one trained project)" or "")] or []
	bks += (
	    "3" in keys and settings["3"][0].get("settingsSource", "").startswith("Tuned") and [
	        "before 3, to tune the counting parameters (only if no tuned values are found)"] or [])
	if bks:
		out.append("Breaks: %s. Every slide is brought to a break before it; the run waits there "
		           "while you work, and Stop here pauses it." % "; ".join(bks))
	other = [x for x in paused_regions(animal) if x.lower() != re.sub(
	    r"[^A-Za-z0-9]+", "_", typed or "").strip("_").lower() and not (x == "(blank)" and not typed)]
	if other:
		out.append("This animal also has a paused run for: %s (type that region to continue it)."
		           % ", ".join(other))
	out += ["", "Slides: %d found, %d to run%s" % (len(plan), len([r for r in plan if r["todo"]]),
	        excl and "; left out (include = no in experiment_layout.csv): " + ", ".join(excl) or "")]
	for r in plan:
		if not r["excluded"]:
			out.append("   %s -> %s: %s" % (r["name"], where(r), r["todo"] and "runs " +
			                                ", ".join(r["todo"]) or "nothing to run"))
	for key, script, name, reads, outf in chosen:
		out += ["", "%s, settings for every slide:" % name]
		out += ["   %s = %s" % (label, v) for label, v in settings[key][1]]
	out += ["", "Each slide is processed on its own, as when the stage runs on that slide: its "
	        "outputs go into its own folders (tifs/ in the slide folder, the rest in its region "
	        "folder), and its region folder gets a record of this run. Counts are not pooled."]
	if "3" in settings and WRITE_ANIMAL_TABLES:
		out.append("After stage 3 the animal folder gets particle_counts_all_slides_<region>.csv "
		           "and particle_counts_by_region_all_slides_<region>.csv: the tables of the "
		           "slides counted in this run, one after the other.")
	return warn + out


def record_files(dirs):
	"""The _run_*.txt parameter records in dirs and one level below."""
	out = set()
	for d in dirs:
		subs = [d] + [os.path.join(d, n) for n in (os.path.isdir(d) and os.listdir(d) or [])]
		for s in subs:
			for n in (os.path.isdir(s) and os.listdir(s) or []):
				if n.startswith("_run_") and n.endswith(".txt"):
					out.add(os.path.join(s, n))
	return out


def add_note(paths, text):
	"""Add the animal run to the parameter records a stage wrote."""
	for p in paths:
		try:
			fh = open(p, "a")
			fh.write(text)
			fh.close()
		except IOError:
			pass


def slide_record(r, ctx):
	d = r["region"] or (os.path.isdir(r["slide"]) and r["slide"])
	if not d:
		return None
	settings, chosen = ctx["settings"], ctx["chosen"]
	items = [("#Run for the animal as a whole", ""), ("Animal folder", ctx["animal"]),
	         ("Slides of this run", ctx["together"]), ("This slide", r["slide"]),
	         ("Region (its MBF folder)", "%s (used: %s)" % (ctx["typed"] or "(blank)", where(r)))]
	if ctx["resumed"]:
		items.append(("Continued from", "the run paused on %s at the break: %s"
		              % (ctx["resumed"].get("time"), ctx["resumed"].get("break"))))
	if "1" in settings:
		items.append(("Raw data top folder", ctx["raw_root"] or "(blank: raw files in the slide folder)"))
	if "2c" in settings:
		p = ctx.get("ilp") or ctx["project"]
		items.append(("ilastik project (2c)", p == OWN_PROJECT and "the slide's own, in its "
		              "region folder" or p == ANIMAL_PROJECT and "the animal's (none was used)"
		              or p + " (the animal's)"))
	if r["name"] in ctx["reviewed"]:
		items.append(("2a.i Review and Edit ROIs", "opened on this slide at the break before 2b "
		              "(its own record and rois/_roi_review_log.csv say what changed)"))
	items.append(("#What ran on this slide", ""))
	for key, script, name, reads, outf in chosen:
		st = r["stages"].get(key, ("not run", "", "", [], []))
		items.append((name, st[1] and "%s - %s" % (st[0], st[1]) or st[0]))
		if st[2]:
			items.append(("   counting settings used", st[2]))
		items += [("   warning", w) for w in st[3]]
	if ctx["paused"]:
		items.append(("Paused", "at the break: %s; stages left: %s" % (ctx["paused"], ", ".join(
		              ctx["left"]))))
	for key, script, name, reads, outf in chosen:
		items.append(("#Settings: " + name, ""))
		items += settings[key][1]
	return write_run_record(d, SCRIPT_NAME, SCRIPT_VERSION, items)


def phases_of(keys):
	"""The stages split where a break may come: before 2b, 2c and 3."""
	out = []
	for k in keys:
		if not out or k in ("2b", "2c", "3"):
			out.append([k])
		else:
			out[-1].append(k)
	return out


def review_break(ctx, slides):
	"""Before 2b: review the ROIs, slide by slide. "go" or "stop"."""
	todo = [r for r in slides if r["name"] not in ctx["reviewed"]]
	if not todo:
		return "go"
	save_pause(ctx, BREAK_NAMES["2b"])       # saved now: closing Fiji at the break keeps the run
	got = break_window("review ROIs", [
	    "2a has run (%d slide(s) ready for 2b). 2b clears everything outside the ROIs, so correct"
	    % len(slides), "any ROI outlines now, before 2b runs.", "",
	    "Slides to review: %s" % ", ".join([r["name"] for r in todo]),
	    ctx["reviewed"] and "Already reviewed: %s" % ", ".join(ctx["reviewed"]) or "",
	    "When 2a.i closes, its message mentions running 2b again: here 2b runs after the review."],
	    [REVIEW_NOW, REVIEW_SKIP], ok="OK")
	if got is None:
		return "stop"
	if got[0] != REVIEW_NOW:
		return "go"
	path = os.path.join(ctx["kdir"], "Batch", "2a.i_Review_and_Edit_ROIs.py")
	code = compile(script_text(path), path, "exec")
	for i, r in enumerate(todo):
		if i:
			nxt = "Review %s" % r["name"]
			got = break_window("review ROIs", ["2a.i was opened on: %s." % (", ".join(ctx["reviewed"])
			                                                                   or "none yet"),
			                                   "Next: %s (%d of %d)." % (r["name"], i + 1, len(todo))],
			                   [nxt, "Done reviewing: go on with 2b"], ok="OK")
			if got is None:
				return "stop"
			if got[0] != nxt:
				return "go"
		IJ.log("Reviewing the ROIs of %s (2a.i)" % r["slide"])
		why = review_slide(code, r["slide"], ctx["typed"], ctx["raw_root"])
		if why:
			IJ.log("  2a.i on %s did not open: %s" % (r["name"], why))
		else:
			ctx["reviewed"].append(r["name"])
			save_pause(ctx, BREAK_NAMES["2b"])
	return "go"


def ilastik_break(ctx, slides):
	"""Before 2c: the trained project to use (ctx["ilp"]). The run waits for
	training when 2b ran in this run or no trained project is found."""
	animal, mode, need, problem = ctx["animal"], ctx["project"], "2b" in ctx["keys"], ""
	fixed, shown = mode not in (ANIMAL_PROJECT, OWN_PROJECT), None
	while True:
		ilps = mode == ANIMAL_PROJECT and animal_projects(animal) or []
		trained = [p for p, t in ilps if t]
		lacking = mode == OWN_PROJECT and [r["name"] for r in slides
		                                   if not own_ilp(r["region"], r["slide"])] or []
		if not need and not problem:
			if fixed or (mode == OWN_PROJECT and len(lacking) < len(slides)) or (
			        len(ilps) == 1 and trained):
				ctx["ilp"] = fixed and mode or trained and trained[0] or OWN_PROJECT
				return "go"
		status = fixed and ["Project: %s" % mode] or mode == OWN_PROJECT and [
		    lacking and "Slides without a trained project in their region folder: %s (their 2c "
		    "is skipped)." % ", ".join(lacking) or "Every slide has a trained project in its "
		    "region folder."] or [ilps and "Found in the animal folder: %s." % ", ".join([
		        "%s (%s)" % (os.path.basename(p), t and "trained" or "no trained classifier yet")
		        for p, t in ilps]) or "No .ilp file is in the animal folder yet."]
		lines = (problem and ["NOT READY: " + problem, ""] or []) + [
		    need and "2b has run (%d slide(s) ready for 2c). Train the ilastik classifier now, then "
		    "press Continue to run 2c." % len(slides) or "2c needs a trained ilastik project.", "",
		    "1. In ilastik, make a Pixel Classification project and add training images from",
		    "   several of the slides, from their processed_bgsub_cleared/ folders:"] + [
		    "      %s: %s" % (r["name"], layout_find(r["slide"], r["region"], "processed_bgsub_cleared"))
		    for r in slides[:8]] + (len(slides) > 8 and ["      ... and %d more" % (len(slides) - 8)]
		                            or []) + [
		    "2. Label 1 must be the cells. Turn on Live Update and wait until the predictions appear.",
		    mode == OWN_PROJECT and "3. Save each slide's project in its region folder, then close "
		    "ilastik." or "3. Save the project in the animal folder, then close ilastik:",
		    mode != OWN_PROJECT and "      %s" % animal or "", ""] + status
		shown = len(ilps) > 1 and [os.path.basename(p) for p, t in ilps] or None
		save_pause(ctx, BREAK_NAMES["2c"])
		got = break_window("train ilastik", lines, project=shown)
		if got is None:
			return "stop"
		need, problem = False, ""
		if mode == ANIMAL_PROJECT:
			now = animal_projects(animal)
			if len(now) > 1 and [os.path.basename(p) for p, t in now] != shown:
				problem = ("there are %d .ilp files in the animal folder: choose the one to use."
				           % len(now))
				continue
			pick = got[1] and os.path.join(animal, got[1]) or now and now[0][0] or ""
			if pick and stored_classifier(pick):
				ctx["ilp"] = pick
				return "go"
			problem = pick and ("%s holds no trained classifier yet: in ilastik turn on Live "
			                    "Update, wait for the predictions, then save the project."
			                    % os.path.basename(pick)) or "no .ilp file is in the animal folder yet."
			continue
		if mode == OWN_PROJECT and not [r for r in slides if own_ilp(r["region"], r["slide"])]:
			problem = "no slide has a trained ilastik project in its region folder yet."
			continue
		ctx["ilp"] = mode
		return "go"


def tune_break(ctx, slides):
	"""Before 3, when stage 3 should use tuned values and none are found."""
	missing = [r for r in slides if not tuned_file(r["slide"], r["region"])]
	if not missing:
		return "go"
	have, total = experiment_maps(ctx["animal"], ctx["typed"])
	exp_csv = layout_csv_up(ctx["animal"])[0]
	mine = len([r for r in ctx["runs"] if r["region"] and [n for n in has_files(os.path.join(
	    r["region"], "probabilities")) if n.lower().endswith((".tif", ".tiff"))]])
	use_start = "Count with the values given at the start of the run"
	problem = ""
	while True:
		lines = (problem and ["NOT READY: " + problem, ""] or []) + [
		    "Stage 3 is set to use the tuned values of the experiment, and no tuned values for",
		    "%s were found (on %s)." % (where(missing[0]), ", ".join([r["name"] for r in missing])),
		    exp_csv and "Tune saves them in %s" % os.path.join(os.path.dirname(exp_csv),
		                                                     "counting_tuning") or
		    "No experiment_layout.csv was found above the animal folder: Tune needs it (run Map "
		    "Experiment Folders first).", "",
		    "Tune Counting Parameters draws sections from the whole experiment, and stage 3 uses",
		    "its values for every animal, so that all animals are counted the same way."]
		if total:
			lines.append("Slides with probability maps for this region: %d of %d in the experiment "
			             "(this animal: %d of %d)." % (have, total, mine, len(ctx["runs"])))
			if have < total:
				lines += ["Tuning now fits the values to the slides that have maps so far. To tune "
				          "on the whole", "experiment, press Stop here, make the maps of the other "
				          "animals, run Tune, then run", "this script on this animal again to "
				          "continue."]
		lines += ["", "To tune now: run Plugins > Kapur Lab Cell Counting > Tune Counting "
		          "Parameters (this window", "can stay open). Close Tune's windows before you press "
		          "Continue: windows that are", "open while stage 3 runs are closed."]
		save_pause(ctx, BREAK_NAMES["3"])
		got = break_window("tune counting parameters", lines,
		                   problem and ["Check again for tuned values", use_start] or None)
		if got is None:
			return "stop"
		missing = [r for r in slides if not tuned_file(r["slide"], r["region"])]
		if not missing or got[0] == use_start:
			return "go"
		problem = "no tuned values were found yet. Check that Tune finished and wrote them, or count "\
		          "with the values given at the start of the run."


def before_phase(first, ctx, slides):
	"""The break before a part, if it applies: "go" or "stop". The run is saved
	first, as paused before this part (a break saves its own name when its
	window opens), so closing Fiji or a crash keeps it."""
	if not slides:
		return "go"
	ctx["watch"].listen = False
	if first in BREAK_NAMES:
		save_pause(ctx, "before %s" % ctx["names"][first])
	brk = first == "2b" and ("2a" in ctx["keys"] or (ctx["resumed"] or {}).get(
	    "break") == BREAK_NAMES["2b"]) and review_break or first == "2c" and ilastik_break or \
	    first == "3" and ctx["settings"]["3"][0].get("settingsSource", "").startswith(
	        "Tuned") and tune_break or None
	return brk and brk(ctx, slides) or "go"


BREAK_NAMES = {"2b": "review ROIs", "2c": "train ilastik", "3": "tune counting parameters"}


def save_pause(ctx, why):
	"""Save the run as paused here (why: the break, or "before <stage>"), with
	the stages left (ctx["left"]); for the slides, the stages done and stage
	3's tables and settings used; the ilastik project 2c uses, once chosen."""
	done, tables = {}, {}
	for r in ctx["plan"]:
		ks = [k for k in ctx["keys"] if r["stages"].get(k, ("",))[0].startswith("done")]
		if ks:
			done[r["name"]] = ks
		if "3" in ks:
			tables[r["name"]] = list(r["stages"]["3"][4])
	ctx["at"] = why
	ctx["unsaved"] = not save_state(ctx["animal"], ctx["typed"], {
	    "time": time.strftime("%Y-%m-%d %H:%M"), "region": ctx["typed"], "break": why,
	    "error": ctx.get("error", ""), "raw_root": ctx["raw_root"], "stages": ctx["left"],
	    "project": ctx["project"], "ilp": ctx.get("ilp") or "", "slides": ctx["together"],
	    "reviewed": ctx["reviewed"], "done": done, "tables": tables, "used": ctx["used"],
	    "settings": dict([(k, ctx["settings"][k]) for k in ctx["left"]]),
	    "broken": dict([(r["name"], r["broken"]) for r in ctx["plan"] if r["broken"]])})


def run_phase(phase, ctx):
	"""The stages of one part, slide by slide."""
	watch, names = ctx["watch"], ctx["names"]
	IJ.resetEscape()
	watch.esc, watch.listen = False, True
	for n, r in enumerate(ctx["runs"]):
		keys = [k for k in phase if k in r["todo"]]
		if not keys:
			continue
		if ctx["esc"] or ctx["fatal"]:
			for key in keys:
				r["stages"][key] = ("not run yet", ctx["esc"] and "the run was stopped with Esc" or
				                    "the run ended: " + ctx["fatal"], "", [], [])
			continue
		IJ.log("-" * 64)
		IJ.log("[%d/%d] %s" % (n + 1, len(ctx["runs"]), r["slide"]))
		made = set()
		for key in keys:
			wide = ctx["wide"].get(key)
			stop = ctx["esc"] and "the run was stopped with Esc" or ctx["fatal"] and \
			    "the run ended: " + ctx["fatal"]
			if stop and not (r["broken"] or wide):          # continued later
				r["stages"][key] = ("not run yet", stop, "", [], [])
				continue
			if r["broken"] or wide:
				r["stages"][key] = ("not run", r["broken"] or "it stopped on %s for the same "
				                    "reason" % wide[0], "", [], [])
				if wide and not r["broken"]:
					r["broken"] = "%s did not finish on this slide" % names[key]
				continue
			miss = missing_input(key, r["slide"], r["region"], made, ctx["settings"],
			                     ctx["raw_root"], ctx.get("ilp") or ctx["project"])
			if miss:
				r["stages"][key] = ("skipped", miss, "", [], [])
				continue
			if not os.path.isdir(r["slide"]):
				os.makedirs(r["slide"])
			dirs = [d for d in (r["region"], r["slide"]) if d]
			before = record_files(dirs)
			IJ.log("  %s ..." % names[key])
			res, err = run_stage(ctx["codes"][key], key, r["slide"], ctx["typed"],
			                     ctx["settings"][key][0], ctx["raw_root"],
			                     ctx.get("ilp") or ctx["project"], watch)
			if key == "3" and res[0].startswith("done") and "2c" in ctx["keys"] and \
			        not r["stages"].get("2c", ("",))[0].startswith("done"):
				w = ("2c made no maps on this slide in this run, so stage 3 counted the maps "
				     "that were already in probabilities/")
				res = ("done, with warnings", res[1] and res[1] + "; " + w or w, res[2],
				       res[3] + [w], res[4])
			r["stages"][key] = res
			IJ.log("  %s: %s%s" % (names[key], res[0], res[1] and " - " + res[1] or ""))
			add_note(record_files(dirs) - before, ctx["note"])
			if res[2]:
				ctx["used"][r["name"]] = res[2]
			ctx["fatal"] = err and res[1] or ctx["fatal"]
			ctx["esc"] = ctx["esc"] or watch.esc or IJ.escapePressed() or res[1] == "stopped with Esc"
			if res[0].startswith("done"):
				made.add(MAKES[key])
			elif not (err or res[1] == "stopped with Esc"):      # Esc / an error: run again later
				r["broken"] = "%s did not finish on this slide" % names[key]
				last = ctx["last_stop"].get(key)
				if res[0] == "stopped" and last and last[1] == res[1]:
					ctx["wide"][key] = last
				ctx["last_stop"][key] = (r["name"], res[1])
			System.gc()
	watch.listen = False


def resume_choice(state, animal):
	"""Continue the animal's paused run? "continue", "new" or None."""
	if "RUNNER_RESUME" in globals():          # the automated tests
		return RUNNER_RESUME
	from ij.gui import GenericDialog
	opts = ["Continue the paused run", "Start a new run with the stages ticked now"]
	gd = GenericDialog(SCRIPT_NAME + " - paused run")
	gd.addMessage("%s has a paused run:\n   paused on %s at the break: %s\n   stages left: %s\n"
	              "   region: %s\nContinue it with the settings of that run, or start a new run "
	              "(the paused run\nis then forgotten, once the new run starts)." % (
	                  os.path.basename(animal), state.get("time"), state.get("break"),
	                  ", ".join(state.get("stages", [])), state.get("region") or "(blank)"))
	gd.addRadioButtonGroup("", opts, 2, 1, opts[0])
	gd.showDialog()
	if gd.wasCanceled():
		return None
	return gd.getNextRadioButton() == opts[0] and "continue" or "new"


def main():
	IJ.resetEscape()
	kdir = stage_dir()
	if not kdir:
		IJ.error(SCRIPT_NAME, "The stage scripts (the Batch folder) were not found. Keep this "
		         "script in the Kapur Lab Cell Counting folder in Fiji's scripts/Plugins/ folder, "
		         "next to Batch/, and restart Fiji.")
		return
	animal = os.path.normpath(animalDir.getAbsolutePath())
	typed = (globals().get("regionName") or "").strip()
	raw_root = globals().get("rawRoot") and os.path.normpath(rawRoot.getAbsolutePath()) or ""
	chosen = [s for s in STAGES if globals().get("run" + s[0])]
	own = layout_regions(animal) + [d for d in LAYOUT_SLIDE_LEVEL + LAYOUT_REGION_SUBS
	                                if os.path.isdir(os.path.join(animal, d))]
	if own or layout_is_region(animal):
		IJ.error(SCRIPT_NAME, "%s\nlooks like a slide or region folder (it holds %s).\n\n"
		         "Choose the animal folder: the folder that holds the animal's slide folders."
		         % (animal, ", ".join(own) or "pipeline folders"))
		return
	resumed, state, forget = None, load_state(animal, typed), False
	if state:
		pick = resume_choice(state, animal)
		if pick is None:
			return
		if pick == "continue":
			resumed = state
			chosen = [s for s in STAGES if s[0] in state["stages"]]
			typed, raw_root = state.get("region") or u"", state.get("raw_root") or u""
		else:
			forget = True                  # once the new run starts
	if not chosen:
		IJ.error(SCRIPT_NAME, "Tick at least one stage to run.")
		return
	settings = {}
	for key, script, name, reads, outf in chosen:
		path = os.path.join(kdir, "Batch", script)
		if not os.path.isfile(path):
			IJ.error(SCRIPT_NAME, "Not found:\n%s" % path)
			return
		if resumed:                    # the paused run's settings; defaults for new fields
			use = [f for f in parse_fields(path) if f[0] not in GIVEN and f[0] not in FIXED.get(key, {})]
			saved = resumed["settings"][key][0]
			vals, shown = typed_values(key, use, {}), list(resumed["settings"][key][1])
			shown += [(f[2].strip() + " (new since the pause: its default)", shown_value(vals[f[0]]))
			          for f in use if f[0] not in saved]
			vals.update(saved)
			settings[key] = (vals, shown)
			continue
		got = ask_settings(key, name, parse_fields(path))
		if got is None:
			return
		settings[key] = got
	bad = []
	if "2b" in settings and settings["2b"][0].get("clearMode", "").startswith("union of ROIs I pick"):
		bad.append("2b: 'Clear outside...' is 'union of ROIs I pick from a list', which asks "
		           "for every image. For an animal run choose 'union of ALL ROIs in the set' "
		           "or 'one named ROI'.")
	if "4" in settings and not settings["4"][0].get("saveComposites"):
		bad.append("4: 'Save the composites to disk' is off. An animal run does not open the "
		           "composites on screen, so nothing would be made.")
	project = ""
	if "2c" in settings:
		# continuing: the project 2c used before the pause, once chosen
		project = resumed and (resumed.get("ilp") or resumed.get("project")) or choose_project(animal)
		if project is None:
			return
		if project not in (ANIMAL_PROJECT, OWN_PROJECT) and not os.path.isfile(project):
			bad.append("2c: %s\nwas not found. The paused run used it for 2c: put it back, or "
			           "start a new run." % project)
		elif project not in (ANIMAL_PROJECT, OWN_PROJECT) and not stored_classifier(project):
			bad.append("2c: %s\nholds no trained classifier. Open it in ilastik, turn on Live "
			           "Update, wait until the predictions appear, save it, and run this "
			           "again." % project)
	ft = "1" in settings and (settings["1"][0].get("fileType") or "").lower() or ""
	raw_animal = raw_root and layout_raw(animal, raw_root) or ""
	if raw_root and not raw_animal and "1" in settings:
		bad.append("The animal folder\n%s\nwas not found in the raw data top folder\n%s\n"
		           "The raw tree must repeat the folder names of this tree, at least from the "
		           "animal folder down (<raw top>/.../%s/<slide folder>/<raw files>)."
		           % (animal, raw_root, os.path.basename(animal)))
	if bad:
		IJ.error(SCRIPT_NAME, "\n\n".join(bad))
		return
	exts = tuple(set((".nd2", ".ims") + (ft and (ft,) or ())))
	slides = animal_slides(animal, raw_animal, exts)
	if not slides:
		IJ.error(SCRIPT_NAME, "No slide folders were found in\n%s%s\n\nA slide folder holds a "
		         "region (MBF) folder, pipeline folders (tifs, xml, rois, ...) or raw .nd2/.ims "
		         "files. Choose the folder of ONE animal: its subfolders are its slides."
		         % (animal, raw_animal and "\nor in\n%s" % raw_animal or ""))
		return
	plan = plan_slides(slides, typed, chosen, settings, raw_root, project, resumed or {})
	runs = [r for r in plan if r["todo"]]
	lines = check_lines(animal, typed, raw_animal, chosen, settings, project, plan, resumed)
	if not runs:
		IJ.error(SCRIPT_NAME, "Nothing can run on any slide of\n%s\n\n%s" % (animal, "\n".join(
		    [ln[1:] for ln in lines if ln.startswith("!")][:20]) or "All slides are left out."))
		return
	if not confirm_settings(SCRIPT_NAME, lines, CONFIRM_BEFORE_RUN):
		return
	if forget:
		forget_state(animal, typed)

	keys = [s[0] for s in chosen]
	together = resumed and resumed.get("slides") or ", ".join([r["name"] for r in runs])
	ctx = {"kdir": kdir, "animal": animal, "typed": typed, "raw_root": raw_root,
	       "chosen": chosen, "keys": keys, "settings": settings, "project": project,
	       "runs": runs, "plan": plan, "together": together, "resumed": resumed,
	       "reviewed": resumed and resumed["reviewed"] or [],
	       "names": dict([(s[0], s[2]) for s in STAGES]), "esc": False, "fatal": "",
	       "wide": {}, "last_stop": {}, "used": dict(resumed and resumed.get("used") or {}),
	       "paused": "", "left": [],
	       "codes": dict([(s[0], stage_code(os.path.join(kdir, "Batch", s[1]))) for s in chosen])}
	ctx["note"] = ("\n\n[Run Stages for an Animal]\nThis stage ran on every slide of the animal, "
	               "with the same settings for all of them.\nanimal folder = %s\nslides of this "
	               "run = %s\nregion = %s\nThe run is recorded in _run_Run_Stages_for_an_Animal_"
	               "*.txt in the region folder.\n" % (b(animal), b(together), b(typed or "(blank)")))
	watch = ctx["watch"] = Watch()
	t = Thread(watch, "Run Stages for an Animal: messages")
	t.setDaemon(True)
	t.start()
	esc_keys = EscKey(watch)
	Toolkit.getDefaultToolkit().addAWTEventListener(esc_keys, AWTEvent.KEY_EVENT_MASK)
	IJ.log("=" * 64)
	IJ.log("%s: %s (%d slides), stages %s" % (SCRIPT_NAME, animal, len(runs), ", ".join(keys)))
	phases = phases_of(keys)
	try:
		for i, phase in enumerate(phases):
			ready = [r for r in runs if phase[0] in r["todo"] and not r["broken"]]
			if not (ctx["esc"] or ctx["fatal"]):
				ctx["left"] = [k for p in phases[i:] for k in p]
				try:
					act = before_phase(phase[0], ctx, ready)
				except (ANY_ERROR, Throwable), e:
					IJ.log("ERROR at the break: %s" % e)
					act, ctx["error"] = "stop", u"%s" % e
				if act == "stop":
					ctx["paused"] = ctx.get("at") or "before %s" % ctx["names"][phase[0]]
					IJ.log("Paused at the break: %s" % ctx["paused"])
					break
				ctx["left"] = []
			run_phase(phase, ctx)
			if ctx["esc"] or ctx["fatal"]:
				ctx["left"] = ctx["left"] or [k for p in phases[i:] for k in p]
				break
	finally:
		watch.alive = False
		Toolkit.getDefaultToolkit().removeAWTEventListener(esc_keys)
	for r in runs:            # stages the run did not reach
		for k in ctx["left"]:
			if k in r["todo"] and k not in r["stages"]:
				r["stages"][k] = ("not run yet", ctx["paused"] and "paused at the break" or
				                  ctx["esc"] and "the run was stopped with Esc" or
				                  "the run ended after an error", "", [], [])
	# left: the stages some slide still has to do (none: the run is complete)
	ctx["left"] = [k for k in ctx["left"] if [r for r in runs if k in r["todo"] and not r["broken"]
	               and not r["stages"].get(k, ("",))[0].startswith("done")]]
	if ctx["esc"] and not ctx["left"]:
		IJ.log("Esc was pressed, but every stage had finished on every slide.")
	for r in runs:
		if [k for k in r["todo"] if not r["stages"].get(k, ("not run",))[0].startswith("not run")]:
			slide_record(r, ctx)
	if ctx["left"]:
		save_pause(ctx, ctx["paused"] or (ctx["esc"] and "stopped with Esc") or
		           "stopped after an error")
	else:
		forget_state(animal, typed)
	report(ctx, plan)


def report(ctx, plan):
	animal, runs, chosen, settings = ctx["animal"], ctx["runs"], ctx["chosen"], ctx["settings"]
	tables, notes = [], []
	regions = sorted(set([where(r) for r in runs if r["region"]]))
	if len(regions) > 1:
		notes.append("The region folders differ between slides (%s). Check that they hold the "
		             "same brain regions." % ", ".join(regions))
	if "3" in settings and WRITE_ANIMAL_TABLES:
		tag = re.sub(r"[^A-Za-z0-9]+", "_", ctx["typed"] or len(regions) == 1 and regions[0] !=
		             "the slide folder" and regions[0] or len(regions) > 1 and "several regions"
		             or "slides")
		try:
			tables = animal_tables(animal, plan, tag.strip("_") or "slides")
		except ANY_ERROR, e:
			notes.append("The combined tables could not be written: %s" % e)
	srcs = {}
	for k, v in sorted(ctx["used"].items(), key=lambda x: natural(x[0])):
		srcs.setdefault(v, []).append(k)
	if len(srcs) > 1:
		notes.append("Stage 3 counted the slides with different settings, so their counts are "
		             "not comparable: %s" % "; ".join(["%s: %s" % (", ".join(v), k)
		                                              for k, v in sorted(srcs.items())]))
	dialog = [k for k, v in ctx["used"].items() if v == "the values in the dialog"]
	if dialog and settings.get("3", ({},))[0].get("settingsSource", "").startswith("Tuned"):
		notes.append("Stage 3 was set to the tuned values, but none were found, so %s counted "
		             "with the values given at the start of the run." % ", ".join(sorted(dialog, key=natural)))
	if ctx.get("ilp"):
		notes.append("ilastik project used by 2c: %s" % (ctx["ilp"] == OWN_PROJECT and
		             "each slide's own, in its region folder" or ctx["ilp"]))
	carried = [r["name"] for r in plan if r["broken"] and not r["todo"] and not r["excluded"]]
	if carried:
		notes.append("Not continued, as a stage did not finish on them before the pause: %s."
		             % ", ".join(carried))
	if ctx.get("error"):
		notes.append("The break ended with an error: %s" % ctx["error"])
	if ctx["fatal"]:
		notes.append("The run ended after %s.%s" % (ctx["fatal"], "OutOfMemory" in ctx["fatal"]
		             and " Give Fiji more memory (Edit > Options > Memory & Threads), restart "
		             "it and run again." or ""))
	ran = [r for r in runs if [k for k in r["todo"] if not r["stages"].get(
	    k, ("not run",))[0].startswith("not run")]]
	not_done = [r for r in plan if not r["excluded"] and [k for k in r["stages"] if r["stages"][
	    k][0] not in ("done", "not run yet", "done before the pause")]]
	title = (ctx["esc"] or ctx["fatal"]) and ctx["left"] and "Animal run STOPPED" or \
	    ctx["paused"] and ctx["left"] and "Animal run paused%s (break: %s)" % (
	        ctx.get("error") and " after an error" or "", ctx["paused"]) or (not_done or [
	        x for x in notes if not x.startswith("ilastik project used")]) and \
	    "Animal run complete - with problems" or "Animal run complete"
	body = ["Animal: %s" % animal, "Region: %s" % (ctx["typed"] or "(blank)"),
	        "Slides run: %d of %d found" % (len(ran), len(plan)), ""]
	for r in plan:
		if r["excluded"]:
			body.append("%s: left out (include = no in %s)" % (r["name"], r["excluded"]))
			continue
		body.append("%s: %s" % (r["name"], outcomes(r, [s[0] for s in chosen if s[0] in r["stages"]])))
	body += notes and [""] + ["NOTE: " + x for x in notes] or []
	if tables:
		body += ["", "Combined tables of the slides counted in this run (animal folder):"] + \
		    ["   " + os.path.basename(p) for p in tables]
	body += ["", "Each slide's record of this run: _run_%s_<time>.txt in its region folder."
	         % SCRIPT_NAME]
	if ctx["left"]:
		body.append("%s Stages left: %s. %s" % (ctx["paused"] and "Paused at the break: %s." %
		            ctx["paused"] or ctx["esc"] and "Stopped with Esc." or "Stopped after an error.",
		            ", ".join(ctx["left"]), ctx.get("unsaved") and "The paused run could not be "
		            "saved (see the Log), so it cannot be continued: run the stages left as a new "
		            "run." or "To continue, run this script on this animal again and choose "
		            "'Continue the paused run'."))
	IJ.log("=" * 64)
	IJ.log(title)
	for x in body:
		IJ.log(x)
	show_summary(title, body)


main()
