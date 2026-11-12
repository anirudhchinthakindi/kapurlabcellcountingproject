# Set_Up_Slide_Folders.py
#
# Fiji / ImageJ Jython script - Kapur Lab Cell Counting suite, set-up tool.
#
# Builds the folder layout for one analysed region inside every slide
# folder of a dataset, in one run. In each slide folder it makes a folder
# named "<region> MBF" (e.g. "hippocampus MBF") for that region's work, and
# sorts the pipeline subfolders into two places (both lists can be changed
# in the dialog):
#
#   slide1 and tnc/                     the slide folder
#       hippocampus MBF/                this region's folder
#           xml/  rois/  processed_bgsub_cleared/  probabilities/
#           particle_counts/
#       tifs/  jpx/                     shared by every region of the slide
#       Region0000_..._Seq0000.nd2 ...  raw files stay where they are
#
# tifs/ and jpx/ hold the converted images and NeuroInfo stacks, which do
# not depend on the region, so every region's MBF folder on a slide uses the
# same ones. Run the tool once per region to give a slide one MBF folder per
# region ("hippocampus MBF", "PAG MBF", ...).
#
# How the other scripts fit this layout (their default output locations):
#   1 Convert to Tif run on the slide folder itself (raw files directly in
#     it, and an MBF folder made by this tool) makes tifs/ inside the slide
#     folder; run on an nd2/ folder it makes tifs/ next to nd2/.
#   2a run on "<region> MBF/xml" makes rois/ in the MBF folder.
#   2b (tifs/ + "<region> MBF/rois") makes processed_bgsub_cleared/ next to
#     rois/, in the MBF folder.
#   ilastik: export into "<region> MBF/probabilities".
#   3 makes particle_counts/ in the MBF folder; 0 and 4 put their output in
#     the MBF folder when their input sits there, or when the slide folder
#     holds exactly one MBF folder and no region subfolders of its own.
#   The slide-folder check in 2b, 3 and 4 treats a "... MBF" folder as part
#   of its slide, and warns when inputs come from two regions' MBF folders.
#
# Existing subfolders in the wrong place (for example rois/ directly in the
# slide folder, from the older layout) are MOVED to where they belong when
# "Move them to where they belong" is chosen. A move is a rename on the
# same disk: nothing is copied or deleted, and the parameter record lists
# every move (from -> to) so it can be undone. A folder is never moved onto
# one that already exists; such a clash is reported and both are left.
#
# Raw files (.nd2 / .ims) stay in the slide folder by default. You can
# instead link them into an nd2/ folder (a hard link is a second name for
# the same file: no extra space, and nothing in the pipeline edits it) or
# copy them there. nd2/ goes in the slide folder unless you list "nd2"
# among the MBF subfolders. The original raw files are never moved,
# changed or deleted, and neither is a subfolder that holds them (such as
# an older layout's nd2/): it is left where it is and reported.
#
# Menu  : Plugins > Kapur Lab Cell Counting > Set Up Slide Folders
# Reads : the dataset folder you pick, searched at every depth (it can also
#         be a single slide folder). A slide folder is a folder that holds
#         raw files of the chosen type (directly, or in an nd2/ or ims/
#         subfolder), or that already holds one of the listed subfolders or
#         a "... MBF" folder with pipeline subfolders in it (a folder such
#         as "MBF exports" with none does not count). Its name does not
#         matter ("slide1 and tnc", "tnc", "NECAB1" ...); the optional name
#         field narrows it. A folder whose only sign is a listed subfolder
#         (a stray tifs/) is searched instead when slide folders lie below
#         it, and reported. The search does not go inside a slide folder,
#         an MBF folder or a pipeline subfolder. Picking an MBF folder or a
#         pipeline subfolder (or a folder inside one) stops with an error.
# Writes: the MBF folders and subfolders, moves and links as planned, and a
#         parameter record _run_Set_Up_Slide_Folders_<time>.txt in the
#         dataset folder. Running it again is safe: what is already in place
#         is left alone. Slides marked include = no in experiment_layout.csv
#         (Map Experiment Folders) are left alone and listed in the preview.
#
# Before anything is changed, the Check settings window shows a preview:
# the folder tree of two slide folders (those with the most moves and
# clashes) as it will look after the run (new, moved and existing folders
# marked), the totals for the whole dataset, and warnings (clashes, folders
# it skipped). Press Run to go ahead or Cancel to change nothing.
#
# Usage: Plugins > Kapur Lab Cell Counting > Set Up Slide Folders, or open
# this file in the Script Editor (File > New > Script..., or Plugins >
# Scripting > Script Editor) with Language = Python (Jython) and press Run.

