# 2a_NeuroInfo_XML_to_ROI.py - Kapur Lab Cell Counting, stage 2a (batch).
# Converts NeuroInfo contour exports (xml/, micrometres) into ImageJ RoiSet
# .zip files in pixel coordinates (rois/), one per XML, plus a parameter
# record and, optionally, a summary CSV:  xml/Region0000.xml -> rois/Region0000.zip
# Per file: 1. check the contour names against EXPECTED_ROIS; 2. compose
# the ROI set (one ROI per brain region, unify, split by hemisphere, keep,
# or the rules coded in compose_rois(); chosen in the dialog); 3. check the
# result against EXPECTED_ROIS_AFTER_MATH and write. A Check settings
# window comes first (CONFIRM_BEFORE_RUN = False skips it). Edit only the
# USER CONFIGURATION block. Menu: Plugins > Kapur Lab Cell Counting > Batch.
# To load a result later: ROI Manager > More >> > Open... > Region0007.zip

#@ File    (label="Slide folder (the scripts find its subfolders)", style="directory") slideDir
#@ String  (label="Region (its MBF folder; blank = choose from a list)", value="", required=false) regionName
#@ File    (label="Output location (blank = one level above the input)", style="directory", required=false) outParentDir
#@ String  (label="Name for the new output folder", value="rois") outFolderName
#@ String (label="Filename pattern", value="Region*.xml") filePattern
#@ String (label="Y axis", choices={"flip (usual)", "no flip"}, style="radioButtonHorizontal") yMode
#@ String (label="ROI composition", choices={"Separate brain regions - one ROI per region (options below)", "None - keep ROIs as converted", "Unify all ROIs into one", "Unify by hemisphere - left / right / unpaired", "Unify by hemisphere - unpaired added to both", "Use the composition coded in this script"}, style="listBox") compositionMode
#@ String (label="   regions to count, separated by ; (blank = every outermost region)", value="", required=false) brainRegions
#@ Boolean(label="   also count each subregion inside them separately", value=false) withSubregions
#@ String (label="   hemispheres", choices={"Left and right separately", "Left and right together (one ROI)", "Both: left, right and together"}, style="listBox") hemispheres
#@ String (label="On validation problem", choices={"warn and convert anyway", "skip the file", "stop the whole run"}, style="listBox") validationAction
#@ Boolean(label="Skip files whose .zip already exists", value=false) skipExisting
#@ Boolean(label="Write a summary CSV to the output folder", value=false) writeLog


# =========================================================================
# ===  USER CONFIGURATION  ================================================
# =========================================================================

# ---- OUTPUT NAMING ------------------------------------------------------
# Appended to the XML stem to name the zip, so the leading RegionXXXX token
# that pairs files between folders survives. "" keeps the stem
# (Region0011.xml -> Region0011.zip); "_ROIs" gives Region0011_ROIs.zip.
OUTPUT_SUFFIX = ""


# ---- 1. What the XML is supposed to contain -----------------------------
# The exact contour names expected (the XML's name="..."); EMPTY disables
# the check. With LIST_NAMES_ON_FIRST_FILE = True the Log prints every name
# in the first file, ready to paste here.
EXPECTED_ROIS = [
	# "Caudoputamen-L",
	# "Caudoputamen-R",
	# "Nucleus accumbens-L",
	# "Nucleus accumbens-R",
]

# A region split into pieces exports as several contours with the SAME
# name: the most pieces per name before it is flagged (0 = no limit).
MAX_PIECES_PER_NAME = 0

# Flag contours that are present but NOT in EXPECTED_ROIS?
FLAG_UNEXPECTED = True

# Print all contour names found in the first file (to fill EXPECTED_ROIS).
LIST_NAMES_ON_FIRST_FILE = True


# ---- 2. What should exist AFTER composition -----------------------------
# The same check on the final set written (empty = skip), against a rule
# silently doing nothing. Built-in modes: e.g. ["Left", "Right", "Unpaired"].
EXPECTED_ROIS_AFTER_MATH = [
	# "CP_combined",
	# "ACB_shell_only",
]


# ---- 3. ROI COMPOSITION -------------------------------------------------
# The mode is chosen in the dialog:
#   Separate brain regions    one ROI per brain region, with the dialog's
#                             options (section 3a) - for counts per region
#   None                      write the ROIs exactly as converted
#   Unify all                 one ROI covering every region
#   Unify by hemisphere (3)   Left / Right / Unpaired (the unpaired regions
#                             minus Left and Right): no overlap, areas add up
#   Unify by hemisphere (2)   Left / Right, each with the unpaired midline
#                             regions (they OVERLAP there)
#   Coded                     run compose_rois() below
# In both hemisphere modes an unpaired "parent" contour enclosing a left and
# a right region (PARENT_ENCLOSED_FRACTION of their area), such as "Tissue",
# is left out (and named in the Log).

# Names of the ROIs the built-in modes produce.
UNIFIED_ROI_NAME = "AllRegions"
HEMI_LEFT_NAME = "Left"
HEMI_RIGHT_NAME = "Right"
HEMI_UNPAIRED_NAME = "Unpaired"

# Hemisphere of a region name (case ignored). Step 1: the suffix "-L" /
# "-R" decides ("LH-R" is right); (_\d+)* covers pieces (Caudoputamen-L_2).
HEMISPHERE_SUFFIX_LEFT = r"-L(_\d+)*$"
HEMISPHERE_SUFFIX_RIGHT = r"-R(_\d+)*$"
#
# Step 2, without a suffix: fallback words. Matching both sides, or none,
# means unpaired. Do not add bare LH or RH (Allen: lateral habenula,
# rhomboid nucleus).
LEFT_FALLBACK_PATTERNS = [r"\(left\)", r"[_\s-]left\b", r"\bleft\b"]
RIGHT_FALLBACK_PATTERNS = [r"\(right\)", r"[_\s-]right\b", r"\bright\b"]

# Unify modes only: non-empty INCLUDE means ONLY those regions take part. A
# name also matches its pieces ("Tissue" covers Tissue_2, when Tissue is
# also in the file).
UNIFY_INCLUDE_NAMES = []       # e.g. ["Caudoputamen", "Nucleus accumbens"]
UNIFY_EXCLUDE_NAMES = []       # e.g. ["Ventricular systems"]

# Union method: "auto" (raster for many regions, else exact geometry),
# "shape" (exact ShapeRoi; slow with many detailed contours) or "raster"
# (mask and re-trace; fast, memory grows with the bounding box).
UNION_METHOD = "auto"
UNION_RASTER_MIN_ROIS = 12          # auto: use raster at or above this count
UNION_RASTER_MAX_PIXELS = 250000000  # auto: but not if the bbox is bigger

# Hemisphere modes: fraction of a left and of a right region's area inside
# a contour that makes it a parent outline.
PARENT_ENCLOSED_FRACTION = 0.90


# ---- 3a. SEPARATE BRAIN REGIONS ------------------------------------------
# "Separate brain regions": a contour's region is its name without -L / -R;
# its pieces become one ROI, so stage 3 has one column per region (NA where
# a section lacks it). Each entry of 'regions to count' (; between them) is
# a group below, else a name as NeuroInfo writes it (case ignored; the Log
# lists them), else every region with the entry at a word start. Regions
# inside another found one are its subregions. Blank: the outermost
# regions (a sideless outline enclosing both sides, as Tissue, left out).
REGION_GROUPS = {
  "Hippocampus": ["Hippocampal region", "Ammon's horn", "Field CA1", "Field CA2",
                  "Field CA3", "Dentate gyrus"],
  "Amygdala": ["Lateral amygdalar nucleus", "Basolateral amygdalar nucleus",
               "Basomedial amygdalar nucleus", "Posterior amygdalar nucleus",
               "Central amygdalar nucleus", "Medial amygdalar nucleus",
               "Intercalated amygdalar nucleus", "Anterior amygdalar area",
               "Cortical amygdalar area"],
  "Somatosensory cortex": ["Somatosensory areas", "Primary somatosensory area",
                           "Supplemental somatosensory area"],
  "Motor cortex": ["Somatomotor areas", "Primary motor area", "Secondary motor area"],
  "Dorsal striatum": ["Striatum dorsal region", "Caudoputamen"],
  "Ventral striatum": ["Striatum ventral region", "Nucleus accumbens",
                       "Fundus of striatum", "Olfactory tubercle"],
  "PAG": ["Periaqueductal gray"],
}


# ---- 4. PARAMETER RECORD ------------------------------------------------
#
# True writes _run_2a_NeuroInfo_XML_to_ROI_<date-time>.txt into the output
# folder: every dialog value and setting this run used, so the ROI sets
# can be traced back to how they were made. Keep it on.
WRITE_PARAMETER_RECORD = True


# ---- SAFETY CHECKS ----------------------------------------------------
# True shows the "Check settings" window before processing.
CONFIRM_BEFORE_RUN = True


# ---- 3b. CODED COMPOSITION ----------------------------------------------
# Used with "Use the composition coded in this script"; edit compose_rois()
# (one copy of the script per paradigm).
#   rois    ordered dict name -> Roi; mutate it or return a new one
#   ctx     ctx["file"], ctx["scale_x"], ctx["scale_y"], ctx["origin_x"],
#           ctx["origin_y"]
# Helpers (return a new Roi, inputs untouched):
#   merge(a, b, ...)      union of any number of ROIs          (OR)
#   intersect(a, b)       overlap only                         (AND)
#   subtract(a, b)        a with b removed                     (a AND NOT b)
#   xor(a, b)             in one or the other, not both        (XOR)
#   unify(rois, names)    fast union of many ROIs, by name
#   area_px(roi)          area in pixels, for sanity checks
#   is_empty(roi)         True if the ROI has no area left
#   hemisphere_of(name)   "left", "right" or None
#   warn(ctx, message)    record a warning; it reaches the Log and summary
#
# A name not in the dict makes the file FAIL with an error naming it.

