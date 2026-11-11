# Tune_Counting_Parameters.py
#
# Fiji / ImageJ Jython script - Kapur Lab Cell Counting suite, optional.
#
# Finds ONE set of counting parameters (threshold, watershed, size and
# circularity limits for 3 Count Particles per ROI) for a whole experiment,
# by comparing them with cells you count by hand:
#
#   1. It draws a share of the experiment's sections at random (e.g. 6% of
#      100 sections = 6), spread over days, treatments and animals (from
#      experiment_layout.csv; run Map Experiment Folders first).
#   2. For each one it opens the image you count on ("Image to count cells
#      on": the ilastik probability map's cell channel by default, which is
#      easier with much noise or axon signal; or the background-subtracted
#      image, when cells are clearly separated and noise is low; counting on
#      the map cannot catch cells ilastik missed) with a rectangle placed at
#      random fully inside the ROI you
#      name (e.g. Left). Move or resize the rectangle if you want, then
#      click every cell inside it with the multi-point tool. You are not
#      told which day, treatment or animal a section comes from, so the
#      counts are blind to the group.
#   3. It then counts the same rectangles from the ilastik probability maps
#      exactly as stage 3 does, for every combination of the candidate
#      values, matches the detected particles to your clicks, and picks the
#      combination with the best agreement (F1 = 2TP / (2TP + FP + FN): a
#      click inside a counted particle is a hit; one particle takes at most
#      one click; ties go to the smaller difference in total count).
#
# The result is written to tuned_counting_parameters_<region>.txt in the
# experiment folder (region = the MBF folder's name, also written inside).
# Stage 3 uses it by default for that region only, on every slide of the
# experiment, and warns when "The values below" differ from it. Keep
# 'Exclude particles on edges' off in stage 3 (the tuning counts particles
# by centre, with edge exclusion off).
#
# Needs, for every sampled section: a background-subtracted image (2b), a
# probability map (ilastik / 2c) and an ROI set (2a) in the region folder
# you name. Sections without all three are not drawn.
#
# Menu  : Plugins > Kapur Lab Cell Counting > Tune Counting Parameters
# Writes: in <experiment>/counting_tuning_<time>/: the clicks and rectangle
#         of each section (section_<n>.zip), sections.csv (which section
#         each code was, added as each section is counted, so a session
#         cut short can be reused; do not open it while counting, to stay
#         blind), results.csv (every combination tried, best first;
#         results_<time>.csv when counts are reused) and a parameter record;
#         and <experiment>/tuned_counting_parameters_<region>.txt.
#
# Usage: Plugins > Kapur Lab Cell Counting > Tune Counting Parameters, or
# open this file in the Script Editor (File > New > Script..., or Plugins >
# Scripting > Script Editor) with Language = Python (Jython) and press Run.

#@ File    (label="Experiment folder (holds experiment_layout.csv)", style="directory") expDir
#@ String  (label="Region (its MBF folder name, e.g. hippocampus; blank = choose from a list)", value="", required=false) regionName
#@ String  (label="Only use images whose name contains (blank = all; e.g. _C2)", value="", required=false) nameFilter
#@ Double  (label="Share of the experiment's sections to count by hand (%)", value=6.0, min=0.1, max=100) sharePercent
#@ Integer (label="   but at least this many sections", value=4, min=2) minSections
#@ String  (label="ROI the rectangle must lie inside (blank = any ROI; e.g. Left)", value="", required=false) roiName
#@ Integer (label="Rectangle size (pixels)", value=300, min=40) rectSize
#@ String  (label="Image to count cells on", choices={"Probability map (after ilastik)", "Background-subtracted image (before ilastik)"}, style="radioButtonVertical") countOn
#@ Boolean (label="   with the map, also show the background-subtracted image as an extra channel", value=true) addBgsub
#@ Integer (label="Channel to show from the background-subtracted image (0 = all)", value=1, min=0) showChannel
#@ Integer (label="Probability channel that holds the cells (stage 3 SIGNAL_CHANNEL)", value=1, min=1) probChannel
#@ Boolean (label="Include holes (as in stage 3)", value=false) includeHoles
#@ Integer (label="Random seed (0 = new each run)", value=0, min=0) randomSeed
#@ File    (label="Reuse the counts of an earlier tuning folder (blank = count new sections)", style="directory", required=false) reuseDir

# =========================================================================
# ===  USER CONFIGURATION  ================================================
# =========================================================================
# Nothing below the END OF USER CONFIGURATION banner needs editing for
# routine use.

# ---- CANDIDATE VALUES (every combination is tried) ----
THRESHOLDS = [64, 80, 96, 112, 128, 144, 160, 176, 192, 208, 224]   # 8-bit
WATERSHED = [False, True]
MIN_SIZES = [0, 5, 10, 15, 20, 30, 40, 60, 80, 100, 150]            # pixels
MAX_SIZES = [0]                     # pixels; 0 = no limit
MIN_CIRCULARITIES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
MAX_CIRCULARITY = 1.0

# ---- FILES ----
LAYOUT_CSV = "experiment_layout.csv"
TUNED_FILE = "tuned_counting_parameters.txt"
BGSUB_FOLDER = "processed_bgsub_cleared"
PROB_FOLDER = "probabilities"
ROI_FOLDER = "rois"
PAD = 60                    # pixels counted around the rectangle (whole particles)
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

SCRIPT_NAME = "Tune_Counting_Parameters"
SCRIPT_VERSION = "2.0"
if (globals().get("nameFilter") or "").strip():
	REQUIRE_IN_NAME = nameFilter.strip()