#@ File    (label="Dataset folder (searched at every depth for slide folders)", style="directory") datasetDir
#@ String  (label="Region being analysed (names the folder, e.g. hippocampus)", value="") regionName
#@ String  (label="Added after the region name", value=" MBF") folderSuffix
#@ String  (label="Subfolders inside the region's MBF folder", value="xml, rois, processed_bgsub_cleared, probabilities, particle_counts") insideList
#@ String  (label="Subfolders directly in the slide folder", value="tifs, jpx") outsideList
#@ String  (label="Existing subfolders in the wrong place", choices={"Move them to where they belong", "Leave them where they are"}, style="listBox") moveMode
#@ String  (label="Raw files (.nd2 / .ims)", choices={"Leave them in the slide folder", "Link them into nd2/ (no extra disk space)", "Copy them into nd2/ (uses as much space again)"}, style="listBox") fileMode
#@ String  (label="Raw file type", choices={".nd2", ".ims", ".nd2 and .ims"}, style="radioButtonHorizontal") rawType
#@ String  (label="Only folders whose name starts with (blank = every slide folder)", value="", required=false) namePrefix
#@ File    (label="Raw data top folder (the tree with the .nd2/.ims files; its slide folders are mirrored here; blank = none)", style="directory", required=false) rawRoot

# =========================================================================
# ===  USER CONFIGURATION  ================================================
# =========================================================================
# Nothing below the END OF USER CONFIGURATION banner needs editing for
# routine use. The two subfolder lists are set in the dialog (comma-
# separated folder names).

# ---- RAW FILES ----
RAW_TYPES = {".nd2": [".nd2"], ".ims": [".ims"], ".nd2 and .ims": [".nd2", ".ims"]}
# Subfolder names that hold raw files in the protocol layout. A folder with
# raw files in one of these counts as a slide folder.
RAW_FOLDER_NAMES = ["nd2", "ims"]
# Name of the folder raw files are linked or copied into.
RAW_SUBFOLDER = "nd2"

# ---- FOLDERS NEVER SEARCHED ----
# Folders the pipeline makes. The search never goes inside them, nor inside
# a "... MBF" region folder (named so, and holding one of these or a listed
# subfolder), nor inside a slide folder.
PIPELINE_FOLDER_NAMES = ["nd2", "ims", "tifs", "jpx", "xml", "rois",
                         "processed_bgsub_cleared", "probabilities",
                         "particle_counts", "optimization",
                         "pipeline_composites", "thresholded", "watershed",
                         "QC", "particle_rois"]

# Name matching for "Only folders whose name starts with" ignores case.
CASE_INSENSITIVE_NAMES = True

# ---- PREVIEW ----
PREVIEW_SLIDES = 2          # slide folders drawn as a tree in the preview

# ---- SAFETY CHECKS ----
# Show the Check settings window (with the preview) before anything is
# changed. False skips it.
CONFIRM_BEFORE_RUN = True

# Write the parameter record into the dataset folder.
WRITE_PARAMETER_RECORD = True

# =========================================================================
# ===  END OF USER CONFIGURATION  =========================================
# =========================================================================

SCRIPT_NAME = "Set_Up_Slide_Folders"
SCRIPT_VERSION = "2.0"

import os
import re
import sys
from ij import IJ
from java.lang import Exception as JavaException

MOVE = (moveMode == "Move them to where they belong")
MODE_LEAVE = "Leave them in the slide folder"
MODE_LINK = "Link them into nd2/ (no extra disk space)"
MODE_COPY = "Copy them into nd2/ (uses as much space again)"
RAW_EXTENSIONS = RAW_TYPES[rawType]
RAW_TEXT = " / ".join(RAW_EXTENSIONS)
MBF_WORD = re.compile(r"(^|[^A-Za-z0-9])MBF([^A-Za-z0-9]|$)", re.IGNORECASE)


# ---- SHARED: errors -- keep identical ----
class StepError(Exception):
	"""A per-file failure with a message already written for a human."""
	pass
# ---- END SHARED: errors ----


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

# ---------------------------------------------------------------- helpers
def split_list(text):
	"""'xml, rois ,probabilities' -> ['xml', 'rois', 'probabilities']."""
	out = []
	for part in (text or "").split(","):
		p = part.strip().strip("/").strip()
		if p and p.lower() not in [o.lower() for o in out]:
			out.append(p)
	return out


def lower_in(name, names):
	return name.lower() in [n.lower() for n in names]


def raw_files(folder):
	out = []
	try:
		names = sorted(os.listdir(folder))
	except OSError:
		return out
	for n in names:
		p = os.path.join(folder, n)
		if (not n.startswith(".") and os.path.isfile(p)
		        and os.path.splitext(n)[1].lower() in RAW_EXTENSIONS):
			out.append(n)
	return out