def compose_rois(rois, ctx):
	"""Reshape the ROI set. Return the dict to be written."""

	# EXAMPLE A - merge left and right hemispheres into one bilateral ROI
	# rois["Caudoputamen"] = merge(rois["Caudoputamen-L"],
	#                              rois["Caudoputamen-R"])
	# del rois["Caudoputamen-L"]
	# del rois["Caudoputamen-R"]

	# EXAMPLE B - punch a hole: shell = whole structure minus the core
	# rois["ACB_shell_only"] = subtract(rois["Nucleus accumbens"],
	#                                   rois["Nucleus accumbens, core"])
	# del rois["Nucleus accumbens, core"]

	# EXAMPLE C - one ROI from a list of subregions
	# parts = ["CA1", "CA2", "CA3", "Dentate gyrus"]
	# rois["Hippocampus_combined"] = unify(rois, parts)
	# for p in parts:
	#     del rois[p]

	# EXAMPLE D - conditional composition with a sanity check
	# cp = rois["Caudoputamen"]
	# if area_px(cp) < 500:
	#     warn(ctx, "Caudoputamen is suspiciously small (%d px)" % area_px(cp))


	return rois


# =========================================================================
# ===  END OF USER CONFIGURATION  =========================================
# =========================================================================
# Nothing below this line should need editing for routine use.

SCRIPT_NAME = "2a_NeuroInfo_XML_to_ROI"
SCRIPT_VERSION = "2.0"

# Later stages pair a ROI set with its images by the leading RegionXXXX token
# of the file name (their KEY_PATTERN). Used here only to warn when the XML
# names do not carry it.
PAIRING_KEY_PATTERN = r"^(Region\d+)"

import re
import os
import fnmatch
from xml.etree import ElementTree as ET
from jarray import array
from collections import OrderedDict

from ij import IJ
from java.lang import Exception as JavaException
ANY_ERROR = (Exception, JavaException)
from ij.gui import PolygonRoi, Roi, ShapeRoi
from java.awt import Color


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


# ---- SHARED: roi_geometry -- keep identical ----
def roi_area_px(roi):
	"""Area of an ROI in pixels, computed in Java (fast even for huge ROIs)."""
	from java.lang import Exception as JavaException
	if roi is None:
		return 0
	try:
		mask = roi.getMask()
		b = roi.getBounds()
		if mask is None:
			return b.width * b.height
		hist = mask.getHistogram()
		return mask.getWidth() * mask.getHeight() - hist[0]
	except (Exception, JavaException):
		b = roi.getBounds()
		return b.width * b.height


def raster_union(roi_list):
	"""Union of ROIs via a mask traced again (fast; exact to the pixel).
	Raises StepError if empty."""
	from ij.plugin.filter import ThresholdToSelection
	from ij.process import ByteProcessor, ImageProcessor
	from java.lang import Exception as JavaException

	if not roi_list:
		raise StepError("there are no ROIs to combine.")
	if len(roi_list) == 1:
		return roi_list[0]
	bounds = [r.getBounds() for r in roi_list]
	minx = min([b.x for b in bounds])
	miny = min([b.y for b in bounds])
	w = max([b.x + b.width for b in bounds]) - minx
	h = max([b.y + b.height for b in bounds]) - miny
	if w <= 0 or h <= 0:
		raise StepError("the ROIs to combine have no area.")

	bp = ByteProcessor(w, h)
	bp.setColor(255)
	for r in roi_list:
		shifted = r.clone()
		# float bounds keep sub-pixel positions
		fb = r.getFloatBounds()
		shifted.setLocation(fb.x - minx, fb.y - miny)
		try:
			bp.fill(shifted)
		except (Exception, JavaException), e:
			raise StepError("the ROI '%s' could not be drawn into the union (%s)."
			                % (r.getName(), str(e)))

	bp.setThreshold(128, 255, ImageProcessor.NO_LUT_UPDATE)
	out = ThresholdToSelection().convert(bp)
	if out is None:
		raise StepError("the combined ROI came out empty.")
	ob = out.getBounds()
	out.setLocation(ob.x + minx, ob.y + miny)
	return out
# ---- END SHARED: roi_geometry ----


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


Y_FLIP = (yMode == "flip (usual)")

COMPOSE_NONE = compositionMode.startswith("None")
COMPOSE_UNIFY = compositionMode.startswith("Unify all")
COMPOSE_HEMI3 = compositionMode.startswith("Unify by hemisphere - left")
COMPOSE_HEMI2 = compositionMode.startswith("Unify by hemisphere - unpaired")
COMPOSE_CODED = compositionMode.startswith("Use the composition")
COMPOSE_REGIONS = compositionMode.startswith("Separate brain regions")
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
	_got = layout_confirm(SCRIPT_NAME + " - folders", _SLIDE, _REGION, [
	    ('Folder of NeuroInfo XML files (xml/)', "dir", layout_find(_SLIDE, _REGION, "xml"), None, True),
	])
	if _got is None:
		raise SystemExit
	inputDir = _F(_got[0]) if _got[0] else None


IN_DIR = inputDir.getAbsolutePath()

ACTION_WARN = (validationAction == "warn and convert anyway")
ACTION_SKIP = (validationAction == "skip the file")
ACTION_STOP = (validationAction == "stop the whole run")


class CompositionError(Exception):
	"""Raised by the helpers when a composition rule cannot be applied."""
	pass


RoiMathError = CompositionError     # older compose_rois() code raises this


# ------------------------------------------------------- math helpers
def _shape(roi, who):
	if roi is None:
		raise CompositionError("%s was given None instead of an ROI" % who)
	try:
		return ShapeRoi(roi)
	except ANY_ERROR, e:
		raise CompositionError("%s could not convert an ROI to a ShapeRoi: %s"
		                   % (who, str(e)))


# ShapeRoi's or / and / not are Python keywords: called through getattr().
def _op(a, b, method, who):
	try:
		return getattr(_shape(a, who), method)(_shape(b, who))
	except CompositionError:
		raise
	except ANY_ERROR, e:
		raise CompositionError("%s failed during the '%s' operation: %s"
		                   % (who, method, str(e)))


def merge(*rois):
	if len(rois) == 0:
		raise CompositionError("merge() needs at least one ROI")
	acc = _shape(rois[0], "merge()")
	for r in rois[1:]:
		acc = _op(acc, r, "or", "merge()")
	return acc


def intersect(a, b):
	return _op(a, b, "and", "intersect()")


def subtract(a, b):
	return _op(a, b, "not", "subtract()")


def xor(a, b):
	return _op(a, b, "xor", "xor()")


def area_px(roi):
	return roi_area_px(roi)


def is_empty(roi):
	return area_px(roi) == 0


def merge_named(rois, names, ctx):
	"""Deprecated alias for unify(rois, names); kept for older scripts."""
	missing = [n for n in names if n not in rois]
	if missing:
		raise CompositionError(
		    "merge_named() could not find these ROIs in %s: %s\n"
		    "  Available names: %s"
		    % (ctx.get("file", "?"), ", ".join(missing),
		       ", ".join(sorted(rois.keys())[:40])))
	return merge(*[rois[n] for n in names])


def _piece_base(name, present=None):
	"""Lower-case name without a _2 / _3 piece suffix (with present: only
	when the shorter name is present, so "layer 2_3" keeps its digits)."""
	low = name.lower()
	if present is None:
		return re.sub(r"_\d+$", "", low)
	have = set([p.lower() for p in present])
	while True:
		base = re.sub(r"_\d+$", "", low)
		if base == low or base not in have:
			return low
		low = base


def _hemisphere_detail(name):
	"""(side "left" / "right" / None, how "suffix" / "fallback" / "both" /
	None)."""
	s = name.strip()
	if re.search(HEMISPHERE_SUFFIX_LEFT, s, re.IGNORECASE):
		return "left", "suffix"
	if re.search(HEMISPHERE_SUFFIX_RIGHT, s, re.IGNORECASE):
		return "right", "suffix"
	is_l = [p for p in LEFT_FALLBACK_PATTERNS if re.search(p, s, re.IGNORECASE)]
	is_r = [p for p in RIGHT_FALLBACK_PATTERNS if re.search(p, s, re.IGNORECASE)]
	if is_l and is_r:
		return None, "both"
	if is_l:
		return "left", "fallback"
	if is_r:
		return "right", "fallback"
	return None, None


def hemisphere_of(name):
	""""left", "right" or None (unpaired) for an ROI name."""
	return _hemisphere_detail(name)[0]


def _short_list(names, cap=10):
	"""'a, b, c, ... (n more)' for the Log."""
	shown = ", ".join(names[:cap])
	if len(names) > cap:
		shown += ", ... (%d more)" % (len(names) - cap)
	return shown


def apply_unify_filters(names):
	inc = [x.lower() for x in UNIFY_INCLUDE_NAMES]
	exc = [x.lower() for x in UNIFY_EXCLUDE_NAMES]
	out = []
	for n in names:
		low, base = n.lower(), _piece_base(n, names)
		if inc and low not in inc and base not in inc:
			continue
		if low in exc or base in exc:
			continue
		out.append(n)
	return out


def _union_roi_list(roi_list):
	if len(roi_list) == 1:
		return roi_list[0], "single region, nothing to union"

	use_raster = (UNION_METHOD == "raster")
	if UNION_METHOD == "auto" and len(roi_list) >= UNION_RASTER_MIN_ROIS:
		bs = [r.getBounds() for r in roi_list]
		px = ((max([b.x + b.width for b in bs]) - min([b.x for b in bs]))
		      * (max([b.y + b.height for b in bs]) - min([b.y for b in bs])))
		use_raster = (0 < px <= UNION_RASTER_MAX_PIXELS)

	if use_raster:
		try:
			out = raster_union(roi_list)
		except StepError, e:
			raise CompositionError("the union could not be computed: %s" % str(e))
		return out, "raster union of %d region(s)" % len(roi_list)
	return merge(*roi_list), "geometric union of %d region(s)" % len(roi_list)


def unify(rois, names):
	"""Fast union of several ROIs, by name."""
	missing = [n for n in names if n not in rois]
	if missing:
		raise CompositionError(
		    "unify() could not find these ROIs: %s" % ", ".join(missing))
	roi, _note = _union_roi_list([rois[n] for n in names])
	return roi


