# Map_Experiment_Folders.py
#
# Fiji / ImageJ Jython script - Kapur Lab Cell Counting suite, set-up tool.
#
# Reads an experiment's folder tree and writes it as a table you can check
# and correct: experiment_layout.csv in the experiment (top) folder, one row
# per slide folder:
#
#   include, day, treatment, animal, slide, slide_path, region_folders,
#   sections, notes
#
# The levels are read from the folder path, expected as
#   <experiment>/<day>/<treatment>/<animal>/<slide>
# and filled from the bottom up (the slide folder, its parent is the animal,
# and so on). Folder names differ between experiments and days, so the
# script only guesses: open the CSV (it opens in your spreadsheet program),
# correct any day, treatment or animal, set include to "no" for slides to
# leave out (a TNC slide, for example), save it as CSV, and press OK in Fiji.
# The script then checks the file and reports anything it cannot use.
#
# Other tools read this file: Tune Counting Parameters samples sections
# from it across days, treatments and animals. Run this script again after
# adding slides; your corrections are kept for slides already in the table
# (matched by slide_path), and new slides are added with guessed levels.
#
# A slide folder is a folder that holds raw files (.nd2 / .ims), an nd2/,
# ims/ or tifs/ folder, or a region folder ("... MBF"). The search does not
# go inside a slide folder or a pipeline folder.
#
# Menu  : Plugins > Kapur Lab Cell Counting > Map Experiment Folders
# Writes: experiment_layout.csv (the previous one is kept as
#         experiment_layout_previous_<time>.csv) and a parameter record in
#         the experiment folder.
#
# Usage: Plugins > Kapur Lab Cell Counting > Map Experiment Folders, or open
# this file in the Script Editor (File > New > Script..., or Plugins >
# Scripting > Script Editor) with Language = Python (Jython) and press Run.

#@ File    (label="Experiment folder (the top folder, above the days)", style="directory") expDir
#@ String  (label="Levels between the experiment folder and the slides", value="day, treatment, animal") levelNames
#@ Boolean (label="Open the table in my spreadsheet program to check it", value=true) openTable

# =========================================================================
# ===  USER CONFIGURATION  ================================================
# =========================================================================
# Nothing below the END OF USER CONFIGURATION banner needs editing for
# routine use.

LAYOUT_CSV = "experiment_layout.csv"
RAW_EXTENSIONS = [".nd2", ".ims"]
SLIDE_SUBFOLDERS = ["nd2", "ims", "tifs"]       # their presence marks a slide
PIPELINE_FOLDER_NAMES = ["nd2", "ims", "tifs", "jpx", "xml", "rois",
                         "processed_bgsub_cleared", "probabilities",
                         "particle_counts", "optimization",
                         "pipeline_composites", "counting_tuning"]
KEY_PATTERN = r"^(Region\d+)"
CASE_INSENSITIVE_KEYS = True
REQUIRE_IN_NAME = ""
EXCLUDE_IN_NAME = ""
WRITE_PARAMETER_RECORD = True

# =========================================================================
# ===  END OF USER CONFIGURATION  =========================================
# =========================================================================

SCRIPT_NAME = "Map_Experiment_Folders"
SCRIPT_VERSION = "2.0"

import os
import re
import shutil
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


COLUMNS = ["include", "slide", "slide_path", "region_folders", "sections", "notes"]


def norm_path(p):
	"""slide_path with "/" separators, whatever computer wrote it."""
	return "/".join([c for c in p.replace("\\", "/").split("/") if c not in ("", ".")])


def is_slide(folder):
	try:
		names = os.listdir(folder)
	except OSError:
		return False
	for n in names:
		p = os.path.join(folder, n)
		if os.path.isfile(p) and os.path.splitext(n)[1].lower() in RAW_EXTENSIONS:
			return True
		if os.path.isdir(p) and (n.lower() in SLIDE_SUBFOLDERS
		                         or layout_is_region(p)):
			return True
	return False


def find_slides(root):
	out = []
	for cur, dirs, files in os.walk(root):
		if is_slide(cur):
			out.append(cur)
			dirs[:] = []
			continue
		dirs[:] = sorted([d for d in dirs if not d.startswith(".")
		                  and d.lower() not in PIPELINE_FOLDER_NAMES
		                  and not re.search(LAYOUT_MBF_RE, d, re.IGNORECASE)])
	return sorted(out + empty_slides(root, out))