def holds_raw(folder):
	"""True when folder (at any depth) holds a .nd2 or .ims file."""
	exts = []
	for v in RAW_TYPES.values():
		exts += v
	for cur, dirs, files in os.walk(folder):
		for n in files:
			if os.path.splitext(n)[1].lower() in exts:
				return True
	return False


def subdirs(folder):
	try:
		return sorted([d for d in os.listdir(folder) if not d.startswith(".")
		               and os.path.isdir(os.path.join(folder, d))])
	except OSError:
		return []


def is_mbf_name(name, suffix):
	"""Named like a region folder: the word MBF, or ending in the suffix as
	typed (with its leading space, so "slideNMBF" does not count)."""
	return bool(MBF_WORD.search(name)) or bool(
	    suffix.strip() and name.lower().endswith(suffix.lower()))


def is_mbf_folder(path, suffix, listed):
	"""A region folder: named "... MBF" AND holding a pipeline subfolder.

	The name alone is not enough: a folder such as "MBF exports" next to
	the slide folders would otherwise make the dataset folder a slide.
	"""
	if not is_mbf_name(os.path.basename(path), suffix):
		return False
	for d in subdirs(path):
		if lower_in(d, listed + PIPELINE_FOLDER_NAMES):
			return True
	return False


def name_ok(name, prefix):
	if not prefix:
		return True
	if CASE_INSENSITIVE_NAMES:
		return name.lower().startswith(prefix.lower())
	return name.startswith(prefix)


def slide_signs(folder, listed, suffix):
	"""Why folder counts as a slide folder ([] = it does not)."""
	why = []
	raws = raw_files(folder)
	if raws:
		why.append("%d %s file(s)" % (len(raws), RAW_TEXT))
	for d in subdirs(folder):
		if lower_in(d, RAW_FOLDER_NAMES) and raw_files(os.path.join(folder, d)):
			why.append("raw files in %s/" % d)
		elif lower_in(d, listed):
			why.append("%s/" % d)
		elif is_mbf_folder(os.path.join(folder, d), suffix, listed):
			why.append("%s/" % d)
	return why


def strong_signs(why):
	"""Raw files or a region folder: signs that cannot be a stray folder."""
	return [w for w in why if "file(s)" in w or MBF_WORD.search(w)
	        or w.startswith("raw files")]


def slide_below(folder, listed, suffix):
	"""True when a folder at any depth below folder is clearly a slide
	(raw files or a region folder). Pipeline and MBF folders are not
	searched."""
	never = PIPELINE_FOLDER_NAMES + listed
	for cur, dirs, files in os.walk(folder):
		dirs[:] = [d for d in dirs if not d.startswith(".")
		           and not lower_in(d, never)
		           and not is_mbf_folder(os.path.join(cur, d), suffix, listed)]
		if cur != folder and strong_signs(slide_signs(cur, listed, suffix)):
			return True
	return False


def find_slides(root, prefix, listed, suffix, strays):
	"""(slides, skipped): lists of (folder, reasons).

	A folder whose only sign is a listed subfolder (e.g. a stray tifs/ in an
	animal folder, or a pooled probabilities/ in the dataset folder) is not
	a slide when a folder at any depth below it is clearly a slide (raw
	files or a region folder): it is reported in strays and searched
	further, so the real slides below are found.
	"""
	slides, skipped = [], []
	never = PIPELINE_FOLDER_NAMES + listed
	for cur, dirs, files in os.walk(root):
		why = slide_signs(cur, listed, suffix)
		if why and not strong_signs(why) and slide_below(cur, listed, suffix):
			strays.append((cur, why))
			why = []
		if why:
			dirs[:] = []                    # never search inside a slide
			if name_ok(os.path.basename(cur), prefix):
				slides.append((cur, why))
			else:
				skipped.append((cur, why))
			continue
		dirs[:] = sorted([d for d in dirs if not d.startswith(".")
		                  and not lower_in(d, never)
		                  and not is_mbf_folder(os.path.join(cur, d), suffix, listed)])
	empty_slides(root, prefix, listed, suffix, slides, skipped)
	return slides, skipped


def empty_slides(root, prefix, listed, suffix, slides, skipped):
	"""Add empty slide folders (no images copied in yet): a folder with no
	subfolders and no files (hidden files such as .DS_Store aside), at the
	same depth as slide folders already found, named with the word "slide"
	or next to a slide folder already found."""
	found = [s for s, _w in slides + skipped]
	if not found:
		return
	rel = lambda f: len(os.path.relpath(f, root).split(os.sep))
	depths = set([rel(s) for s in found])
	parents = set([os.path.dirname(s) for s in found])
	never = PIPELINE_FOLDER_NAMES + listed
	for cur, dirs, files in os.walk(root):
		kids = [d for d in dirs if not d.startswith(".")]
		dirs[:] = sorted([d for d in kids if not lower_in(d, never)
		                  and os.path.join(cur, d) not in found
		                  and not is_mbf_folder(os.path.join(cur, d), suffix, listed)])
		if cur == root or kids or [f for f in files if not f.startswith(".")]:
			continue
		name = os.path.basename(cur)
		if rel(cur) in depths and ("slide" in name.lower()
		                           or os.path.dirname(cur) in parents):
			why = ["empty slide folder (no images yet)"]
			(slides if name_ok(name, prefix) else skipped).append((cur, why))
	slides.sort()
	skipped.sort()