def _mask_info(roi):
	"""(bounds, mask (255 inside, aligned to the bounds), area) of an ROI."""
	from ij.process import ByteProcessor
	b = roi.getBounds()
	m = roi.getMask()
	if m is None:
		m = ByteProcessor(max(1, b.width), max(1, b.height))
		m.setValue(255)
		m.fill()
	return b, m, m.getHistogram()[255]


def _shared_px(info_a, info_b):
	"""Number of pixels inside both ROIs (from their _mask_info)."""
	from ij.process import ByteProcessor, Blitter
	ba, ma, _aa = info_a
	bb, mb, _ab = info_b
	x0, y0 = max(ba.x, bb.x), max(ba.y, bb.y)
	x1 = min(ba.x + ba.width, bb.x + bb.width)
	y1 = min(ba.y + ba.height, bb.y + bb.height)
	if x1 <= x0 or y1 <= y0:
		return 0
	both = ByteProcessor(x1 - x0, y1 - y0)
	both.copyBits(ma, ba.x - x0, ba.y - y0, Blitter.COPY)
	other = ByteProcessor(x1 - x0, y1 - y0)
	other.copyBits(mb, bb.x - x0, bb.y - y0, Blitter.COPY)
	both.copyBits(other, 0, 0, Blitter.AND)
	return both.getHistogram()[255]


def _parent_outlines(rois, left, right, unpaired):
	"""Unpaired names enclosing PARENT_ENCLOSED_FRACTION or more of a left
	and of a right region's area."""
	if not left or not right or not unpaired:
		return []
	cache = {}

	def info(n):
		if n not in cache:
			cache[n] = _mask_info(rois[n])
		return cache[n]

	def encloses_one(u, sided):
		ub = rois[u].getBounds()
		for n in sided:
			nb = rois[n].getBounds()
			x0, y0 = max(ub.x, nb.x), max(ub.y, nb.y)
			x1 = min(ub.x + ub.width, nb.x + nb.width)
			y1 = min(ub.y + ub.height, nb.y + nb.height)
			if x1 <= x0 or y1 <= y0:
				continue
			area = info(n)[2]
			if area <= 0:
				continue
			if (x1 - x0) * (y1 - y0) < PARENT_ENCLOSED_FRACTION * area:
				continue
			if _shared_px(info(u), info(n)) >= PARENT_ENCLOSED_FRACTION * area:
				return True
		return False

	return [u for u in unpaired
	        if encloses_one(u, left) and encloses_one(u, right)]


def _subtract_masks(keep, cuts):
	"""keep minus every ROI in cuts, pixel exact; an Roi or None if empty."""
	from ij.plugin.filter import ThresholdToSelection
	from ij.process import ByteProcessor, ImageProcessor, Blitter
	if keep.getBounds().width <= 0 or keep.getBounds().height <= 0:
		return None
	kb, km, _ka = _mask_info(keep)
	canvas = ByteProcessor(kb.width, kb.height)
	canvas.copyBits(km, 0, 0, Blitter.COPY)
	for c in cuts:
		cb, cm, _ca = _mask_info(c)
		canvas.copyBits(cm, cb.x - kb.x, cb.y - kb.y, Blitter.SUBTRACT)
	if canvas.getHistogram()[255] == 0:
		return None
	canvas.setThreshold(128, 255, ImageProcessor.NO_LUT_UPDATE)
	out = ThresholdToSelection().convert(canvas)
	if out is None:
		return None
	ob = out.getBounds()
	out.setLocation(ob.x + kb.x, ob.y + kb.y)
	return out


def _centre_x(roi):
	"""x of the ROI's centroid, in pixels."""
	try:
		return float(roi.getContourCentroid()[0])
	except ANY_ERROR:
		b = roi.getBounds()
		return b.x + b.width / 2.0


def left_side_of(rois):
	""""left" / "right": the image side of the left regions (mean centroid
	x against the right regions'); None without both, or on a tie."""
	lx = [_centre_x(r) for n, r in rois.items() if hemisphere_of(n) == "left"]
	rx = [_centre_x(r) for n, r in rois.items() if hemisphere_of(n) == "right"]
	if not lx or not rx:
		return None
	ml = sum(lx) / len(lx)
	mr = sum(rx) / len(rx)
	if ml < mr:
		return "left"
	if ml > mr:
		return "right"
	return None


def off_image_message(rois, where):
	"""A problem text when most ROIs land above or left of the image, else
	None. where: e.g. "in Region0000.xml" or ""."""
	if not rois:
		return None
	above = [n for n, r in rois.items()
	         if r.getBounds().y + r.getBounds().height <= 0]
	left = [n for n, r in rois.items()
	        if r.getBounds().x + r.getBounds().width <= 0]
	off = [n for n in rois.keys() if n in above or n in left]
	if len(off) * 2 <= len(rois):
		return None
	return ("With Y axis '%s', %d of the %d ROIs%s fall completely above or "
	        "left of the image (negative pixel coordinates: %d above, %d to "
	        "the left). Either the Y axis is wrong (try the other Y axis "
	        "setting) or the X axis is mirrored (a negative x scale in the "
	        "XML, see the scale warning)."
	        % (yMode, len(off), len(rois), where and " " + where or "",
	           len(above), len(left)))


def negative_x_message(raw_sx):
	"""A problem text when the XML's x scale is negative, else None."""
	if raw_sx is None or raw_sx >= 0:
		return None
	return ("the x scale in the XML is negative (%g um/pixel): the image is "
	        "mirrored left to right. The sign is ignored, so the ROIs are "
	        "probably mirrored about the image's left edge. Check this file "
	        "with 4 Build Pipeline Composite before counting." % raw_sx)


def _split_sides(names):
	"""(left, right, unpaired, matched-both) names."""
	detail = dict([(n, _hemisphere_detail(n)) for n in names])
	return ([n for n in names if detail[n][0] == "left"],
	        [n for n in names if detail[n][0] == "right"],
	        [n for n in names if detail[n][0] is None],
	        [n for n in names if detail[n][1] == "both"])


def built_in_composition(rois, ctx):
	"""Apply one of the dialog's built-in modes. Returns (dict, [notes])."""
	if COMPOSE_REGIONS:
		return region_composition(rois, ctx)
	notes = []
	names = apply_unify_filters(list(rois.keys()))
	if not names:
		raise CompositionError(
		    "every region was removed by UNIFY_INCLUDE_NAMES / "
		    "UNIFY_EXCLUDE_NAMES, so there is nothing to unify.\n"
		    "  Regions present: %s"
		    % ", ".join(sorted(rois.keys())[:30]))
	if len(names) != len(rois):
		notes.append("%d of %d region(s) taken forward after include/exclude"
		             % (len(names), len(rois)))

	out = _SafeRoiDict(ctx)

	if COMPOSE_UNIFY:
		roi, note = _union_roi_list([rois[n] for n in names])
		roi.setName(UNIFIED_ROI_NAME)
		out[UNIFIED_ROI_NAME] = roi
		notes.append(note)
		return out, notes

	left, right, unpaired, both = _split_sides(names)
	if not left and not right:
		roi, note = _union_roi_list([rois[n] for n in names])
		roi.setName(UNIFIED_ROI_NAME)
		out[UNIFIED_ROI_NAME] = roi
		notes.append(
		    "no region name has a -L / -R suffix or matches the left/right "
		    "fallback patterns: fell back to a single unified ROI. Check that "
		    "'Separate contours by left and right hemispheres' was on in "
		    "NeuroInfo.")
		notes.append(note)
		return out, notes

	notes.append("%d left, %d right, %d unpaired region(s)"
	             % (len(left), len(right), len(unpaired)))
	if unpaired:
		notes.append("unpaired: %s" % _short_list(unpaired))
	if both:
		notes.append("WARNING: %d name(s) match both a left and a right "
		             "pattern and were treated as unpaired: %s"
		             % (len(both), _short_list(both, 5)))

	parents = _parent_outlines(rois, left, right, unpaired)
	if parents:
		into = "/".join([HEMI_LEFT_NAME, HEMI_RIGHT_NAME]
		                + ([] if COMPOSE_HEMI2 else [HEMI_UNPAIRED_NAME]))
		notes.append("%s %s both hemispheres, left out of %s"
		             % (_short_list(parents, 5),
		                "encloses" if len(parents) == 1 else "enclose", into))
	midline = [n for n in unpaired if n not in parents]

	def add_group(gname, gnames):
		roi, note = _union_roi_list([rois[n] for n in gnames])
		roi.setName(gname)
		out[gname] = roi
		notes.append("%s: %s" % (gname, note))
		return roi

	if COMPOSE_HEMI2:
		written = []
		for gname, sided, side in ((HEMI_LEFT_NAME, left, "left"),
		                           (HEMI_RIGHT_NAME, right, "right")):
			if not sided:
				notes.append("'%s' has no %s region of its own (only unpaired "
				             "midline regions), so it was not written"
				             % (gname, side))
				continue
			add_group(gname, sided + midline)
			written.append(gname)
		if midline and len(written) == 2:
			notes.append(
			    "%d unpaired midline region(s) were added to BOTH hemispheres, "
			    "so the two ROIs OVERLAP there and anything in them is counted "
			    "twice" % len(midline))
		return out, notes

	cuts = []
	for gname, gnames in ((HEMI_LEFT_NAME, left), (HEMI_RIGHT_NAME, right)):
		if not gnames:
			notes.append("'%s' had no regions and was not written" % gname)
			continue
		cuts.append(add_group(gname, gnames))
	if not midline:
		notes.append("'%s' had no regions and was not written"
		             % HEMI_UNPAIRED_NAME)
		return out, notes
	upd, note = _union_roi_list([rois[n] for n in midline])
	rest = _subtract_masks(upd, cuts)
	if rest is None:
		notes.append("'%s' had no area left after removing %s and %s, so it "
		             "was not written" % (HEMI_UNPAIRED_NAME, HEMI_LEFT_NAME,
		                                  HEMI_RIGHT_NAME))
		return out, notes
	rest.setName(HEMI_UNPAIRED_NAME)
	out[HEMI_UNPAIRED_NAME] = rest
	notes.append("%s: %s; %s and %s removed from it, so the three ROIs do "
	             "not overlap and their areas add up"
	             % (HEMI_UNPAIRED_NAME, note, HEMI_LEFT_NAME, HEMI_RIGHT_NAME))
	return out, notes