def empty_slides(root, found):
	"""Empty slide folders (no images copied in yet): no subfolders and no
	files (hidden files such as .DS_Store aside), at the same depth as the
	slide folders found, named with the word "slide" or next to one."""
	if not found:
		return []
	rel = lambda f: len(os.path.relpath(f, root).split(os.sep))
	depths = set([rel(f) for f in found])
	parents = set([os.path.dirname(f) for f in found])
	out = []
	for cur, dirs, files in os.walk(root):
		kids = [d for d in dirs if not d.startswith(".")]
		dirs[:] = sorted([d for d in kids if d.lower() not in PIPELINE_FOLDER_NAMES
		                  and os.path.join(cur, d) not in found
		                  and not re.search(LAYOUT_MBF_RE, d, re.IGNORECASE)])
		if cur == root or kids or [f for f in files if not f.startswith(".")]:
			continue
		name = os.path.basename(cur)
		if rel(cur) in depths and ("slide" in name.lower()
		                           or os.path.dirname(cur) in parents):
			out.append(cur)
	return out


def count_sections(slide):
	tifs = layout_find(slide, slide, "tifs")
	keys = set()
	for d in (tifs, os.path.join(slide, "nd2"), slide):
		try:
			for n in os.listdir(d):
				if os.path.splitext(n)[1].lower() in [".tif", ".tiff"] + RAW_EXTENSIONS:
					k = key_from(n)
					if k:
						keys.add(k)
		except OSError:
			pass
		if keys:
			break
	return len(keys)


def write_layout(path, levels, rows):
	def cell(v):
		v = u"%s" % v
		return u'"%s"' % v.replace('"', '""')
	cols = ["include"] + levels + COLUMNS[1:]
	fh = open(path, "wb")
	try:
		# The BOM makes Excel read the file as UTF-8 (accented names).
		fh.write("\xef\xbb\xbf" + (u",".join([cell(c) for c in cols]) + u"\n").encode("utf-8"))
		for r in rows:
			fh.write((u",".join([cell(r.get(c, "")) for c in cols]) + u"\n").encode("utf-8"))
	finally:
		fh.close()


def check_layout(root, levels, rows):
	problems = []
	for i, r in enumerate(rows):
		line = i + 2
		inc = r.get("include", "").lower()
		if inc not in ("yes", "no", "y", "n", "1", "0", "true", "false"):
			problems.append("row %d: include is '%s'; use yes or no" % (line, r.get("include", "")))
			continue
		if inc in ("no", "n", "0", "false"):
			continue
		p = os.path.join(root, *norm_path(r.get("slide_path", "")).split("/"))
		if not r.get("slide_path") or not os.path.isdir(p):
			problems.append("row %d: slide_path '%s' is not a folder under the "
			                "experiment folder" % (line, r.get("slide_path", "")))
		for lv in levels:
			if not r.get(lv):
				problems.append("row %d (%s): '%s' is empty" % (line, r.get("slide_path", ""), lv))
	return problems