# What you count on: the ilastik probability map (default; easier when there
# is much noise or axon signal) or the background-subtracted image (when the
# cells are clearly separated and there is little noise).
COUNT_ON_MAP = not (globals().get("countOn") or "").startswith("Background")
COUNT_ON_TEXT = (COUNT_ON_MAP and "probability map (after ilastik)"
                 or "background-subtracted image (before ilastik)")
# Counting on the map, the background-subtracted image can be shown with it
# as an extra channel (on by default), to tell cells from noise.
ADD_BG = COUNT_ON_MAP and globals().get("addBgsub", True)

import os
import re
import time
import math
import random
from ij import IJ, ImagePlus, Prefs
from ij.gui import Roi, PointRoi, Overlay, NonBlockingGenericDialog
from ij.plugin import ChannelSplitter, Duplicator
from ij.plugin.filter import ParticleAnalyzer
from ij.measure import ResultsTable, Measurements, Calibration
from ij.process import ImageProcessor, ByteProcessor
from java.awt import Color
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


# ---- SHARED: roi_io -- keep identical ----
# RoiSet .zip files are read and written without the ROI Manager.
def read_roiset(path):
	"""RoiSet .zip (or .roi) -> OrderedDict name -> Roi. Raises StepError."""
	import os
	import jarray
	from collections import OrderedDict
	from ij.io import RoiDecoder
	from java.io import FileInputStream, BufferedInputStream, ByteArrayOutputStream
	from java.util.zip import ZipInputStream
	from java.lang import Exception as JavaException

	rois = OrderedDict()
	if not os.path.isfile(path):
		raise StepError("the ROI file does not exist: %s" % path)

	if path.lower().endswith(".roi"):
		try:
			roi = RoiDecoder(path).getRoi()
		except (Exception, JavaException), e:
			raise StepError("the .roi file could not be read: %s" % str(e))
		if roi is None:
			raise StepError("the .roi file contains no readable ROI.")
		rname = os.path.splitext(os.path.basename(path))[0]
		roi.setName(rname)
		rois[rname] = roi
		return rois

	try:
		zis = ZipInputStream(BufferedInputStream(FileInputStream(path)))
	except (Exception, JavaException), e:
		raise StepError("the ROI zip could not be opened: %s" % str(e))

	try:
		buf = jarray.zeros(8192, 'b')
		entry = zis.getNextEntry()
		while entry is not None:
			short = entry.getName().replace("\\", "/").split("/")[-1]
			if short.lower().endswith(".roi"):
				bos = ByteArrayOutputStream()
				n = zis.read(buf, 0, len(buf))
				while n > 0:
					bos.write(buf, 0, n)
					n = zis.read(buf, 0, len(buf))
				roi = RoiDecoder(bos.toByteArray(), short).getRoi()
				if roi is not None:
					rname = short[:-4]
					base, k = rname, 2
					while rname in rois:          # duplicate entry names
						rname = "%s~%d" % (base, k)
						k += 1
					roi.setName(rname)
					rois[rname] = roi
			entry = zis.getNextEntry()
	except StepError:
		raise
	except (Exception, JavaException), e:
		raise StepError("the ROI zip could not be read (%s). It may be "
		                "truncated or not an ImageJ RoiSet." % str(e))
	finally:
		try:
			zis.close()
		except (Exception, JavaException):
			pass

	if not rois:
		raise StepError("the ROI zip contains no readable .roi entries. "
		                "It may be empty or corrupt.")
	return rois


def write_roiset(rois, path):
	"""Write a dict or (name, Roi) list as a RoiSet .zip; names made safe
	and unique, each Roi named to match. Raises StepError."""
	import re
	from ij.io import RoiEncoder
	from java.io import FileOutputStream, BufferedOutputStream
	from java.util.zip import ZipOutputStream, ZipEntry
	from java.lang import Exception as JavaException

	pairs = rois.items() if hasattr(rois, "items") else list(rois)
	try:
		zos = ZipOutputStream(BufferedOutputStream(FileOutputStream(path)))
	except (Exception, JavaException), e:
		raise StepError("could not open the output file for writing:\n"
		                "      %s\n      %s\n      Check that the folder "
		                "exists and is not read-only, and that the file is "
		                "not open in another program." % (path, str(e)))
	used = {}
	try:
		for name, roi in pairs:
			if roi is None:
				raise StepError("ROI '%s' is None and cannot be saved" % name)
			safe = re.sub(r'[\\/:*?"<>|]', "_", str(name)).strip() or "roi"
			used[safe] = used.get(safe, 0) + 1
			if used[safe] > 1:
				safe = "%s~%d" % (safe, used[safe])
			roi.setName(safe)
			data = RoiEncoder.saveAsByteArray(roi)
			if data is None:
				raise StepError(
				    "ImageJ could not encode ROI '%s'. If it came out of a "
				    "subtract() that removed everything, it may have zero "
				    "area." % name)
			zos.putNextEntry(ZipEntry(safe + ".roi"))
			zos.write(data, 0, len(data))
			zos.closeEntry()
	finally:
		try:
			zos.close()
		except (Exception, JavaException):
			pass
# ---- END SHARED: roi_io ----


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


# ---------------------------------------------------------------- layout


def region_of(slide, typed):
	regs = layout_regions(slide)
	if typed:
		hits = layout_match_region(regs, typed)
		return os.path.join(slide, hits[0]) if len(hits) == 1 else None
	if len(regs) == 1:
		return os.path.join(slide, regs[0])
	return slide if not regs else None