# ---- SHARED: brain_regions -- keep identical ----
# 'Separate brain regions' (2a): one ROI per region, pieces joined. Needs
# the 2a helpers and the dialog's brainRegions, withSubregions, hemispheres.
REGIONS_FOUND = set()      # typed regions found in at least one file
HEMI_TOGETHER = (globals().get("hemispheres") or "").startswith("Left and right together")
HEMI_BOTH = (globals().get("hemispheres") or "").startswith("Both")


def clean_name(n):
	"""A name as the ROIs carry it."""
	return re.sub(r'[\\/:*?"<>|]', "_", " ".join(n.split()))


def region_entries(text):
	"""[(label, lower-case key)] from the typed list (';' between them)."""
	out = []
	for e in re.split(r"[;\n]", text or ""):
		e = clean_name(e)
		if e and e.lower() not in [k for _l, k in out]:
			out.append((e, e.lower()))
	return out


def region_side(name):
	"""(region name without its side marker, "L" / "R" / "")."""
	side, how = _hemisphere_detail(name)
	if side is None:
		return name, ""
	if how == "suffix":
		pats = [side == "left" and HEMISPHERE_SUFFIX_LEFT or HEMISPHERE_SUFFIX_RIGHT]
	else:
		pats = side == "left" and LEFT_FALLBACK_PATTERNS or RIGHT_FALLBACK_PATTERNS
	base = name
	for p in pats:
		base = re.compile(p, re.I).sub(" ", base)
	return " ".join(base.split()).strip(" -_,") or name, side[0].upper()


def region_groups():
	return dict([(k.lower(), [clean_name(m).lower() for m in v])
	             for k, v in REGION_GROUPS.items()])


def region_matches(key, order):
	"""Regions of order an entry names: a REGION_GROUPS group (and its
	"<name>, ..." parts), else that exact name, else a word start."""
	low = [r.lower() for r in order]
	want = region_groups().get(key)
	if want:
		return [r for r, l in zip(order, low)
		        if l in want or [w for w in want if l.startswith(w + ", ")]]
	if key in low:
		return [order[low.index(key)]]
	word = re.compile(r"(^|\W)" + re.escape(key), re.I)
	return [r for r in order if word.search(r)]


def _join(pieces):
	"""One new ROI from a region's pieces."""
	if len(pieces) == 1:
		return pieces[0].clone()
	return _union_roi_list(pieces)[0]


class SectionRegions(object):
	"""A section's regions: pieces by side, outlines, containment."""

	def __init__(self, rois):
		self.order, self.parts, self._whole, self._info = [], {}, {}, {}
		for n, roi in rois.items():
			reg, side = region_side(clean_name(roi.getProperty("contour") or n))
			k = reg.lower()
			if k not in self.parts:
				self.order.append(reg)
				self.parts[k] = {"L": [], "R": [], "": []}
			self.parts[k][side].append(roi)

	def pieces(self, regs, sides="LR"):
		out = []
		for r in regs:
			for s in sides:
				out.extend(self.parts[r.lower()][s])
		return out

	def whole(self, reg):
		k = reg.lower()
		if k not in self._whole:
			self._whole[k] = _join(self.pieces([reg], ("L", "R", "")))
		return self._whole[k]

	def info(self, reg):
		k = reg.lower()
		if k not in self._info:
			self._info[k] = _mask_info(self.whole(reg))
		return self._info[k]

	def inside(self, a, b):
		"""PARENT_ENCLOSED_FRACTION of a's area is in b."""
		ia, ib = self.info(a), self.info(b)
		ba, bb = ia[0], ib[0]
		x0, y0 = max(ba.x, bb.x), max(ba.y, bb.y)
		x1 = min(ba.x + ba.width, bb.x + bb.width)
		y1 = min(ba.y + ba.height, bb.y + bb.height)
		need = PARENT_ENCLOSED_FRACTION * ia[2]
		if ia[2] <= 0 or x1 <= x0 or y1 <= y0 or (x1 - x0) * (y1 - y0) < need:
			return False
		return _shared_px(ia, ib) >= need

	def outermost(self, regs, rank=None):
		"""Regions of regs in no other. Of two in each other, the one
		ranked first (a group's order), else the larger, else the first."""
		out = []
		for i, a in enumerate(regs):
			for j, b in enumerate(regs):
				if i == j or not self.inside(a, b):
					continue
				ka = (rank and rank(a), -self.info(a)[2], i)
				if not self.inside(b, a) or (rank and rank(b), -self.info(b)[2], j) < ka:
					break
			else:
				out.append(a)
		return out

	def outlines(self):
		"""Sideless regions enclosing both sides (a Tissue outline)."""
		out = []
		for u in self.order:
			p = self.parts[u.lower()]
			if p["L"] or p["R"]:
				continue
			sides = set()
			for r in self.order:
				q = self.parts[r.lower()]
				if r != u and (q["L"] or q["R"]) and self.inside(r, u):
					sides.update([s for s in "LR" if q[s]])
			if len(sides) == 2:
				out.append(u)
		return out


def add_region(out, label, regs, sr, notes, sideless):
	"""Add region label (regs joined) as label-L / label-R and / or label."""
	sided = sr.pieces(regs, "LR")
	loose = sr.pieces(regs, ("",))
	if sided and not HEMI_TOGETHER:
		for s in "LR":
			if sr.pieces(regs, s):
				out["%s-%s" % (label, s)] = _join(sr.pieces(regs, s))
		if loose and not HEMI_BOTH:
			notes.append("%s: %d piece(s) without -L / -R are left out of %s-L "
			             "and %s-R" % (label, len(loose), label, label))
	if HEMI_TOGETHER or HEMI_BOTH or not sided:
		out[label] = (len(regs) == 1 and sr.whole(regs[0]).clone()
		              or _join(sided + loose))
		if not sided and not HEMI_TOGETHER:
			sideless.append(label)
	for n in out:
		out[n].setName(n)


def region_composition(rois, ctx):
	"""'Separate brain regions'. Returns (dict, [notes])."""
	sr = SectionRegions(rois)
	out, notes, wanted, missing, sideless = _SafeRoiDict(ctx), [], [], [], []
	entries = region_entries(globals().get("brainRegions"))
	groups = region_groups()
	if entries:
		for label, key in entries:
			g = groups.get(key, [])
			rank = g and (lambda r: min([k for k, m in enumerate(g)
			                             if r.lower() == m or r.lower().startswith(m + ", ")]))
			hits = sr.outermost(region_matches(key, sr.order), rank)
			if hits:
				REGIONS_FOUND.add(key)
				wanted.append((label, hits))
				if [h for h in hits if h.lower() != key]:
					notes.append("%s = %s" % (label, " + ".join(hits)))
			else:
				missing.append(label)
	else:
		skip = sr.outlines()
		if skip:
			notes.append("left out (encloses both hemispheres): %s"
			             % _short_list(skip, 5))
		wanted = [(r, [r]) for r in sr.outermost([r for r in sr.order
		                                          if r not in skip])]
	taken = set([h.lower() for _l, hs in wanted for h in hs])
	for label, hits in wanted:
		add_region(out, label, hits, sr, notes, sideless)
		if globals().get("withSubregions"):
			for r in sr.order:
				if r.lower() not in taken and [h for h in hits if sr.inside(r, h)]:
					taken.add(r.lower())
					add_region(out, r, [r], sr, notes, sideless)
	if sideless:
		notes.append("no -L / -R in the contour names, so one ROI covers both "
		             "sides: %s" % _short_list(sideless, 6))
	if missing:
		notes.append("not in this section: %s" % ", ".join(missing))
	notes.append("%d ROI(s) for %d region(s)%s"
	             % (len(out), len(wanted), globals().get("withSubregions")
	                and " and their subregions" or ""))
	return out, notes


def region_preview(paths):
	"""Check-settings lines on the region list (from the XML names)."""
	from xml.sax.saxutils import unescape
	per_file, every = [], []
	for p in paths:
		try:
			with open(p) as fh:
				txt = fh.read().decode("latin-1")    # NeuroInfo: ISO-8859-1
		except IOError:
			continue
		regs = []
		for n in re.findall(r'<contour\b[^>]*?\bname="([^"]*)"', txt):
			r = region_side(clean_name(unescape(n, {"&apos;": "'", "&quot;": '"'})))[0]
			regs += [r][:r not in regs]
			every += [r][:r.lower() not in [e.lower() for e in every]]
		per_file.append(regs)
	lines = ["    regions: %s; hemispheres: %s%s" % (
			brainRegions or "the outermost of each section", hemispheres,
			withSubregions and "; every subregion too" or "")]
	for label, key in region_entries(brainRegions):
		n = len([1 for regs in per_file if region_matches(key, regs)])
		lines.append(n and "    %s: in %d of %d file(s) (%s)" % (label, n, len(per_file),
				_short_list(region_matches(key, every), 6)) or "! Region '%s' matches no "
				"contour name in the XML file(s); check its spelling against the names "
				"in the Log." % label)
	IJ.log("Region names in the XML files (for 'regions to count'):")
	for r in sorted(every, key=lambda x: x.lower()):
		IJ.log("    %s" % r)
	return lines
# ---- END SHARED: brain_regions ----


_warnings_this_file = []


def warn(ctx, message):
	_warnings_this_file.append(message)
	IJ.log("      ! %s" % message)


class _SafeRoiDict(OrderedDict):
	"""Ordered dict with an informative error on a missing ROI name."""

	def __init__(self, ctx):
		OrderedDict.__init__(self)
		self._ctx = ctx

	def __getitem__(self, key):
		if key not in self:
			shown = _short_list(sorted(self.keys()), 40)
			raise CompositionError(
			    "composition asked for the ROI named '%s', which is not in %s.\n"
			    "  Check the spelling against the XML's name= attribute.\n"
			    "  Names present in this file: %s"
			    % (key, self._ctx.get("file", "?"), shown))
		return OrderedDict.__getitem__(self, key)