def existing_problem(src, dst):
	"""None when dst (already in nd2/) is src or a full copy of it."""
	try:
		if os.path.samefile(src, dst):
			return None
	except (OSError, AttributeError):
		pass
	try:
		a, b = os.path.getsize(src), os.path.getsize(dst)
	except OSError, e:
		return "already exists but its size could not be read (%s); kept it" % e
	if a == b:
		return None
	return ("already exists with a different size (%d bytes, the original has "
	        "%d): a copy cut short, or another file of the same name. Kept it; "
	        "delete it and run again to replace it" % (b, a))


def put_file(src, dst, mode):
	"""Returns 'hard link', 'symbolic link' or 'copy'; raises StepError."""
	from java.nio.file import Paths, Files, StandardCopyOption
	s, d = Paths.get(src), Paths.get(dst)
	if mode == MODE_COPY:
		# Copy under a temporary name, then rename, so an interrupted copy
		# never has the final name.
		part = Paths.get(dst + ".part")
		try:
			Files.copy(s, part, [StandardCopyOption.COPY_ATTRIBUTES,
			                     StandardCopyOption.REPLACE_EXISTING])
			try:
				Files.move(part, d, [StandardCopyOption.ATOMIC_MOVE])
			except (Exception, JavaException):
				Files.move(part, d, [])
			return "copy"
		except (Exception, JavaException), e:
			try:
				Files.deleteIfExists(part)
			except (Exception, JavaException):
				pass
			raise StepError("could not copy: %s" % e)
	try:
		Files.createLink(d, s)
		return "hard link"
	except (Exception, JavaException), e1:
		try:
			Files.createSymbolicLink(d, s)
			return "symbolic link"
		except (Exception, JavaException):
			raise StepError("this disk allows neither a hard link nor a "
			                "symbolic link (%s). Run again with 'Copy'." % e1)


def short(path, root):
	rel = os.path.relpath(path, root)
	return rel if rel != "." else os.path.basename(root)


# ------------------------------------------------------------------ plan
def plan_slide(slide, mbf_name, inside, outside, raw_dir_inside):
	"""Everything this run would do in one slide folder, nothing done yet.

	Returns a dict: folders = [(path, state, note)] where state is one of
	'exists', 'new', 'move', 'clash', 'left'; moves = [(src, dst)];
	raws = raw file names; raw_dir = where they go (or None).
	"""
	mbf = os.path.join(slide, mbf_name)
	p = {"slide": slide, "mbf": mbf, "folders": [], "moves": [], "clashes": [],
	     "left_in_slide": []}
	p["mbf_state"] = "exists" if os.path.isdir(mbf) else "new"
	if os.path.exists(mbf) and not os.path.isdir(mbf):
		p["clashes"].append("a FILE named '%s' is where the MBF folder goes" % mbf_name)
		p["mbf_state"] = "clash"

	def place(name, home, other, other_label):
		dst = os.path.join(home, name)
		src = os.path.join(other, name)
		here = os.path.exists(dst)
		there = os.path.isdir(src)
		if here and not os.path.isdir(dst):
			p["clashes"].append("a FILE named '%s' is where the %s/ folder goes" % (dst, name))
			return (dst, "clash", "a file is in the way")
		if here and there:
			p["clashes"].append("%s/ is in both %s and the place it belongs; "
			                    "both were left as they are" % (name, other_label))
			return (dst, "clash", "also in %s; left both" % other_label)
		if here:
			return (dst, "exists", "")
		if there and MOVE and holds_raw(src):
			p["clashes"].append("%s/ in %s holds raw files, which are never moved; "
			                    "left it there" % (name, other_label))
			return (src, "left", "holds raw files, never moved")
		if there and MOVE:
			p["moves"].append((src, dst))
			return (dst, "move", "from %s" % other_label)
		if there and home == mbf and not lower_in(name, RAW_FOLDER_NAMES):
			# The region still gets its own folder; the one in the slide
			# folder stays as it is (and is not used for this region).
			p["left_in_slide"].append(name)
			return (dst, "new", "the %s/ in the slide folder is left as it is" % name)
		if there:
			return (src, "left", "left in %s (move turned off)" % other_label)
		return (dst, "new", "")

	for name in inside:
		p["folders"].append(("in", name, place(name, mbf, slide, "the slide folder")))
	for name in outside:
		p["folders"].append(("out", name, place(name, slide, mbf, "the MBF folder")))

	raws = raw_files(slide)
	p["raws"] = raws
	p["raw_dir"] = None
	if fileMode != MODE_LEAVE and raws:
		p["raw_dir"] = os.path.join(mbf if raw_dir_inside else slide, RAW_SUBFOLDER)
	other = [d for d in subdirs(slide) if d != mbf_name
	         and not lower_in(d, inside + outside)
	         and not (p["raw_dir"] and d == RAW_SUBFOLDER)]
	p["other"] = other
	return p