def pick_region_name(root, rows):
	"""With 'Region' blank: "" when the slides hold at most one region name,
	else the name chosen from a list (None if cancelled)."""
	from ij.gui import GenericDialog
	counts = {}
	for r in rows:
		if r.get("include", "").lower() in ("no", "n", "0", "false"):
			continue
		slide = os.path.join(root, *[c for c in r.get("slide_path", "").replace("\\", "/")
		                             .split("/") if c not in ("", ".")])
		for g in layout_regions(slide):
			counts[g] = counts.get(g, 0) + 1
	if len(counts) < 2:
		return ""
	names = sorted(counts)
	shown = ["%s  (%d slide(s))" % (g, counts[g]) for g in names]
	last = Prefs.get("kapurcellcount.region", "")
	gd = GenericDialog("Choose the region")
	gd.addMessage("The slides hold several region folders. Choose the one to tune.")
	gd.addChoice("Region folder", shown, shown[names.index(last)] if last in names else shown[0])
	gd.showDialog()
	if gd.wasCanceled():
		return None
	pick = names[shown.index(gd.getNextChoice())]
	Prefs.set("kapurcellcount.region", pick)
	return pick


def files_by_key(folder, exts):
	out = {}
	try:
		for n in sorted(os.listdir(folder)):
			if (os.path.splitext(n)[1].lower() in exts and key_from(n)
			        and (exts == (".zip",) or name_allowed(n))):
				out.setdefault(key_from(n), []).append(os.path.join(folder, n))
	except OSError:
		pass
	return out


def eligible_sections(root, rows, levels, region_typed):
	"""[(group label, slide row, key, bgsub, prob, roizip, region name)]
	and notes. The region name is the MBF folder's name ("" when the slide
	has none)."""
	out, notes = [], []
	for r in rows:
		if r.get("include", "").lower() in ("no", "n", "0", "false"):
			continue
		slide = os.path.join(root, *[c for c in r.get("slide_path", "").replace("\\", "/")
		                             .split("/") if c not in ("", ".")])
		reg = region_of(slide, region_typed)
		if reg is None:
			notes.append("%s: no single region folder matches '%s'"
			             % (r.get("slide_path"), region_typed or "(blank)"))
			continue
		bg = files_by_key(layout_find(slide, reg, BGSUB_FOLDER), (".tif", ".tiff"))
		pr = files_by_key(layout_find(slide, reg, PROB_FOLDER), (".tif", ".tiff"))
		rz = files_by_key(layout_find(slide, reg, ROI_FOLDER), (".zip",))
		group = " / ".join([r.get(l, "") for l in levels])
		rname = reg != slide and os.path.basename(reg) or ""
		n = 0
		# Counting on the map needs no background-subtracted image.
		need = COUNT_ON_MAP and pr or bg
		for k in sorted(need):
			one_bg = len(bg.get(k, [])) == 1 and bg[k][0] or ""
			if (k in pr and k in rz and len(pr[k]) == 1
			        and (COUNT_ON_MAP or len(bg[k]) == 1)):
				out.append((group, r, k, one_bg, pr[k][0], rz[k][0], rname))
				n += 1
			elif k in pr and k in rz:
				notes.append("%s %s: several images or probability maps for one "
				             "section (fill in 'Only use images whose name "
				             "contains'); left out" % (r.get("slide_path"), k))
		if need and not n:
			notes.append("%s: no section has %s, a probability map and an ROI set"
			             % (r.get("slide_path"), not COUNT_ON_MAP and
			                "a background-subtracted image," or ""))
	return out, notes


def draw_sections(pool, n, rng):
	"""n sections spread over groups (day / treatment / animal): take one at
	random from each group in turn (groups in random order), so every group
	is used before any is used twice."""
	groups = {}
	for item in pool:
		groups.setdefault(item[0], []).append(item)
	names = sorted(groups)
	rng.shuffle(names)
	for g in names:
		rng.shuffle(groups[g])
	chosen = []
	while len(chosen) < n and any(groups[g] for g in names):
		for g in names:
			if groups[g] and len(chosen) < n:
				chosen.append(groups[g].pop())
	rng.shuffle(chosen)
	return chosen


# ---------------------------------------------------------------- images
def roi_mask_image(rois, name, w, h):
	"""ByteProcessor 255 inside the chosen ROI (or any ROI; a region name
	without -L / -R: both sides), for placing the rectangle."""
	bp = ByteProcessor(w, h)
	bp.setColor(255)
	low = (name or "").lower()
	use = [r for n, r in rois.items() if not name or n.lower() == low]
	if not use:         # a region typed without its side: both sides
		use = [r for n, r in rois.items() if n.lower() in (low + "-l", low + "-r")]
	for r in use:
		bp.fill(r)
	return bp, len(use)


def rect_inside(mask, x, y, s):
	if x < 0 or y < 0 or x + s > mask.getWidth() or y + s > mask.getHeight():
		return False
	mask.setRoi(x, y, s, s)
	st = mask.getStatistics()
	mask.resetRoi()
	return st.min >= 255


def place_rect(mask, size, rng):
	"""A random size x size square fully inside the mask, shrinking the
	size if needed. (x, y, s) or None."""
	from ij.process import ImageStatistics
	b = None
	w, h = mask.getWidth(), mask.getHeight()
	pts = []
	for yy in range(0, h, 8):
		for xx in range(0, w, 8):
			if mask.get(xx, yy):
				pts.append((xx, yy))
	if not pts:
		return None
	s = size
	for _shrink in range(4):
		for _try in range(400):
			cx, cy = pts[rng.randrange(len(pts))]
			x, y = cx - s // 2, cy - s // 2
			if rect_inside(mask, x, y, s):
				return x, y, s
		s = int(s * 0.75)
		if s < 40:
			break
	return None