# ------------------------------------------------------------ parse XML
XML_WARNED = set()      # files whose <image> blocks disagree, logged once
XML_MISMATCH = []       # their messages, for the Check settings window


def parse_xml(path):
	try:
		fh = open(path)
		try:
			raw = fh.read()
		finally:
			fh.close()
	except IOError, e:
		raise ValueError("could not be read from disk (%s)" % str(e))

	if not raw.strip():
		raise ValueError("the file is empty (0 bytes of content)")

	# Strip the XML namespaces so findall() stays simple.
	raw = re.sub(r'\sxmlns(:[A-Za-z0-9_]+)?="[^"]*"', '', raw)
	raw = re.sub(r'<(/?)[A-Za-z0-9_]+:', r'<\1', raw)

	try:
		root = ET.fromstring(raw)
	except ANY_ERROR, e:
		raise ValueError(
		    "is not valid XML (%s).\n"
		    "  A truncated export from NeuroInfo looks exactly like this. "
		    "Try re-exporting it." % str(e))

	all_imgs = root.findall('.//images/image')
	img = all_imgs[0] if all_imgs else None
	if len(all_imgs) > 1:
		IJ.log("      . note: %s has %d <images><image> blocks; the first "
		       "was used for the scale and origin"
		       % (os.path.basename(path), len(all_imgs)))
	if img is None:
		raise ValueError(
		    "has no <images><image> block, so there is no scale or origin to "
		    "convert micrometres to pixels.\n  Re-export from NeuroInfo with "
		    "the section image loaded.")

	scale_el = img.find('scale')
	coord_el = img.find('coord')
	if scale_el is None:
		raise ValueError("has an <image> block with no <scale> element")
	if coord_el is None:
		raise ValueError("has an <image> block with no <coord> element")

	try:
		sx = abs(float(scale_el.get('x')))
		sy = abs(float(scale_el.get('y')))
		ox = float(coord_el.get('x'))
		oy = float(coord_el.get('y'))
	except (TypeError, ValueError), e:
		raise ValueError("has an unreadable <scale> or <coord> value (%s)" % str(e))

	if sx == 0 or sy == 0:
		raise ValueError(
		    "reports a scale of zero um/pixel, which cannot be used. "
		    "The image calibration in NeuroInfo is probably unset.")
	for other in all_imgs[1:]:
		try:
			o = [abs(float(other.find('scale').get(c))) for c in 'xy'] + \
			    [float(other.find('coord').get(c)) for c in 'xy']
		except ANY_ERROR:
			continue
		if (abs(o[0] - sx) > 1e-4 * sx or abs(o[1] - sy) > 1e-4 * sy
		        or abs(o[2] - ox) > 0.01 or abs(o[3] - oy) > 0.01) \
		        and path not in XML_WARNED:
			XML_WARNED.add(path)
			XML_MISMATCH.append(
			    "%s: another <image> block (%s) has a different scale or origin "
			    "(%.6f, %.6f um/px at %.3f, %.3f) from the first (%.6f, %.6f at "
			    "%.3f, %.3f), which was used. Check the ROIs on the image with 4 "
			    "Build Pipeline Composite."
			    % (os.path.basename(path), other.findtext('filename') or "?",
			       o[0], o[1], o[2], o[3], sx, sy, ox, oy))
			IJ.log("      ! WARNING: " + XML_MISMATCH[-1])

	return root, sx, sy, ox, oy


def raw_scale_x(root):
	"""The XML's x scale with its sign (a negative one means mirrored)."""
	try:
		imgs = root.findall('.//images/image')
		return float(imgs[0].find('scale').get('x'))
	except ANY_ERROR:
		return None


def contour_names(root):
	"""Raw contour names as they appear in the XML, in document order."""
	return [c.get('name') or '(unnamed)' for c in root.findall('.//contour')]


# ----------------------------------------------------------- validation
def validate(names, expected, stage, ctx):
	"""Return a list of human-readable problem strings. Empty list = clean."""
	problems = []

	counts = {}
	for n in names:
		counts[n] = counts.get(n, 0) + 1

	if expected:
		missing = [e for e in expected if e not in counts]
		if missing:
			problems.append(
			    "%s: %d expected ROI(s) MISSING: %s"
			    % (stage, len(missing), ", ".join(missing)))

		if FLAG_UNEXPECTED:
			unexpected = [n for n in sorted(counts.keys()) if n not in expected]
			if unexpected:
				problems.append(
				    "%s: %d UNEXPECTED ROI(s) present: %s"
				    % (stage, len(unexpected), ", ".join(unexpected[:20])
				       + (", ..." if len(unexpected) > 20 else "")))

	if MAX_PIECES_PER_NAME > 0:
		toomany = ["%s x%d" % (n, c) for n, c in counts.items()
		           if c > MAX_PIECES_PER_NAME]
		if toomany:
			problems.append(
			    "%s: name(s) split into more pieces than MAX_PIECES_PER_NAME "
			    "(%d): %s" % (stage, MAX_PIECES_PER_NAME, ", ".join(toomany)))

	if not names:
		problems.append("%s: the ROI set is EMPTY - nothing to write" % stage)

	return problems


# ------------------------------------------------------------ build ROIs
def build_rois(root, sx, sy, ox, oy, ctx):
	rois = _SafeRoiDict(ctx)
	seen = {}
	short = 0
	degenerate = []

	for contour in root.findall('.//contour'):
		raw_name = contour.get('name') or 'contour'
		pts = contour.findall('point')

		if len(pts) < 3:
			short += 1
			degenerate.append("%s (%d point(s))" % (raw_name, len(pts)))
			continue

		xs, ys, bad = [], [], False
		for p in pts:
			try:
				x_um = float(p.get('x'))
				y_um = float(p.get('y'))
			except (TypeError, ValueError):
				bad = True
				break
			xs.append((x_um - ox) / sx)
			ys.append(((oy - y_um) if Y_FLIP else (y_um - oy)) / sy)

		if bad:
			degenerate.append("%s (unreadable point coordinates)" % raw_name)
			short += 1
			continue

		roi = PolygonRoi(array(xs, 'f'), array(ys, 'f'), len(xs), Roi.POLYGON)

		name = re.sub(r'[\\/:*?"<>|]', '_', raw_name).strip() or 'contour'
		base_name = name        # before a piece number is added
		seen[name] = seen.get(name, 0) + 1
		if name in rois:
			# A repeated name becomes a piece name_2, name_3, ... (first unused)
			k = max(2, seen[name])
			while "%s_%d" % (name, k) in rois:
				k += 1
			name = "%s_%d" % (name, k)
		roi.setName(name)
		roi.setProperty("contour", base_name)

		hexcol = contour.get('color')
		if hexcol and hexcol.startswith('#'):
			try:
				roi.setStrokeColor(Color.decode(hexcol))
			except ANY_ERROR:
				pass

		rois[name] = roi

	return rois, short, degenerate


# ------------------------------------------------------ parameter record
def config_record_items():
	"""Every configuration constant that affects the result, for the record."""
	return [("#Configuration", ""), ("OUTPUT_SUFFIX", repr(OUTPUT_SUFFIX))] + [
	    (n, globals()[n]) for n in (
	        "EXPECTED_ROIS MAX_PIECES_PER_NAME FLAG_UNEXPECTED "
	        "LIST_NAMES_ON_FIRST_FILE EXPECTED_ROIS_AFTER_MATH REGION_GROUPS UNIFIED_ROI_NAME "
	        "HEMI_LEFT_NAME HEMI_RIGHT_NAME HEMI_UNPAIRED_NAME "
	        "HEMISPHERE_SUFFIX_LEFT HEMISPHERE_SUFFIX_RIGHT LEFT_FALLBACK_PATTERNS "
	        "RIGHT_FALLBACK_PATTERNS PARENT_ENCLOSED_FRACTION UNIFY_INCLUDE_NAMES "
	        "UNIFY_EXCLUDE_NAMES UNION_METHOD UNION_RASTER_MIN_ROIS "
	        "UNION_RASTER_MAX_PIXELS WRITE_PARAMETER_RECORD "
	        "CONFIRM_BEFORE_RUN").split()]


# ------------------------------------------------ Check settings window
def _warning(text):
	"""A wrapped '!' warning line for confirm_settings."""
	import textwrap
	return "!" + textwrap.fill(text, 88, subsequent_indent="    ",
	                           break_long_words=False,
	                           break_on_hyphens=False)


def _overlapping_pairs(rois):
	"""[(a, b, b (almost) all inside a)] of overlapping ROIs, on a grid of
	about 1500 x 1500 pixels."""
	from ij.plugin import RoiScaler
	items = list(rois.items())
	if len(items) < 2:
		return []
	bounds = [r.getBounds() for _n, r in items]
	span = max(max([b.x + b.width for b in bounds]) - min([b.x for b in bounds]),
	           max([b.y + b.height for b in bounds]) - min([b.y for b in bounds]))
	f = 1.0
	if span > 1500:
		f = 1500.0 / span
	masks = []
	for n, r in items:
		s = RoiScaler.scale(r, f, f, False) if f < 1.0 else r
		b = s.getBounds()
		if b.width > 0 and b.height > 0:
			masks.append((n,) + _mask_info(s))
	pairs = []
	for i in range(len(masks)):
		na, ba, ma, aa = masks[i]
		for j in range(i + 1, len(masks)):
			nb, bb, mb, ab = masks[j]
			if aa == 0 or ab == 0:
				continue
			shared = _shared_px((ba, ma, aa), (bb, mb, ab))
			smaller = min(aa, ab)
			if shared <= max(2, 0.01 * smaller):
				continue          # touching borders, not a real overlap
			if shared < 0.95 * smaller:
				pairs.append((na, nb, False))
			else:
				pairs.append((na, nb, True) if aa >= ab else (nb, na, True))
	return pairs