MARK = {"exists": "already there", "new": "NEW", "move": "MOVED here",
        "clash": "CLASH", "left": "left where it is"}


def tree_lines(p, root):
	"""The slide folder as it will look after the run."""
	in_mbf, in_slide = [], []
	for side, name, (path, state, note) in p["folders"]:
		if p["raw_dir"] and path == p["raw_dir"] and state in ("new", "exists"):
			continue                        # drawn once, with the raw files
		where_mbf = (os.path.dirname(path) == p["mbf"])
		sep = " " if state == "move" else "; "
		entry = "%s/   [%s%s]" % (name, MARK[state], (sep + note) if note else "")
		(in_mbf if where_mbf else in_slide).append(entry)
	if p["raw_dir"]:
		entry = "%s/   [%s; %d %s file(s) %s]" % (
		    RAW_SUBFOLDER, MARK["exists" if os.path.isdir(p["raw_dir"]) else "new"],
		    len(p["raws"]), RAW_TEXT,
		    "linked" if fileMode == MODE_LINK else "copied")
		(in_mbf if os.path.dirname(p["raw_dir"]) == p["mbf"] else in_slide).append(entry)
	out = ["%s/" % short(p["slide"], root),
	       "   |-- %s/   [%s]" % (os.path.basename(p["mbf"]), MARK[p["mbf_state"]])]
	out += ["   |      |-- " + e for e in in_mbf]
	out += ["   |-- " + e for e in in_slide]
	if p["raws"]:
		out.append("   |-- %s ... (%d %s file(s), stay here)"
		           % (p["raws"][0], len(p["raws"]), RAW_TEXT))
	if p["other"]:
		out.append("   |-- also here, not touched: %s"
		           % ", ".join([o + "/" for o in p["other"][:6]]
		                       + (["..."] if len(p["other"]) > 6 else [])))
	return out