def open_probability(path):
	"""The cell channel of a probability map, on the 8-bit scale stage 3 uses."""
	imp, _n = bf_open(path, 0)
	from ij.process import StackStatistics
	file_max = imp.getBitDepth() == 32 and StackStatistics(imp).max or None
	if imp.getNChannels() > 1:
		chans = ChannelSplitter.split(imp)
		if len(chans) < probChannel:
			raise StepError("the probability map has %d channel(s)" % len(chans))
		keep = chans[probChannel - 1]
		for j, c in enumerate(chans):
			if j != probChannel - 1:
				c.close()
		imp.close()
		imp = keep
	elif imp.getStackSize() > 1:
		if imp.getStackSize() < probChannel:
			raise StepError("the probability map has %d plane(s)" % imp.getStackSize())
		one = ImagePlus("p", imp.getStack().getProcessor(probChannel).duplicate())
		imp.close()
		imp = one
	probability_to_8bit(imp, file_max)
	imp.setCalibration(Calibration())
	return imp


def particles_in(prob, box, thr, ws):
	"""Particles of the box (threshold thr..255, optional watershed), as
	stage 3 makes them, with no size or shape limit: list of
	(xc, yc, area, circularity, bounds, mask) in image coordinates."""
	x0, y0, bw, bh = box
	prob.setRoi(x0, y0, bw, bh)
	crop = prob.crop()
	prob.deleteRoi()
	crop.getProcessor().setThreshold(thr, 255, ImageProcessor.NO_LUT_UPDATE)
	IJ.run(crop, "Convert to Mask", "")
	if ws:
		IJ.run(crop, "Watershed", "")
	ip = crop.getProcessor()
	ip.setThreshold(255, 255, ImageProcessor.NO_LUT_UPDATE)
	opts = ParticleAnalyzer.SHOW_OVERLAY_OUTLINES | (
	    includeHoles and ParticleAnalyzer.INCLUDE_HOLES or 0)
	rt = ResultsTable()
	pa = ParticleAnalyzer(opts, Measurements.AREA | Measurements.CENTROID
	                      | Measurements.SHAPE_DESCRIPTORS, rt, 0.0,
	                      float("inf"), 0.0, 1.0)
	pa.setHideOutputImage(True)
	crop.setOverlay(None)
	if not pa.analyze(crop, ip):
		raise StepError("Analyze Particles failed")
	ov = crop.getOverlay()
	out = []
	for j in range(rt.size()):
		o = ov.get(j)
		b = o.getBounds()
		out.append((rt.getValue("X", j) + x0, rt.getValue("Y", j) + y0,
		            rt.getValue("Area", j), rt.getValue("Circ.", j),
		            (b.x + x0, b.y + y0, b.width, b.height), o.getMask()))
	crop.close()
	return out


def particle_of_point(parts, px, py):
	ix, iy = int(math.floor(px)), int(math.floor(py))
	for j, (_x, _y, _a, _c, b, m) in enumerate(parts):
		if b[0] <= ix < b[0] + b[2] and b[1] <= iy < b[1] + b[3]:
			if m is None or m.get(ix - b[0], iy - b[1]) != 0:
				return j
	return -1


def score(sections_data, minsz, maxsz, mincirc):
	"""Pooled TP, FP, FN and per-section (manual, auto)."""
	TP = FP = FN = 0
	per = []
	for rect, pts, parts, hit in sections_data:
		x, y, s = rect
		ok = set([j for j, (xc, yc, a, c, _b, _m) in enumerate(parts)
		          if x <= xc < x + s and y <= yc < y + s and a >= minsz
		          and (maxsz <= 0 or a <= maxsz) and mincirc <= c <= MAX_CIRCULARITY])
		matched = set([j for j in hit if j in ok])
		tp = len(matched)
		TP += tp
		FP += len(ok) - tp
		FN += len(pts) - tp
		per.append((len(pts), len(ok)))
	return TP, FP, FN, per


# ---------------------------------------------------------------- counting
def ask(title, text, choices):
	gd = NonBlockingGenericDialog(title)
	gd.addMessage(text)
	gd.addRadioButtonGroup("Then:", choices, len(choices), 1, choices[0])
	gd.hideCancelButton()
	if "TUNE_TEST_HOOK" in globals():          # automated tests only
		TUNE_TEST_HOOK(title)
	gd.showDialog()
	return gd.getNextRadioButton()


def set_tool(name):
	try:
		IJ.setTool(name)
	except (Exception, JavaException):
		pass        # no ImageJ toolbar (headless)


def with_extra_channel(imp, path):
	"""The map's cell channel (magenta) and the background-subtracted image
	(its channel showChannel, or all; green, ...) as one colour image; None
	(logged) when that image cannot be used. The pixel values are only
	shown, never counted."""
	from ij import CompositeImage
	from ij.plugin import RGBStackMerge
	from jarray import array
	try:
		bg, _n = bf_open(path, 0)
	except (StepError, Exception, JavaException), e:
		IJ.log("    background-subtracted image not shown: %s" % e)
		return None
	try:
		if (bg.getWidth(), bg.getHeight()) != (imp.getWidth(), imp.getHeight()):
			IJ.log("    background-subtracted image not shown: its size differs from the map's")
			return None
		nb = bg.getNChannels()
		parts = [(imp, min(probChannel, imp.getNChannels()))] + [
		    (bg, c) for c in (0 < showChannel <= nb and [showChannel] or range(1, nb + 1))]
		planes = [ImagePlus("c%d" % k, src.getStack().getProcessor(
		    src.getStackIndex(c, 1, 1)).duplicate().convertToFloat())
		    for k, (src, c) in enumerate(parts)]
		out = RGBStackMerge.mergeChannels(array(planes, ImagePlus), False)
		if not out.isComposite():
			out = CompositeImage(out, CompositeImage.COMPOSITE)
		out.setMode(CompositeImage.COMPOSITE)
		for c, lut in enumerate(["Magenta", "Green", "Cyan", "Yellow", "Red"][:len(parts)]):
			out.setC(c + 1)
			IJ.run(out, lut, "")
			if c:
				IJ.run(out, "Enhance Contrast", "saturated=0.35")
			else:
				out.resetDisplayRange()             # map: its own 0 to maximum
		out.setC(1)
		return out
	finally:
		bg.close()