def first_file_lines(path):
	"""(info_lines, warning_lines) about an XML (converted in memory)."""
	fname = os.path.basename(path)
	info, warns = [], []
	try:
		root, sx, sy, ox, oy = parse_xml(path)
	except ValueError, e:
		msg = " ".join(str(e).split())
		if msg.startswith("the file "):
			msg = msg[len("the file "):]
		warns.append(_warning("Problem with the first file, %s: it %s. It "
		                      "will be reported as FAILED."
		                      % (fname, msg.rstrip("."))))
		return info, warns
	except ANY_ERROR, e:
		warns.append(_warning("The first file, %s, could not be read (%s: %s)."
		                      % (fname, type(e).__name__, str(e))))
		return info, warns

	info.append("Scale in %s: %.4f x %.4f um/pixel, origin (%.1f, %.1f) um"
	            % (fname, sx, sy, ox, oy))
	info.append("    (read from the XML; it sets the size and position of every ROI)")

	raw_names = contour_names(root)
	uniq = []
	for n in raw_names:
		if n not in uniq:
			uniq.append(n)
	shown = _short_list(uniq)
	info.append("Contours in %s: %d, with %d different name(s):"
	            % (fname, len(raw_names), len(uniq)))
	info.append("    " + (shown or "(none)"))

	if ACTION_WARN:
		then = "files like this are still converted, with a warning in the Log"
	elif ACTION_SKIP:
		then = "files like this are skipped and get no .zip"
	else:
		then = "the run stops at the first file like this"
	problems = validate(raw_names, EXPECTED_ROIS, "names", {"file": fname})
	if problems:
		warns.append(_warning("%s does not pass the name check (%s). With "
		                      "'On validation problem' set to '%s', %s."
		                      % (fname, "; ".join(problems), validationAction,
		                         then)))

	try:
		rois, _short, degenerate = build_rois(root, sx, sy, ox, oy,
		                                      {"file": fname})
	except ANY_ERROR, e:
		warns.append(_warning("The contours in %s could not be converted (%s: "
		                      "%s)." % (fname, type(e).__name__, str(e))))
		return info, warns
	if degenerate:
		warns.append(_warning("%d contour(s) in %s have fewer than 3 usable "
		                      "points and will be dropped: %s."
		                      % (len(degenerate), fname,
		                         "; ".join(degenerate[:3]))))

	negx = negative_x_message(raw_scale_x(root))
	if negx:
		warns.append(_warning("In %s, %s" % (fname, negx)))
	offmsg = off_image_message(rois, "in " + fname)
	if offmsg:
		warns.append(_warning(offmsg))
	side = left_side_of(rois)
	if side:
		info.append("Left regions in %s are on the image's %s side"
		            % (fname, side))

	if COMPOSE_NONE and len(rois) > 1:
		pairs = _overlapping_pairs(rois)
		if pairs:
			ex = [("'%s' lies inside '%s'" % (b, a)) if inside else
			      ("'%s' and '%s' overlap" % (a, b)) for a, b, inside in pairs[:3]]
			warns.append(_warning(
			    "Some ROIs in %s overlap or lie inside one another (%d "
			    "pair(s), e.g. %s): stage 3 counts a particle in each, so the "
			    "columns do not add up to total_particles. For one count per "
			    "brain region, choose 'Separate brain regions'."
			    % (fname, len(pairs), "; ".join(ex))))

	if (COMPOSE_HEMI2 or COMPOSE_HEMI3) and rois:
		names = apply_unify_filters(list(rois.keys()))
		left, right, unpaired, both = _split_sides(names)
		if names and not left and not right:
			warns.append(_warning(
			    "No contour name in %s has a -L / -R suffix or a "
			    "left/right word, so the hemisphere mode makes one ROI per file. "
			    "Check that the hemispheres were separated in the export." % fname))
		else:
			parents = _parent_outlines(rois, left, right, unpaired)
			midline = [n for n in unpaired if n not in parents]
			if unpaired:
				info.append("Unpaired in %s: %s" % (fname, _short_list(unpaired)))
			if parents:
				info.append("    %s %s both hemispheres and will be left out "
				            "of the hemisphere ROIs"
				            % (_short_list(parents, 5),
				               "encloses" if len(parents) == 1 else "enclose"))
			if both:
				warns.append(_warning(
				    "%d name(s) in %s match both a left and a right pattern "
				    "and will be treated as unpaired: %s."
				    % (len(both), fname, _short_list(both, 5))))
			if COMPOSE_HEMI2 and midline:
				warns.append(_warning(
				    "%d region(s) in %s have no left/right marker and will be "
				    "added to BOTH the left and the right ROI (counted twice)." % (len(midline), fname)))

	if COMPOSE_CODED and rois:
		before = list(rois.items())
		try:
			del _warnings_this_file[:]
			result = compose_rois(rois, {"file": fname, "scale_x": sx,
			                             "scale_y": sy, "origin_x": ox,
			                             "origin_y": oy})
			del _warnings_this_file[:]
			if result is None:
				result = rois
			if hasattr(result, "items"):
				after = list(result.items())
				same = (len(after) == len(before) and
				        all([a[0] == b[0] and a[1] is b[1]
				             for a, b in zip(after, before)]))
				if same:
					warns.append(_warning(
					    "The composition coded in this script left the ROIs "
					    "of %s unchanged: compose_rois() may still be the "
					    "unedited template." % fname))
		except ANY_ERROR, e:
			del _warnings_this_file[:]
			warns.append(_warning(
			    "The composition coded in this script fails on %s (%s: %s). "
			    "Files where it fails are reported as FAILED."
			    % (fname, type(e).__name__, " ".join(str(e).split()))))
	return info, warns



# ================================================================= BATCH
if not os.path.isdir(IN_DIR):
	IJ.error("Input folder",
	         "The input folder does not exist:\n%s\n\nChoose the folder that "
	         "holds the NeuroInfo .xml exports (usually xml/)." % IN_DIR)
	raise SystemExit

names_in = [f for f in os.listdir(IN_DIR)
            if fnmatch.fnmatch(f, filePattern)
            and os.path.isfile(os.path.join(IN_DIR, f))]
names_in.sort()   # zero-padded numbering means lexical sort is correct

if not names_in:
	any_xml = [f for f in os.listdir(IN_DIR) if f.lower().endswith('.xml')]
	extra = ""
	if any_xml:
		extra = ("\n\nThere ARE .xml files in that folder, e.g.:\n  %s\n"
		         "Adjust the filename pattern to match."
		         % "\n  ".join(sorted(any_xml)[:5]))
	IJ.error("No input files",
	         "No files matching the filename pattern '%s' in:\n%s%s"
	         % (filePattern, IN_DIR, extra))
	raise SystemExit

_ON = re.sub(r'[\\/:*?"<>|]', "_", (outFolderName or "").strip() or "rois").strip() or "rois"
_OUT_EXISTED = os.path.isdir(os.path.join(outParentDir is not None and outParentDir.getAbsolutePath()
                             or os.path.dirname(os.path.normpath(IN_DIR)), _ON))
OUT_DIR = resolve_output_dir(IN_DIR, outFolderName, "rois", outParentDir)
if OUT_DIR is None:
	raise SystemExit

# ---- Check settings window: say what is about to happen, then Run / Cancel
_others = sorted([f for f in os.listdir(IN_DIR)
                  if f not in names_in and not f.startswith(".")
                  and os.path.isfile(os.path.join(IN_DIR, f))])
_other_xml = [f for f in _others if f.lower().endswith(".xml")]
def reviewed_zips(out_dir):
	"""Names of ROI sets edited in 2a.i Review (from its log in out_dir)."""
	try:
		import csv
		fh = open(os.path.join(out_dir, "_roi_review_log.csv"), "rb")
		try:
			return set([r[1] for r in list(csv.reader(fh))[1:] if len(r) > 1])
		finally:
			fh.close()
	except (IOError, OSError):
		return set()


def keep_reviewed(path):
	"""Copy a reviewed set to _before_review/<name>_reviewed_<time>.zip."""
	import shutil
	import time
	d = os.path.join(os.path.dirname(path), "_before_review")
	if not os.path.isdir(d):
		os.makedirs(d)
	dst = os.path.join(d, "%s_reviewed_%s.zip" % (os.path.splitext(
	    os.path.basename(path))[0], time.strftime("%Y%m%d_%H%M%S")))
	shutil.copy2(path, dst)
	IJ.log("    reviewed ROI set kept as %s" % dst)


_existing = [f for f in names_in
             if os.path.exists(os.path.join(
                 OUT_DIR, os.path.splitext(f)[0] + OUTPUT_SUFFIX + ".zip"))]
_nokey = [f for f in names_in
          if not re.search(PAIRING_KEY_PATTERN, os.path.splitext(f)[0])]

check_lines = []
check_lines.append("Input folder: %s" % IN_DIR)
check_lines.append("XML files to convert: %d (matching '%s')"
                   % (len(names_in), filePattern))
if _others:
	check_lines.append("Left out (not matching the pattern): %d file(s), e.g. %s"
	                   % (len(_others), ", ".join(_others[:3])))
check_lines.append("Output folder: %s" % OUT_DIR)
check_lines.append("Example: %s -> %s.zip"
                   % (names_in[0], os.path.splitext(names_in[0])[0] + OUTPUT_SUFFIX))
if _existing and skipExisting:
	check_lines.append("Already converted: %d of %d file(s) have a .zip and "
	                   "will be skipped" % (len(_existing), len(names_in)))
elif not _existing:
	check_lines.append("No .zip exists yet for these files.")
check_lines.append("Y axis: %s" % yMode)
check_lines.append("ROI composition: %s" % compositionMode)
if COMPOSE_REGIONS:
	check_lines.extend(region_preview([os.path.join(IN_DIR, f) for f in names_in]))
if (COMPOSE_UNIFY or COMPOSE_HEMI2 or COMPOSE_HEMI3):
	if UNIFY_INCLUDE_NAMES:
		check_lines.append("    only these regions take part: %s"
		                   % ", ".join(UNIFY_INCLUDE_NAMES))
	if UNIFY_EXCLUDE_NAMES:
		check_lines.append("    these regions are left out: %s"
		                   % ", ".join(UNIFY_EXCLUDE_NAMES))