def main():
	root = expDir.getAbsolutePath()
	levels = [l.strip().lower() for l in (levelNames or "").split(",") if l.strip()]
	if not levels or [l for l in levels if l in COLUMNS]:
		IJ.error(SCRIPT_NAME, "'Levels between the experiment folder and the "
		         "slides' must be names such as: day, treatment, animal "
		         "(not %s)." % ", ".join(COLUMNS))
		return
	if is_slide(root):
		IJ.error(SCRIPT_NAME, "%s\nis itself a slide folder. Pick the experiment "
		         "folder above the days (it holds the day folders)." % root)
		return
	slides = find_slides(root)
	if not slides:
		IJ.error(SCRIPT_NAME, "No slide folders were found under\n%s" % root)
		return
	csv_path = os.path.join(root, LAYOUT_CSV)
	old = {}
	if os.path.isfile(csv_path):
		try:
			_h, old_rows = layout_read_csv(csv_path)
			old = dict([(norm_path(r.get("slide_path", "")), r) for r in old_rows])
		except (Exception, JavaException), e:
			IJ.log("WARNING: the existing %s could not be read (%s); "
			       "it is kept as a copy." % (LAYOUT_CSV, e))
	rows, n_new, n_kept, n_deep = [], 0, 0, 0
	for s in slides:
		rel = norm_path(os.path.relpath(s, root))   # always "/" (any computer)
		parts = rel.split("/")
		r = {"slide": parts[-1], "slide_path": rel,
		     "region_folders": "; ".join(layout_regions(s)),
		     "sections": count_sections(s)}
		above = parts[:-1]
		notes = []
		if rel in old:
			for k in ["include"] + levels + ["notes"]:
				r[k] = old[rel].get(k, "")
			n_kept += 1
		else:
			r["include"] = "yes"
			guess = above[-len(levels):] if above else []
			guess = [""] * (len(levels) - len(guess)) + guess
			for lv, g in zip(levels, guess):
				r[lv] = g
			if len(above) > len(levels):
				notes.append("extra folder level(s) above: %s"
				             % "/".join(above[:len(above) - len(levels)]))
				n_deep += 1
			if len(above) < len(levels):
				notes.append("fewer folder levels than %d; fill in the blanks"
				             % len(levels))
			r["notes"] = "; ".join(notes)
			n_new += 1
		rows.append(r)
	# Write the new table beside the old one first, then swap them. A share
	# that refuses renames gets a copy and an overwrite instead. On Windows a
	# table open in Excel is locked: say so, and change nothing.
	tmp = csv_path + ".writing"
	keep = None
	try:
		write_layout(tmp, levels, rows)
		if os.path.isfile(csv_path):
			keep = os.path.join(root, "experiment_layout_previous_%s.csv"
			                    % time.strftime("%Y%m%d-%H%M%S"))
			try:
				os.rename(csv_path, keep)
			except OSError:
				shutil.copyfile(csv_path, keep)
				write_layout(csv_path, levels, rows)
		if os.path.isfile(tmp) and not os.path.isfile(csv_path):
			os.rename(tmp, csv_path)
		if keep:
			IJ.log("  previous table kept as %s" % keep)
	except (OSError, IOError), e:
		if keep and os.path.isfile(keep):
			try:
				if os.path.isfile(csv_path):
					os.remove(keep)        # the old table is still in place
				else:
					os.rename(keep, csv_path)
			except OSError:
				pass
		IJ.error(SCRIPT_NAME, "%s\ncould not be replaced (%s).\n\nIt is probably open in "
		         "Excel or another program, which locks the file on Windows. Close "
		         "it there and run Map Experiment Folders again. The table was not "
		         "changed." % (csv_path, e))
		return
	finally:
		try:
			if os.path.isfile(tmp):
				os.remove(tmp)
		except OSError:
			pass
	IJ.log("=" * 64)
	IJ.log("%s v%s: %d slide folder(s) -> %s (%d new, %d kept from the "
	       "previous table)" % (SCRIPT_NAME, SCRIPT_VERSION, len(rows), csv_path,
	                            n_new, n_kept))
	problems = []
	open_it = openTable
	while True:
		if open_it:
			try:
				from java.awt import Desktop
				from java.io import File
				Desktop.getDesktop().open(File(csv_path))
			except (Exception, JavaException), e:
				IJ.log("  (could not open the table automatically: %s)" % e)
		from ij.gui import GenericDialog
		gd = GenericDialog(SCRIPT_NAME + " - check the table")
		msg = ("%d slide folder(s) were written to\n%s\n\nCheck the %s columns "
		       "and 'include' (yes / no) in your spreadsheet program, save it\n"
		       "as CSV with the same name, then press OK. Cancel keeps the "
		       "table as it is now on disk without checking it."
		       % (len(rows), csv_path, ", ".join(levels)))
		if problems:
			msg += "\n\nProblems found last time:\n" + "\n".join(problems[:12])
		gd.addMessage(msg)
		gd.showDialog()
		if gd.wasCanceled():
			break
		try:
			head, rows2 = layout_read_csv(csv_path)
		except (Exception, JavaException), e:
			problems = ["the table could not be read: %s" % e]
			continue
		missing = [c for c in ["include", "slide_path"] + levels if c not in head]
		problems = (["missing column(s): %s" % ", ".join(missing)] if missing
		            else check_layout(root, levels, rows2))
		if not problems:
			rows = rows2
			break
		IJ.log("  table problems: " + " | ".join(problems[:12]))
		open_it = False
	inc = [r for r in rows if (r.get("include") or "yes").lower() in ("yes", "y", "1", "true")]
	groups = {}
	for r in inc:
		g = " / ".join([r.get(lv, "") for lv in levels[:-1]] or ["all"])
		groups[g] = groups.get(g, 0) + 1
	summary = ["%s: %d slide(s)" % (g, n) for g, n in sorted(groups.items())]
	for ln in summary:
		IJ.log("  " + ln)
	rec = None
	if WRITE_PARAMETER_RECORD:
		rec = write_run_record(root, SCRIPT_NAME, SCRIPT_VERSION, [
		    ("#Dialog", ""), ("Experiment folder (the top folder, above the days)", root),
		    ("Levels between the experiment folder and the slides", ", ".join(levels)),
		    ("#Result", ""), ("table", csv_path), ("slide folders", len(rows)),
		    ("included", len(inc)), ("problems left", len(problems))]
		    + [("#Groups", "")] + [(g, n) for g, n in sorted(groups.items())])
	body = ("%d slide folder(s) mapped, %d included.\n\n%s\n\nTable: %s\n"
	        % (len(rows), len(inc), "\n".join(summary[:20]), csv_path))
	if problems:
		body += "\n%d problem(s) left in the table; see the Log.\n" % len(problems)
	if rec:
		body += "\nParameter record:\n%s" % rec
	IJ.showMessage(SCRIPT_NAME + (" - with problems" if problems else ""), body)


main()