def count_by_hand(code, n, bgsub, rect, size_wh, roi_mask=None, extra=None):
	"""Show the section, let the user adjust the rectangle and click cells.
	extra: the background-subtracted image shown with the map. Returns
	(rect, points) or None (skip) or "stop"."""
	imp, _ns = bf_open(bgsub, 0)
	if (imp.getWidth(), imp.getHeight()) != size_wh:
		IJ.log("  a section was skipped: its image and probability map differ in size")
		imp.close()
		return None
	both = extra and with_extra_channel(imp, extra)
	if both:
		imp.close()
		imp = both
	else:
		ch = COUNT_ON_MAP and probChannel or showChannel   # map: the cell channel
		if ch > 0 and imp.getNChannels() >= ch and imp.getNChannels() > 1:
			imp.setC(ch)
			if imp.isComposite():
				imp.setDisplayMode(IJ.GRAYSCALE)
		if COUNT_ON_MAP:
			imp.resetDisplayRange()                 # map: its own 0 to maximum
		else:
			IJ.run(imp, "Enhance Contrast", "saturated=0.35")
	imp.setTitle("Section %d of %d" % (code, n))   # no group information
	imp.show()
	try:
		x, y, s = rect
		imp.setRoi(Roi(x, y, s, s))
		IJ.run(imp, "To Selection", "")
		set_tool("rectangle")
		a = ask("Section %d of %d - rectangle" % (code, n),
		        "The yellow square lies inside the ROI. Move or resize it if you "
		        "want another area\n(drag it, or drag its corners), then press OK.",
		        ["Count cells in this rectangle", "Skip this section", "Stop counting"])
		if a.startswith("Skip"):
			return None
		if a.startswith("Stop"):
			return "stop"
		r = imp.getRoi()
		if r is not None and r.getType() == Roi.RECTANGLE:
			b = r.getBounds()
			x0, y0 = max(0, b.x), max(0, b.y)
			x1 = min(imp.getWidth(), b.x + b.width)
			y1 = min(imp.getHeight(), b.y + b.height)
			if x1 - x0 >= 10 and y1 - y0 >= 10:
				# a square inside both the drawn rectangle and the image
				x, y, s = x0, y0, min(x1 - x0, y1 - y0)
				if x1 - x0 != y1 - y0:
					IJ.log("    the rectangle was made square (side %d px, from its "
					       "top-left corner)" % s)
			if roi_mask is not None and not rect_inside(roi_mask, x, y, s):
				IJ.log("    the adjusted square is not entirely inside %s"
				       % (roiName or "the ROIs"))
		ov = Overlay()
		box = Roi(x, y, s, s)
		box.setStrokeColor(Color.yellow)
		ov.add(box)
		imp.setOverlay(ov)
		imp.deleteRoi()
		set_tool("multipoint")
		while True:
			a = ask("Section %d of %d - count" % (code, n),
			        "Click the centre of every cell inside the yellow square "
			        "(multi-point tool).\nAlt-click a point to remove it. Count a "
			        "cell on the edge when most of it is inside.\nZero is a valid "
			        "count. Press OK when done." + (both and "\n\nMagenta: the "
			        "probability map; green: the background-subtracted image. Image > "
			        "Color > Channels Tool turns either off." or ""),
			        ["Done", "Skip this section", "Stop counting"])
			if a.startswith("Skip"):
				return None
			if a.startswith("Stop"):
				return "stop"
			pts = []
			r = imp.getRoi()
			if r is not None and r.getType() == Roi.POINT:
				fp = r.getFloatPolygon()
				pts = [(fp.xpoints[i], fp.ypoints[i]) for i in range(fp.npoints)]
			inside = [(px, py) for px, py in pts if x <= px < x + s and y <= py < y + s]
			if len(inside) < len(pts):
				IJ.log("    %d click(s) outside the square were left out"
				       % (len(pts) - len(inside)))
			return (x, y, s), inside
	finally:
		imp.changes = False
		imp.close()


def save_counts(path, rect, pts):
	x, y, s = rect
	items = [("rectangle", Roi(x, y, s, s))]
	if pts:
		pr = PointRoi()
		for px, py in pts:
			pr.addPoint(px, py)
		items.append(("cells", pr))
	write_roiset(items, path)


def load_counts(path):
	rois = read_roiset(path)
	b = rois["rectangle"].getBounds()
	pts = []
	if "cells" in rois:
		fp = rois["cells"].getFloatPolygon()
		pts = [(fp.xpoints[i], fp.ypoints[i]) for i in range(fp.npoints)]
	return (b.x, b.y, b.width), pts


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


def tuned_name(region):
	"""tuned_counting_parameters_<region>.txt (no region: the plain name)."""
	tag = re.sub(r"[^A-Za-z0-9]+", "_", region).strip("_")
	return tag and "tuned_counting_parameters_%s.txt" % tag or TUNED_FILE