check_lines.append("On validation problem: %s" % validationAction)
if EXPECTED_ROIS:
	check_lines.append("Name check: against the %d name(s) in EXPECTED_ROIS"
	                   % len(EXPECTED_ROIS))
else:
	check_lines.append("Name check: off (EXPECTED_ROIS is empty)")
if EXPECTED_ROIS_AFTER_MATH:
	check_lines.append("Check after composition: %d name(s) in "
	                   "EXPECTED_ROIS_AFTER_MATH" % len(EXPECTED_ROIS_AFTER_MATH))
_info, _warns = first_file_lines(os.path.join(IN_DIR, names_in[0]))
check_lines.extend(_info)
check_lines.extend(_warns)
check_lines.extend([_warning(m) for m in XML_MISMATCH])
_REVIEWED = reviewed_zips(OUT_DIR)
_rev = [os.path.splitext(f)[0] + OUTPUT_SUFFIX + ".zip" for f in _existing]
_rev = [z for z in _rev if z in _REVIEWED]
if _rev and not skipExisting:
	check_lines.append(_warning(
	    "%d of these ROI sets were edited in 2a.i Review (%s). Replacing them "
	    "loses those edits; each is first copied to _before_review/ as "
	    "<name>_reviewed_<time>.zip." % (len(_rev), ", ".join(_rev[:6]))))
if _existing and not skipExisting:
	check_lines.append(_warning(
	    "%d of the %d file(s) already have a .zip in the output folder; it "
	    "will be replaced from the XML, so any changes made to those ROI sets "
	    "by hand are lost. Tick 'Skip files whose .zip already exists' to "
	    "keep them." % (len(_existing), len(names_in))))
if _other_xml:
	check_lines.append(_warning(
	    "%d .xml file(s) in the input folder do not match the filename "
	    "pattern '%s' and will not be converted: %s."
	    % (len(_other_xml), filePattern, ", ".join(_other_xml[:3]))))
if _nokey and len(_nokey) == len(names_in):
	check_lines.append(_warning(
	    "None of the matched file names start with a RegionXXXX key (e.g. "
	    "%s). Later stages pair ROI sets with images by that key, so these "
	    "ROI sets will not be matched to any image." % _nokey[0]))
elif _nokey:
	check_lines.append(_warning(
	    "%d of the %d matched file names do not start with a RegionXXXX key "
	    "(e.g. %s). Later stages pair ROI sets with images by that key, so "
	    "those ROI sets will not be matched to any image."
	    % (len(_nokey), len(names_in), ", ".join(_nokey[:3]))))
if not confirm_settings(SCRIPT_NAME, experiment_lines(globals().get("_SLIDE") or IN_DIR) + check_lines, CONFIRM_BEFORE_RUN):
	if not _OUT_EXISTED and os.path.isdir(OUT_DIR) and not os.listdir(OUT_DIR):
		os.rmdir(OUT_DIR)      # created for this run only
	IJ.log("%s: cancelled at the settings check; nothing was processed."
	       % SCRIPT_NAME)
	raise SystemExit

IJ.log("=" * 64)
IJ.log("NeuroInfo XML -> RoiSet batch")
IJ.log("  in  : %s" % IN_DIR)
IJ.log("  out : %s" % OUT_DIR)
IJ.log("  %d file(s) matching '%s'" % (len(names_in), filePattern))
IJ.log("  Y flip: %s   |   on problem: %s" % (Y_FLIP, validationAction))
IJ.log("  composition: %s" % compositionMode)
if (COMPOSE_UNIFY or COMPOSE_HEMI2 or COMPOSE_HEMI3):
	if UNIFY_INCLUDE_NAMES:
		IJ.log("     including ONLY: %s" % ", ".join(UNIFY_INCLUDE_NAMES))
	if UNIFY_EXCLUDE_NAMES:
		IJ.log("     excluding: %s" % ", ".join(UNIFY_EXCLUDE_NAMES))
if EXPECTED_ROIS:
	IJ.log("  validating against %d expected ROI name(s)" % len(EXPECTED_ROIS))
else:
	IJ.log("  EXPECTED_ROIS is empty - input validation is OFF")
IJ.log("=" * 64)

log_rows = []
converted_files = []
failed_files = []
flagged_files = []
skipped_files = []
no_region_files = []    # sections with none of the regions: no zip
listed_names_already = False
stopped_early = False
left_side = {}          # stem -> "left" / "right": image side of the Left regions
stop_reason = ""

for i, fname in enumerate(names_in):
	stem = os.path.splitext(fname)[0]
	in_path = os.path.join(IN_DIR, fname)
	out_stem = stem + OUTPUT_SUFFIX
	out_path = os.path.join(OUT_DIR, out_stem + ".zip")

	del _warnings_this_file[:]

	if skipExisting and os.path.exists(out_path):
		IJ.log("[%d/%d] %s  SKIPPED (zip already exists)" % (i + 1, len(names_in), stem))
		skipped_files.append(stem)
		log_rows.append([stem, "no", "", "", "", "", "", "", "",
		                 "skipped - output already existed"])
		continue

	IJ.showProgress(i, len(names_in))
	IJ.showStatus("[%d/%d] %s - converting" % (i + 1, len(names_in), stem))
	existed_before = os.path.exists(out_path)

	ctx = {"file": fname}

	try:
		root, sx, sy, ox, oy = parse_xml(in_path)
		ctx.update({"scale_x": sx, "scale_y": sy, "origin_x": ox, "origin_y": oy})

		raw_names = contour_names(root)

		if LIST_NAMES_ON_FIRST_FILE and not listed_names_already:
			listed_names_already = True
			uniq = sorted(set(raw_names))
			IJ.log("")
			IJ.log("  --- contour names found in %s (%d unique) ---" % (stem, len(uniq)))
			for n in uniq:
				IJ.log('      "%s",' % n)
			IJ.log("  --- paste the ones you need into EXPECTED_ROIS ---")
			IJ.log("")

		problems = validate(raw_names, EXPECTED_ROIS, "in XML", ctx)

		rois, short, degenerate = build_rois(root, sx, sy, ox, oy, ctx)
		n_before = len(rois)

		if degenerate:
			problems.append(
			    "in XML: %d contour(s) dropped as unusable: %s"
			    % (len(degenerate), "; ".join(degenerate[:10])
			       + ("; ..." if len(degenerate) > 10 else "")))
		if n_before != len(raw_names) - short:
			problems.append(
			    "in XML: %d usable contour(s) but %d ROI(s) were built, so "
			    "a contour was lost (two names collided)"
			    % (len(raw_names) - short, n_before))

		negx = negative_x_message(raw_scale_x(root))
		if negx:
			problems.append("scale: " + negx)
		offmsg = off_image_message(rois, "")
		if offmsg:
			problems.append("position: " + offmsg)

		side = left_side_of(rois)
		if side:
			left_side[stem] = side
			IJ.log("      . Left regions are on the image's %s side" % side)

		# ---- ROI composition ----
		if COMPOSE_NONE:
			pass

		elif COMPOSE_CODED:
			try:
				result = compose_rois(rois, ctx)
			except (CompositionError, StepError), e:
				raise ValueError("coded composition failed.\n  %s" % str(e))
			except KeyError, e:
				raise ValueError(
				    "coded composition referred to a name that does not "
				    "exist: %s\n  Run once with EXPECTED_ROIS empty to print "
				    "the real names." % str(e))
			except ANY_ERROR, e:
				raise ValueError(
				    "coded composition raised an unexpected error: %s: %s"
				    % (type(e).__name__, str(e)))

			if result is not None:
				rois = result
			if not hasattr(rois, "items"):
				raise ValueError(
				    "compose_rois() returned a %s instead of a dict of "
				    "name -> Roi. Either mutate the dict in place and return "
				    "it, or return a new dict." % type(rois).__name__)

		else:
			try:
				rois, cnotes = built_in_composition(rois, ctx)
			except (CompositionError, StepError), e:
				raise ValueError("composition failed.\n  %s" % str(e))
			except ANY_ERROR, e:
				raise ValueError(
				    "composition raised an unexpected error: %s: %s"
				    % (type(e).__name__, str(e)))
			for cn in cnotes:
				IJ.log("      . %s" % cn)

		if COMPOSE_REGIONS and not rois:
			IJ.log("[%d/%d] %s  none of the regions is in this section: no .zip"
			       % (i + 1, len(names_in), stem))
			no_region_files.append(stem)
			if os.path.isfile(out_path):
				if os.path.basename(out_path) in _REVIEWED:
					keep_reviewed(out_path)
				os.remove(out_path)
				IJ.log("      the earlier %s.zip was removed, so later stages do "
				       "not count it" % out_stem)
			log_rows.append([stem, "no", str(len(raw_names)), str(n_before), "0",
			                 "%.6f" % sx, "%.6f" % sy, "%.3f" % ox, "%.3f" % oy,
			                 "none of the regions is in this section"])
			continue

		empties = [n for n, r in rois.items() if is_empty(r)]
		if empties:
			problems.append(
			    "after composition: %d ROI(s) have zero area and would be "
			    "unusable for counting: %s"
			    % (len(empties), ", ".join(empties[:10])))

		problems.extend(validate(list(rois.keys()), EXPECTED_ROIS_AFTER_MATH,
		                         "after composition", ctx))

		for w in _warnings_this_file:
			problems.append("from compose_rois(): %s" % w)

		# ---- act on problems ----
		if problems:
			IJ.log("[%d/%d] %s  PROBLEM(S):" % (i + 1, len(names_in), stem))
			for p in problems:
				IJ.log("      - %s" % p)
			flagged_files.append(stem)

			if ACTION_STOP:
				stopped_early = True
				stop_reason = ("%s failed validation:\n\n%s"
				               % (stem, "\n".join(["- " + p for p in problems])))
				log_rows.append([stem, "no", str(len(raw_names)), str(n_before),
				                 str(len(rois)), "%.6f" % sx, "%.6f" % sy,
				                 "%.3f" % ox, "%.3f" % oy,
				                 "STOPPED: " + " | ".join(problems)])
				break

			if ACTION_SKIP:
				IJ.log("      -> skipped, no zip written")
				log_rows.append([stem, "no", str(len(raw_names)), str(n_before),
				                 str(len(rois)), "%.6f" % sx, "%.6f" % sy,
				                 "%.3f" % ox, "%.3f" % oy,
				                 "skipped on validation: " + " | ".join(problems)])
				continue

			IJ.log("      -> converting anyway (warn mode)")

		if not rois:
			raise ValueError("there are no ROIs left to write")

		for _n, _r in rois.items():      # the pixel size, for areas in stage 3
			_r.setProperty("um_per_px", "%.6f,%.6f" % (sx, sy))
		IJ.showStatus("[%d/%d] %s - writing" % (i + 1, len(names_in), stem))
		if os.path.basename(out_path) in _REVIEWED and os.path.isfile(out_path):
			keep_reviewed(out_path)
		try:
			write_roiset(rois, out_path)
		except StepError:
			# do not leave a half-written zip behind for later stages
			try:
				os.remove(out_path)
			except OSError:
				pass
			raise
		converted_files.append(out_stem)

		note = "ok" if not problems else "converted WITH WARNINGS"
		IJ.log("[%d/%d] %s  ->  %s.zip   %d ROI(s)   %.4f um/px%s"
		       % (i + 1, len(names_in), stem, out_stem, len(rois), sx,
		          "   (replaced the existing zip)" if existed_before else ""))

		log_rows.append([stem, "yes", str(len(raw_names)), str(n_before),
		                 str(len(rois)), "%.6f" % sx, "%.6f" % sy,
		                 "%.3f" % ox, "%.3f" % oy,
		                 note if not problems else note + ": " + " | ".join(problems)])

	except (ValueError, StepError), e:
		failed_files.append(stem)
		IJ.log("[%d/%d] %s  FAILED: %s" % (i + 1, len(names_in), stem, str(e)))
		log_rows.append([stem, "no", "", "", "", "", "", "", "",
		                 "FAILED: " + str(e).replace("\n", " ")])
		if ACTION_STOP:
			stopped_early = True
			stop_reason = "%s failed:\n\n%s" % (stem, str(e))
			break

	except ANY_ERROR, e:
		failed_files.append(stem)
		msg = "%s: %s" % (type(e).__name__, str(e))
		IJ.log("[%d/%d] %s  UNEXPECTED ERROR: %s" % (i + 1, len(names_in), stem, msg))
		log_rows.append([stem, "no", "", "", "", "", "", "", "",
		                 "UNEXPECTED ERROR: " + msg.replace("\n", " ")])
		if ACTION_STOP:
			stopped_early = True
			stop_reason = "%s raised an unexpected error:\n\n%s" % (stem, msg)
			break