# ------------------------------------------------------------------ main
def main():
	root = datasetDir.getAbsolutePath()
	region = (regionName or "").strip()
	suffix = folderSuffix or ""
	prefix = (namePrefix or "").strip()
	inside = split_list(insideList)
	outside = split_list(outsideList)
	if not os.path.isdir(root):
		IJ.error(SCRIPT_NAME, "The dataset folder does not exist:\n%s" % root)
		return
	mbf_name = (region + suffix).strip()
	problems = []
	if not region:
		problems.append("'Region being analysed' is blank. Type the region "
		                "this folder is for (e.g. hippocampus); the folder is "
		                "named '<region>%s'." % suffix)
	for what, txt in (("region name", region), ("text added after the region name", suffix)):
		if any(c in txt for c in '\\/:*?"<>|'):
			problems.append("The %s '%s' holds a character that cannot be used in "
			                "a folder name (\\ / : * ? \" < > |)." % (what, txt))
	for what, lst in (("inside the MBF folder", inside), ("in the slide folder", outside)):
		for n in lst:
			if any(c in n for c in '\\/:*?"<>|') or n in (".", ".."):
				problems.append("'%s' (subfolders %s) is not a usable folder name." % (n, what))
	both = [n for n in inside if lower_in(n, outside)]
	if both:
		problems.append("These subfolders are in both lists: %s. Each one goes "
		                "either inside the MBF folder or in the slide folder."
		                % ", ".join(both))
	if not inside:
		problems.append("'Subfolders inside the region's MBF folder' is empty.")
	for here in (os.path.normpath(root), os.path.dirname(os.path.normpath(root))):
		b_ = os.path.basename(here)
		if b_ and (is_mbf_folder(here, suffix, inside + outside)
		           or lower_in(b_, PIPELINE_FOLDER_NAMES)):
			problems.append("The folder you picked is (or is inside) '%s', which "
			                "is a region's MBF folder or a pipeline subfolder. "
			                "Pick the slide folder, or a folder above the slide "
			                "folders." % b_)
			break
	if region and lower_in(mbf_name, inside + outside):
		problems.append("The MBF folder name '%s' is also listed as a subfolder." % mbf_name)
	if problems:
		IJ.error(SCRIPT_NAME, "\n\n".join(problems))
		return
	raw_dir_inside = lower_in(RAW_SUBFOLDER, inside)
	listed = inside + outside

	strays = []
	slides, skipped = find_slides(root, prefix, listed, suffix, strays)
	# Raw files in their own tree: each of its folders holding raw files is a
	# slide, mirrored here (made when it is missing).
	raw_root = globals().get("rawRoot") and rawRoot.getAbsolutePath()
	raw_base, mirrored = raw_root and (layout_raw(root, raw_root, False) or raw_root), []
	have = set([os.path.normcase(os.path.normpath(s_)) for s_, _w in slides])
	for cur, dirs, files in (raw_base and os.walk(raw_base) or []):
		dirs[:] = sorted([d for d in dirs if not d.startswith(".")])
		if not [f for f in files if os.path.splitext(f)[1].lower() in RAW_EXTENSIONS]:
			continue
		dirs[:] = []            # a slide folder: not searched further
		rel = os.path.relpath(cur, raw_base)
		dst = os.path.normpath(rel == "." and root or os.path.join(root, rel))
		if os.path.normcase(dst) in have or not name_ok(os.path.basename(dst), prefix):
			continue
		have.add(os.path.normcase(dst))
		slides.append((dst, ["raw files in %s" % cur]))
		if not os.path.isdir(dst):
			mirrored.append(dst)
	slides.sort()
	if not slides:
		msg = ("No slide folders found under:\n%s\n\nA slide folder holds %s "
		       "files (directly or in nd2/ or ims/), or already holds one of "
		       "the listed subfolders or a '... MBF' folder." % (root, RAW_TEXT))
		if skipped:
			msg += ("\n\n%d such folder(s) were skipped because their names do "
			        "not start with '%s', e.g.:\n%s"
			        % (len(skipped), prefix,
			           "\n".join([short(f, root) for f, _ in skipped[:5]])))
		IJ.error(SCRIPT_NAME, msg)
		return

	# Slides marked include = no in experiment_layout.csv are left alone.
	excluded = [s for s, _w in slides if (layout_csv_row(s)[2] or {}).get(
	    "include", "").lower() in ("no", "n", "0", "false")]
	slides = [(s, w) for s, w in slides if s not in excluded]
	if not slides:
		IJ.error(SCRIPT_NAME, "Every slide folder found is marked include = no "
		         "in experiment_layout.csv, so there is nothing to set up.")
		return
	plans = [plan_slide(s, mbf_name, inside, outside, raw_dir_inside) for s, _w in slides]
	n_new = len([p for p in plans if p["mbf_state"] == "new"])
	n_there = len([p for p in plans if p["mbf_state"] == "exists"])
	n_moves = sum([len(p["moves"]) for p in plans])
	clashes = [(p, c) for p in plans for c in p["clashes"]]
	n_raw = sum([len(p["raws"]) for p in plans if p["raw_dir"]])

	lines = ["Dataset folder: %s" % root] + (raw_root and [
	         "Raw data top folder: %s (matching this folder: %s)" % (raw_root, raw_base)] or []) + [
	         "Slide folders found: %d%s" % (len(plans),
	             (" (name starts with '%s')" % prefix) if prefix else ""),
	         "Region folder in each: '%s'  (new in %d, already there in %d%s)"
	         % (mbf_name, n_new, n_there,
	            (", blocked by a file in %d" % (len(plans) - n_new - n_there))
	            if len(plans) - n_new - n_there else ""),
	         "Inside it: %s" % ", ".join([n + "/" for n in inside]),
	         "Directly in the slide folder: %s" % ", ".join([n + "/" for n in outside]),
	         "Existing subfolders in the wrong place: %s (%d move(s) planned)"
	         % (moveMode, n_moves),
	         "Raw files: %s (%s)" % (raw_root and "left in the raw tree" or fileMode, RAW_TEXT)
	         + ("; %d file(s) into %s/" % (n_raw, RAW_SUBFOLDER) if n_raw else ""),
	         "",
	         "PREVIEW: %d slide folder(s) after the run (most moves / clashes first)" % min(PREVIEW_SLIDES, len(plans))]
	# Preview the slides where the most happens (moves, clashes) first.
	shown = sorted(plans, key=lambda q: -(10 * len(q["clashes"]) + len(q["moves"])))
	for p in shown[:PREVIEW_SLIDES]:
		lines += tree_lines(p, root) + [""]
	lines.append("All slide folders: " + "; ".join(
	    [short(p["slide"], root) for p in plans[:12]])
	    + (" ... (%d in all, listed in the parameter record)" % len(plans)
	       if len(plans) > 12 else ""))
	if not MBF_WORD.search(mbf_name):
		lines.append("! The folder name '%s' does not contain the word MBF. The "
		             "other scripts recognise a region folder by that word (to "
		             "place their output and to check slide folders), so keep "
		             "MBF in the name." % mbf_name)
	for p in plans:
		others = [d for d in subdirs(p["slide"]) if d != mbf_name and MBF_WORD.search(d)]
		if p["moves"] and others:
			lines.append("! %s already has %s; the loose %s will be moved into "
			             "'%s'. Check that they belong to %s."
			             % (short(p["slide"], root), ", ".join(["'%s'" % o for o in others]),
			                ", ".join([os.path.basename(a) + "/" for a, _b in p["moves"]]),
			                mbf_name, region))
	left = [p for p in plans if p["left_in_slide"]]
	if left:
		lines.append("! In %d slide folder(s) (e.g. %s), %s are directly in the slide folder. "
		             "They are left there, and '%s' gets its own new, empty ones, which the "
		             "stage scripts use for %s. To move the existing ones into '%s' "
		             "instead, choose 'Move them to where they belong'."
		             % (len(left), short(left[0]["slide"], root),
		                ", ".join([n + "/" for n in left[0]["left_in_slide"]]),
		                mbf_name, region, mbf_name))
	if mirrored:
		lines.append("%d slide folder(s) of the raw tree are not here yet and will be "
		             "made: %s%s" % (len(mirrored), ", ".join([short(f, root) for f in
		             mirrored[:6]]), " ..." if len(mirrored) > 6 else ""))
	empties = [s for s, w in slides if w and w[0].startswith("empty slide folder")]
	if empties:
		lines.append("%d empty slide folder(s) (no images yet) are set up too: %s%s"
		             % (len(empties), ", ".join([short(f, root) for f in empties[:6]]),
		                " ..." if len(empties) > 6 else ""))
	for f in excluded:
		lines.append("! %s: marked include = no in experiment_layout.csv; left "
		             "alone" % short(f, root))
	for f, w in strays:
		lines.append("! %s holds %s but folders below it are slide folders, so it "
		             "was searched rather than set up as a slide; check that folder."
		             % (short(f, root), ", ".join(w)))
	for p, c in clashes[:8]:
		lines.append("! %s: %s" % (short(p["slide"], root), c))
	if len(clashes) > 8:
		lines.append("! ... %d more clash(es), listed in the Log" % (len(clashes) - 8))
	if skipped:
		lines.append("! %d folder(s) look like slide folders but their names do not "
		             "start with '%s', so they are left alone: %s%s"
		             % (len(skipped), prefix,
		                ", ".join([short(f, root) for f, _ in skipped[:6]]),
		                " ..." if len(skipped) > 6 else ""))
	if raw_dir_inside:
		lines.append("! nd2/ is inside the MBF folder, so 1 Convert to Tif run on it "
		             "with a blank 'Output location' makes tifs/ in the MBF folder. "
		             "Set 'Output location' to the slide folder to keep tifs/ there.")
	if fileMode == MODE_COPY and n_raw:
		total = 0
		for p in plans:
			if p["raw_dir"]:
				for r in p["raws"]:
					try:
						if not os.path.exists(os.path.join(p["raw_dir"], r)):
							total += os.path.getsize(os.path.join(p["slide"], r))
					except OSError:
						pass                # gone since the search; reported at run time
		lines.append("! Copy writes %.1f GB of new files. 'Link' gives the same "
		             "result with no extra space." % (total / 1e9))
	for p, c in clashes:
		IJ.log("  ! %s: %s" % (short(p["slide"], root), c))
	if not confirm_settings(SCRIPT_NAME, lines, CONFIRM_BEFORE_RUN):
		IJ.log("%s: cancelled at the settings check; nothing was processed." % SCRIPT_NAME)
		return

	# ---- do it -------------------------------------------------------------
	IJ.log("=" * 64)
	IJ.log("%s v%s   dataset: %s   region folder: %s"
	       % (SCRIPT_NAME, SCRIPT_VERSION, root, mbf_name))
	done, kinds, issues, record, moved = 0, {}, [], [], []
	for i, p in enumerate(plans):
		label = short(p["slide"], root)
		IJ.showStatus("[%d/%d] %s" % (i + 1, len(plans), label))
		IJ.showProgress(i, len(plans))
		try:
			if p["mbf_state"] == "clash":
				raise StepError(p["clashes"][0])
			if not os.path.isdir(p["mbf"]):
				os.makedirs(p["mbf"])
			n_mv = 0
			for src, dst in p["moves"]:
				if os.path.exists(dst):
					issues.append("%s: %s appeared before the move; left both"
					              % (label, dst))
					continue
				try:
					os.rename(src, dst)
				except OSError, e:
					issues.append("%s: could not move %s to %s (%s); left it"
					              % (label, src, dst, e))
					continue
				moved.append((src, dst))
				IJ.log("    moved %s -> %s" % (src, dst))
				n_mv += 1
			n_made = 0
			for side, name, (path, state, note) in p["folders"]:
				if state == "new" and not os.path.isdir(path):
					os.makedirs(path)
					n_made += 1
			added, kept = 0, 0
			if p["raw_dir"]:
				if not os.path.isdir(p["raw_dir"]):
					os.makedirs(p["raw_dir"])
				for r in p["raws"]:
					src = os.path.join(p["slide"], r)
					dst = os.path.join(p["raw_dir"], r)
					if os.path.exists(dst) or os.path.islink(dst):
						kept += 1
						why = existing_problem(src, dst)
						if why:
							issues.append("%s: %s/%s %s" % (label, RAW_SUBFOLDER, r, why))
						continue
					try:
						how = put_file(src, dst, fileMode)
					except StepError, e:
						issues.append("%s: %s: %s" % (label, r, e))
						continue
					kinds[how] = kinds.get(how, 0) + 1
					added += 1
			done += 1
			text = "%d folder(s) made, %d moved" % (n_made, n_mv)
			if p["raw_dir"]:
				text += ", %d raw file(s) added, %d already there" % (added, kept)
			IJ.log("  %s: %s" % (label, text))
			record.append((label, text))
		except (StepError, OSError), e:
			issues.append("%s: FAILED: %s" % (label, e))
			IJ.log("  %s: FAILED: %s" % (label, e))
		except (Exception, JavaException), e:
			issues.append("%s: FAILED: %s: %s" % (label, type(e).__name__, e))
			IJ.log("  %s: FAILED: %s: %s" % (label, type(e).__name__, e))
	IJ.showProgress(1.0)
	issues = ["%s: %s" % (short(cp["slide"], root), c) for cp, c in clashes] + issues
	for s in issues:
		IJ.log("  ! " + s)

	rec = None
	if WRITE_PARAMETER_RECORD:
		items = [("#Dialog", ""),
		         ("Dataset folder (searched at every depth for slide folders)", root),
		         ("Region being analysed (names the folder, e.g. hippocampus)", region),
		         ("Added after the region name", "'%s'" % suffix),
		         ("Subfolders inside the region's MBF folder", ", ".join(inside)),
		         ("Subfolders directly in the slide folder", ", ".join(outside)),
		         ("Existing subfolders in the wrong place", moveMode),
		         ("Raw files (.nd2 / .ims)", fileMode),
		         ("Raw file type", rawType),
		         ("Raw data top folder (the tree with the .nd2/.ims files; its slide folders are mirrored here; blank = none)",
		          globals().get("rawRoot") and rawRoot.getAbsolutePath() or "(blank)"),
		         ("Only folders whose name starts with (blank = every slide folder)", prefix),
		         ("#Configuration", ""),
		         ("RAW_FOLDER_NAMES", RAW_FOLDER_NAMES), ("RAW_SUBFOLDER", RAW_SUBFOLDER),
		         ("PIPELINE_FOLDER_NAMES", PIPELINE_FOLDER_NAMES),
		         ("CASE_INSENSITIVE_NAMES", CASE_INSENSITIVE_NAMES),
		         ("CONFIRM_BEFORE_RUN", CONFIRM_BEFORE_RUN),
		         ("#Slide folders", "")] + record
		if moved:
			items += [("#Moves (from -> to; rename back to undo)", "")] + \
			         [("%d" % (k + 1), "%s -> %s" % (a, b)) for k, (a, b) in enumerate(moved)]
		if excluded:
			items += [("#Skipped (include = no in experiment_layout.csv)", "")] + \
			         [(short(f, root), "left alone") for f in excluded]
		if skipped:
			items += [("#Skipped (name rule)", "")] + [(short(f, root), ", ".join(w)) for f, w in skipped]
		if issues:
			items += [("#Problems", "")] + [("%d" % (k + 1), s) for k, s in enumerate(issues)]
		rec = write_run_record(root, SCRIPT_NAME, SCRIPT_VERSION, items)

	body = ("%d of %d slide folder(s) set up with '%s'.\nFolders moved: %d\n"
	        % (done, len(plans), mbf_name, len(moved)))
	if kinds:
		body += "Raw files added: %s\n" % ", ".join(
		    ["%d %s(s)" % (v, k) for k, v in sorted(kinds.items())])
	if kinds.get("symbolic link"):
		body += ("\nSome raw files are symbolic links (this disk does not allow "
		         "hard links). They break if the slide folder is moved or renamed.\n")
	if issues:
		body += "\n%d problem(s); check the Log window.\n" % len(issues)
	if rec:
		body += "\nParameter record:\n%s" % rec
	IJ.beep()
	IJ.showMessage(SCRIPT_NAME + (" - with problems" if issues else ""), body)


main()