def one_section(item, code, n, rng):
	"""Place the square and count one section: (rect, points), None (skip
	or no square fits) or "stop". Raises on unreadable files."""
	rois = read_roiset(item[5])
	prob_imp, _ns = bf_open(item[4], 0)
	w, h = prob_imp.getWidth(), prob_imp.getHeight()
	prob_imp.close()
	mask, nuse = roi_mask_image(rois, (roiName or "").strip(), w, h)
	rect = place_rect(mask, rectSize, rng) if nuse else None
	if rect is None:
		IJ.log("  a section was replaced: no %dpx square fits inside %s"
		       % (rectSize, roiName or "its ROIs"))
		return None
	if ADD_BG and not item[3]:
		IJ.log("    no single background-subtracted image for this section: the "
		       "map is shown alone")
	return count_by_hand(code, n, COUNT_ON_MAP and item[4] or item[3], rect, (w, h),
	                     mask, ADD_BG and item[3] or None)


# ------------------------------------------------------------------ main
def main():
	root = expDir.getAbsolutePath()
	layout = os.path.join(root, LAYOUT_CSV)
	if reuseDir is None and not os.path.isfile(layout):
		IJ.error(SCRIPT_NAME, "%s was not found in\n%s\n\nRun Map Experiment "
		         "Folders first." % (LAYOUT_CSV, root))
		return
	seed_used = randomSeed or (int(time.time() * 1000) % 100000000 or 1)
	rng = random.Random(seed_used)
	stamp = time.strftime("%Y%m%d-%H%M%S")
	sections = []      # (code, item, rect, points)
	if reuseDir is not None:
		tdir = reuseDir.getAbsolutePath()
		sp = os.path.join(tdir, "sections.csv")
		for sr in os.path.isfile(sp) and layout_read_csv(sp)[1] or []:
			try:            # a session cut short keeps every row written
				rect, pts = load_counts(os.path.join(tdir, "section_%s.zip" % sr["code"]))
				item = (sr["group"], None, sr["key"], sr["bgsub"], sr["probability"],
				        sr["rois"], sr.get("region", ""))
				sections.append((int(sr["code"]), item, rect, pts))
			except (StepError, KeyError, ValueError, JavaException), e:
				IJ.log("  section %s of %s left out: %s" % (sr.get("code"), tdir, e))
		lines = ["Reusing %d counted section(s) from %s" % (len(sections), tdir)]
		notes = []
		regs = sorted(set([s[1][6] for s in sections]))
	else:
		head, rows = layout_read_csv(layout)
		levels = [h for h in head if h not in ("include", "slide", "slide_path",
		                                       "region_folders", "sections", "notes")]
		typed = (regionName or "").strip() or pick_region_name(root, rows)
		if typed is None:
			return
		pool, notes = eligible_sections(root, rows, levels, typed)
		if not pool:
			IJ.error(SCRIPT_NAME, "No section has %sa probability map and an ROI set."
			         "\n\n" % (not COUNT_ON_MAP and "a background-subtracted image, " or "")
			         + "\n".join(notes[:10]))
			return
		n = max(minSections, int(round(len(pool) * sharePercent / 100.0)))
		n = min(n, len(pool))
		tdir = os.path.join(root, "counting_tuning_%s" % stamp)
		groups = sorted(set([p[0] for p in pool]))
		regs = sorted(set([p[6] for p in pool]))
		lines = ["Experiment: %s" % root,
		         "Sections available: %d in %d group(s) (%s)" % (len(pool), len(groups),
		                                                          ", ".join(levels)),
		         "Sections to count: %d (%.1f%%, at least %d), drawn across groups"
		         % (n, sharePercent, minSections),
		         "Rectangle: %d x %d px inside %s" % (rectSize, rectSize,
		                                              "the ROI '%s'" % roiName if roiName else "any ROI"),
		         "You count on: the %s (channel %s)%s; the script counts probability "
		         "channel %d" % (COUNT_ON_TEXT, (COUNT_ON_MAP and probChannel)
		                         or showChannel or "all", ADD_BG and ", with the "
		                         "background-subtracted image as an extra channel" or "",
		                         probChannel),
		         "Counts are blind: sections are shown as 'Section 1 of %d', ..." % n,
		         "Results: %s" % tdir]
	lines.append("Candidates: %d thresholds x %d watershed x %d min sizes x %d max "
	             "sizes x %d min circularities = %d combinations"
	             % (len(THRESHOLDS), len(WATERSHED), len(MIN_SIZES), len(MAX_SIZES),
	                len(MIN_CIRCULARITIES), len(THRESHOLDS) * len(WATERSHED)
	                * len(MIN_SIZES) * len(MAX_SIZES) * len(MIN_CIRCULARITIES)))
	for nt in notes[:6]:
		lines.append("! " + nt)
	firsts, seen = [], set()        # one image per slide
	for p in (reuseDir is None and (ADD_BG or not COUNT_ON_MAP) and pool or []):
		if p[1].get("slide_path") not in seen:
			seen.add(p[1].get("slide_path"))
			firsts.append(p)
	mapish = [p for p in firsts if p[3] and looks_like_map(p[3])]
	if mapish:
		lines.append("! In %d slide(s) (e.g. %s) the images shown for counting look like "
		             "probability maps, not background-subtracted images (their channels "
		             "add up to the same total everywhere). Counting on them would tune "
		             "ilastik against itself. Check processed_bgsub_cleared/ there."
		             % (len(mapish), mapish[0][1].get("slide_path") or
		                os.path.basename(mapish[0][3])))
	if len(regs) > 1:
		IJ.error(SCRIPT_NAME, "The sections come from region folders with different "
		         "names (%s). Type the region to tune in 'Region'." % ", ".join(regs))
		return
	region = regs and regs[0] or ""
	tname = tuned_name(region)
	lines.append("Region: %s; result: %s (stage 3 uses it for this region only)"
	             % (region or "(none: protocol layout)", tname))
	if os.path.isfile(os.path.join(root, tname)):
		lines.append("! %s already exists; it will be replaced (the old one is "
		             "kept as %s_previous_<time>.txt), and stage 3 then uses the "
		             "new values." % (tname, tname[:-4]))
	if not confirm_settings(SCRIPT_NAME, lines, CONFIRM_BEFORE_RUN):
		IJ.log("%s: cancelled at the settings check; nothing was processed." % SCRIPT_NAME)
		return
	old_black = Prefs.blackBackground
	Prefs.blackBackground = True
	try:
		if reuseDir is None:
			os.makedirs(tdir)
			sec_csv = os.path.join(tdir, "sections.csv")
			fh = open(sec_csv, "wb")
			fh.write("code,group,key,bgsub,probability,rois,rect_x,rect_y,rect_size,"
			         "manual_cells,region\n")
			fh.close()
			chosen = draw_sections(pool, n, rng)
			queue = list(chosen)
			code = 0
			while queue and len(sections) < n:
				item = queue.pop(0)
				try:
					got = one_section(item, code + 1, n, rng)
				except (StepError, Exception, JavaException), e:
					IJ.log("  a section was replaced: %s: %s" % (os.path.basename(item[3]), e))
					got = None
				if got == "stop":
					break
				if got is None:
					spare = [p for p in pool if p not in chosen]
					if spare:                     # keep the sample size
						extra = spare[rng.randrange(len(spare))]
						chosen.append(extra)
						queue.append(extra)
					continue
				code += 1
				rect2, pts = got
				save_counts(os.path.join(tdir, "section_%d.zip" % code), rect2, pts)
				sections.append((code, item, rect2, pts))
				fh = open(sec_csv, "ab")          # written as you go
				fh.write((u'%d,"%s","%s","%s","%s","%s",%d,%d,%d,%d,"%s"\n'
				          % (code, item[0], item[2], item[3], item[4], item[5], rect2[0],
				             rect2[1], rect2[2], len(pts), item[6])).encode("utf-8"))
				fh.close()
				IJ.log("  section %d counted: %d cell(s)" % (code, len(pts)))
		if len(sections) < 2:
			IJ.showMessage(SCRIPT_NAME, "Fewer than 2 sections were counted, so "
			               "nothing was tuned.\nCounts so far are in %s" % tdir)
			return
		# ---- evaluate every combination ----
		IJ.log("  counting the rectangles from the probability maps ...")
		data = {}
		for t in THRESHOLDS:
			for ws in WATERSHED:
				data[(t, ws)] = []
		good = []
		for i, (c, it, rect, pts) in enumerate(sections):
			IJ.showStatus("tuning: section %d of %d" % (i + 1, len(sections)))
			one = {}
			try:
				prob = open_probability(it[4])
				try:
					x, y, s = rect
					bx, by = max(0, x - PAD), max(0, y - PAD)
					box = (bx, by, min(prob.getWidth(), x + s + PAD) - bx,
					       min(prob.getHeight(), y + s + PAD) - by)
					for t in THRESHOLDS:
						for ws in WATERSHED:
							parts = particles_in(prob, box, t, ws)
							hit = []
							for px, py in pts:
								j = particle_of_point(parts, px, py)
								if j >= 0 and j not in hit:
									hit.append(j)
							one[(t, ws)] = (rect, pts, parts, hit)
				finally:
					prob.close()
			except (StepError, Exception, JavaException), e:
				IJ.log("  ! section %d left out: %s" % (c, e))
				continue
			for k in one:
				data[k].append(one[k])
			good.append(sections[i])
		sections = good
		if len(sections) < 2:
			IJ.showMessage(SCRIPT_NAME, "Fewer than 2 sections could be evaluated, "
			               "so nothing was tuned. See the Log.")
			return
		manual_total = sum([len(p) for _c, _i, _r, p in sections])
		results = []
		for (t, ws), sd in data.items():
			for mn in MIN_SIZES:
				for mx in MAX_SIZES:
					if mx and mx <= mn:
						continue
					for mc in MIN_CIRCULARITIES:
						TP, FP, FN, per = score(sd, mn, mx, mc)
						f1 = 2.0 * TP / (2 * TP + FP + FN) if (TP + FP + FN) else 1.0
						auto_total = TP + FP
						results.append((f1, -abs(auto_total - manual_total), t, ws, mn, mx, mc,
						                TP, FP, FN, auto_total, per))
		results.sort(key=lambda r: (-r[0], -r[1], r[2], r[4], r[6]))
		# Several combinations often tie. Take the middle of the tied range
		# (threshold and minimum size nearest the median of the tied values),
		# without watershed and with the loosest shape limit when that ties
		# too: a value in the middle of a plateau is least sensitive to the
		# sections that happened to be drawn.
		top = [r for r in results if abs(r[0] - results[0][0]) < 1e-9
		       and r[1] == results[0][1]]
		med = lambda v: sorted(v)[len(v) // 2]
		mt, mm = med([r[2] for r in top]), med([r[4] for r in top])
		top.sort(key=lambda r: (abs(r[2] - mt), abs(r[4] - mm), r[3], r[6]))
		best = top[0]
		results.remove(best)
		results.insert(0, best)
		f1, _d, t, ws, mn, mx, mc, TP, FP, FN, auto_total, per = best
		prec = TP / float(TP + FP) if TP + FP else 1.0
		rec_ = TP / float(TP + FN) if TP + FN else 1.0
		err = 100.0 * (auto_total - manual_total) / manual_total if manual_total else 0.0
		fh = open(os.path.join(tdir, reuseDir is None and "results.csv"
		                       or "results_%s.csv" % stamp), "wb")
		fh.write("F1,threshold_min,watershed,min_size,max_size,min_circularity,"
		         "TP,FP,FN,auto_total,manual_total\n")
		for r in results:
			fh.write("%.4f,%d,%s,%s,%s,%.2f,%d,%d,%d,%d,%d\n"
			         % (r[0], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], manual_total))
		fh.close()
		tuned = os.path.join(root, tname)
		if os.path.isfile(tuned):
			keep = os.path.join(root, "%s_previous_%s.txt" % (tname[:-4], stamp))
			os.rename(tuned, keep)
			IJ.log("  the previous tuned values are kept as %s" % keep)
		fh = open(tuned, "w")
		fh.write("# Counting parameters tuned on %d hand-counted sections (%s)\n"
		         "# 3 Count Particles per ROI uses these for every slide of the experiment\n"
		         "# (Counting settings = Tuned values of the experiment).\n"
		         % (len(sections), tdir))
		for k, v in [("region", region), ("counted_on", COUNT_ON_TEXT), ("thresholdMin", t), ("thresholdMax", 255), ("doWatershed", ws),
		             ("minSize", float(mn)), ("maxSize", float(mx)), ("minCirc", mc),
		             ("maxCirc", MAX_CIRCULARITY), ("includeHoles", bool(includeHoles)),
		             ("excludeEdges", False), ("SIGNAL_CHANNEL", probChannel),
		             ("F1", round(f1, 4)), ("precision", round(prec, 4)),
		             ("recall", round(rec_, 4)), ("count_error_percent", round(err, 1)),
		             ("manual_cells", manual_total), ("sections", len(sections))]:
			fh.write((u"%s = %s\n" % (k, v)).encode("utf-8"))
		fh.close()
		per_lines = ["   section %d: you %d, counted %d" % (sections[i][0], a, b)
		             for i, (a, b) in enumerate(per)]
		for ln in per_lines:
			IJ.log(ln)
		rec = None
		if WRITE_PARAMETER_RECORD:
			rec = write_run_record(tdir, SCRIPT_NAME, SCRIPT_VERSION, [
			    ("#Dialog", ""),
			    ("Experiment folder (holds experiment_layout.csv)", root),
			    ("Region (its MBF folder name, e.g. hippocampus; blank = choose from a list)", regionName),
			    ("Only use images whose name contains (blank = all; e.g. _C2)", REQUIRE_IN_NAME),
			    ("Share of the experiment's sections to count by hand (%)", sharePercent),
			    ("but at least this many sections", minSections),
			    ("ROI the rectangle must lie inside (blank = any ROI; e.g. Left)", roiName),
			    ("Rectangle size (pixels)", rectSize),
			    ("Image to count cells on", COUNT_ON_TEXT),
			    ("   with the map, also show the background-subtracted image as an extra channel",
			     bool(globals().get("addBgsub", True))),
			    ("Channel to show from the background-subtracted image (0 = all)", showChannel),
			    ("Probability channel that holds the cells (stage 3 SIGNAL_CHANNEL)", probChannel),
			    ("Include holes (as in stage 3)", includeHoles),
			    ("Random seed (0 = new each run)", "%s (seed used: %d)" % (randomSeed, seed_used)),
			    ("Reuse the counts of an earlier tuning folder (blank = count new sections)",
			     reuseDir.getAbsolutePath() if reuseDir is not None else "(blank)"),
			    ("#Configuration", ""), ("THRESHOLDS", THRESHOLDS), ("WATERSHED", WATERSHED),
			    ("MIN_SIZES", MIN_SIZES), ("MAX_SIZES", MAX_SIZES),
			    ("MIN_CIRCULARITIES", MIN_CIRCULARITIES), ("MAX_CIRCULARITY", MAX_CIRCULARITY),
			    ("PAD", PAD), ("#Result", ""), ("tuned file", tuned), ("F1", f1),
			    ("precision", prec), ("recall", rec_), ("count error %", err)])
		body = ("Best of %d combinations on %d sections (%d cells counted by hand;"
		        " %d combination(s) tied, the middle one was taken):\n\n"
		        "  Threshold: minimum (8-bit) = %d\n  Watershed = %s\n"
		        "  minimum size = %s px,  maximum size = %s\n"
		        "  minimum circularity = %.2f,  maximum = %.2f\n"
		        "  Include holes = %s,  Exclude particles on edges = off\n\n"
		        "Agreement: F1 %.2f (precision %.2f, recall %.2f); total %d counted "
		        "vs %d by hand (%+.1f%%).\n\n%s\n\nSaved to %s\nDetails: %s"
		        % (len(results), len(sections), manual_total, len(top), t, ws, mn,
		           mx or "no limit", mc, MAX_CIRCULARITY, bool(includeHoles), f1, prec,
		           rec_, auto_total, manual_total, err, "\n".join(per_lines[:12]), tuned, tdir))
		if len(sections) < 4:
			body += "\n\nFew sections were counted; the result is less certain."
		IJ.beep()
		IJ.showMessage(SCRIPT_NAME, body)
	finally:
		Prefs.blackBackground = old_black


main()