IJ.showProgress(1.0)
IJ.showStatus("")


# --------------------------------------------- left / right side check
# Every file with both -L and -R regions says which side of the image its
# Left regions are on. A section flipped in NeuroInfo exports contours that
# are mirrored relative to the image, and nothing else in the pipeline
# notices on a roughly symmetric section, so files that disagree with the
# others are flagged here.
MIRROR_TEXT = ("Left/Right on the opposite side from the other sections: the "
               "section may have been flipped in NeuroInfo, so its contours may "
               "be mirrored relative to the image. Check it with 4 Build "
               "Pipeline Composite before counting.")
mirrored_files = []
side_summary = None
_n_l = sorted([k for k, v in left_side.items() if v == "left"])
_n_r = sorted([k for k, v in left_side.items() if v == "right"])
if _n_l or _n_r:
	if len(_n_l) > len(_n_r):
		majority, mirrored_files = "left", _n_r
	elif len(_n_r) > len(_n_l):
		majority, mirrored_files = "right", _n_l
	else:
		majority, mirrored_files = None, sorted(_n_l + _n_r)
	if majority:
		side_summary = ("Left side : Left regions on the image's %s side in "
		                "%d of %d section(s)"
		                % (majority, max(len(_n_l), len(_n_r)),
		                   len(_n_l) + len(_n_r)))
	else:
		side_summary = ("Left side : no majority, Left regions on the image's "
		                "left side in %d and right side in %d section(s)"
		                % (len(_n_l), len(_n_r)))
	if mirrored_files:
		IJ.log("")
		for st in mirrored_files:
			IJ.log("WARNING: %s: Left regions on the image's %s side. %s"
			       % (st, left_side[st], MIRROR_TEXT))
			if st not in flagged_files:
				flagged_files.append(st)
			for r in log_rows:
				if r[0] == st:
					r[-1] = str(r[-1]) + " | " + MIRROR_TEXT


log_path = None
if writeLog:
	# 2a has no Overwrite option, so each run gets its own debug log
	# (timestamped) instead of replacing an earlier one.
	import time as _time
	log_path = os.path.join(OUT_DIR, "_conversion_log_%s.csv"
	                        % _time.strftime("%Y%m%d-%H%M%S"))
	try:
		fh = open(log_path, "w")
		try:
			fh.write("file,converted,contours_in_xml,rois_before_math,"
			         "rois_written,scale_x_um_px,scale_y_um_px,"
			         "origin_x_um,origin_y_um,status,left_regions_on_image_side\n")
			for r in log_rows:
				col = left_side.get(r[0], "")
				if col and r[0] in mirrored_files:
					col += " (OPPOSITE from the other sections)"
				fh.write(",".join(['"%s"' % str(c).replace('"', "'")
				                   for c in r + [col]]) + "\n")
		finally:
			fh.close()
		IJ.log("Log written: %s" % log_path)
	except IOError, e:
		log_path = None
		IJ.log("WARNING: could not write the log CSV: %s" % str(e))


record_path = None
if WRITE_PARAMETER_RECORD:
	items = [("#Dialog", "")] + layout_record() + [
	         ("Folder of NeuroInfo XML files (xml/)", IN_DIR),
	         ("Output location (blank = one level above the input)", outParentDir.getAbsolutePath()
	          if outParentDir is not None else "(blank)"),
	         ("Name for the new output folder", outFolderName),
	         ("Filename pattern", filePattern),
	         ("Y axis", yMode),
	         ("ROI composition", compositionMode),
	         ("   regions to count, separated by ; (blank = every outermost region)",
	          globals().get("brainRegions") or ""),
	         ("   also count each subregion inside them separately",
	          bool(globals().get("withSubregions"))),
	         ("   hemispheres", globals().get("hemispheres") or ""),
	         ("On validation problem", validationAction),
	         ("Skip files whose .zip already exists", skipExisting),
	         ("Write a summary CSV to the output folder", writeLog)]
	items.extend(config_record_items())
	items.append(("#Inputs", ""))
	items.append(("input folder", IN_DIR))
	items.append(("output folder", OUT_DIR))
	for k, fname in enumerate(names_in):
		items.append(("file %d" % (k + 1), os.path.join(IN_DIR, fname)))
	items.append(("#Results", ""))
	items.append(("converted", len(converted_files)))
	items.append(("flagged", len(flagged_files)))
	items.append(("failed", len(failed_files)))
	items.append(("skipped", len(skipped_files)))
	items.append(("sections without the regions", ", ".join(no_region_files) or "none"))
	items.append(("left regions on image side", side_summary or "(not checked)"))
	items.append(("possibly mirrored sections", ", ".join(mirrored_files) or "none"))
	items.append(("stopped early", stopped_early))
	record_path = write_run_record(OUT_DIR, SCRIPT_NAME, SCRIPT_VERSION, items)
	if record_path:
		IJ.log("Parameter record: %s" % record_path)


IJ.log("-" * 64)
summary_lines = []
summary_lines.append("Converted : %d" % len(converted_files))
if flagged_files:
	summary_lines.append("Flagged   : %d  (see Log)" % len(flagged_files))
if failed_files:
	summary_lines.append("Failed    : %d  (see Log)" % len(failed_files))
if skipped_files:
	summary_lines.append("Skipped   : %d  (zip already existed)" % len(skipped_files))
if no_region_files:
	summary_lines.append("No regions: %d section(s) hold none of the regions (no "
	                     ".zip): %s" % (len(no_region_files),
	                                    _short_list(no_region_files, 8)))
_never = [l for l, k in region_entries(globals().get("brainRegions"))
          if COMPOSE_REGIONS and k not in REGIONS_FOUND]
if _never and not stopped_early:
	summary_lines.append("Not found : %s - in none of the sections; check the "
	                     "spelling against the names in the Log"
	                     % ", ".join(_never))
if side_summary:
	summary_lines.append(side_summary)
if mirrored_files:
	summary_lines.append("Mirrored? : %d section(s) with %s"
	                     % (len(mirrored_files), MIRROR_TEXT))
	summary_lines.append("            %s" % _short_list(mirrored_files, 12))

for line in summary_lines:
	IJ.log(line)
IJ.log("-" * 64)

IJ.beep()

if stopped_early:
	IJ.error("Batch STOPPED early",
	         "The run was set to stop on the first problem.\n\n"
	         + stop_reason
	         + "\n\n" + "\n".join(summary_lines)
	         + "\n\nOutput folder: %s" % OUT_DIR
	         + ("\nParameter record: %s" % record_path if record_path else "")
	         + "\n\nFull detail is in the Log window.")
else:
	title = "Batch complete"
	body = ["Finished processing %d file(s)." % len(names_in), ""]
	body.extend(summary_lines)
	body.append("")
	body.append("Output folder: %s" % OUT_DIR)
	if converted_files:
		shown = converted_files[:12]
		body.append("Written:")
		for s in shown:
			body.append("   %s.zip" % s)
		if len(converted_files) > len(shown):
			body.append("   ... and %d more" % (len(converted_files) - len(shown)))
	if failed_files or flagged_files or _never:
		title = "Batch complete - with problems"
		body.append("")
		body.append("Check the Log window for the details of each problem.")
	if log_path or record_path:
		body.append("")
	if log_path:
		body.append("Log: %s" % log_path)
	if record_path:
		body.append("Parameter record: %s" % record_path)
	IJ.showMessage(title, "\n".join(body))
