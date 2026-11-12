# 3_Count_Particles_per_ROI.py - count thresholded ilastik detections
# inside every anatomical ROI (batch).
# Menu: Plugins > Kapur Lab Cell Counting > Batch > 3 Count Particles per ROI
# Reads : probability .tif/.tiff files (probabilities/) and ROI .zip files
#         (rois/), paired by the leading RegionXXXX token.
# Writes: a new output folder (default particle_counts/) holding
#   particle_counts.csv: one row per image (with group columns day, ...
#     when experiment_layout.csv has the slide), one column per ROI (NA when
#     off the image); total_particles counts each particle once. An existing
#     CSV is kept as particle_counts_previous_<date-time>.csv unless Overwrite.
#   thresholded/, watershed/, QC/, particle_rois/; the parameter record;
#   _counting_log.csv (debug log, when ticked).
# Counting settings: the experiment's tuned values by default, else the
# dialog's. Each particle counts in every ROI that holds its centre.
# Usage: Plugins > Kapur Lab Cell Counting > Batch > 3 Count Particles per
#        ROI, or open this file in the Script Editor (File > New >
#        Script..., or Plugins > Scripting > Script Editor) with Language =
#        Python (Jython) and press Run.

#@ File    (label="Slide folder (the scripts find its subfolders)", style="directory") slideDir
#@ String  (label="Region (its MBF folder; blank = choose from a list)", value="", required=false) regionName
#@ String  (label="Only use images whose name contains (blank = all)", value="", required=false) nameFilter
#@ String  (label="Counting settings", choices={"Tuned values of the experiment (if found)", "The values below"}, style="radioButtonHorizontal") settingsSource
#@ Integer (label="Threshold: minimum (8-bit)", value=128, min=0, max=255) thresholdMin
#@ Integer (label="Threshold: maximum (8-bit)", value=255, min=0, max=255) thresholdMax
#@ Boolean (label="Watershed before Analyze Particles", value=false) doWatershed
#@ Double  (label="Analyze Particles: minimum size", value=10.0) minSize
#@ Double  (label="Analyze Particles: maximum size (0 = no limit)", value=0.0) maxSize
#@ Double  (label="Analyze Particles: minimum circularity", value=0.0, min=0.0, max=1.0) minCirc
#@ Double  (label="Analyze Particles: maximum circularity", value=1.0, min=0.0, max=1.0) maxCirc
#@ Boolean (label="Include holes", value=false) includeHoles
#@ Boolean (label="Exclude particles on edges", value=false) excludeEdges
#@ String  (label="Show", choices={"Nothing", "Overlay outlines (saved as QC image)", "Masks (saved as QC image)"}, style="listBox") showMode
#@ String  (label="Export particle ROIs", choices={"Nothing", "One combined ROI per image", "Individual particle ROIs", "Both"}, style="listBox") particleExport
#@ File    (label="Output location (blank = one level above the input)", style="directory", required=false) outParentDir
#@ String  (label="Name for the new output folder", value="particle_counts") outFolderName
#@ Boolean (label="Overwrite an existing results CSV", value=false) overwrite
#@ Boolean (label="Write a debug log CSV to the output folder", value=false) writeLog

# =========================================================================
# ===  USER CONFIGURATION  ================================================
# =========================================================================
# Nothing below the END banner needs editing for routine use.

# ---- THRESHOLD
# Set in the DIALOG on the fixed 8-bit scale: 128 = p 0.50, 179 ~ 0.70, 204 ~ 0.80.

# ---- CHANNELS
# The channel (or plane, with no channel dimension) analysed; 1 = 'signal'.
SIGNAL_CHANNEL = 1

# Warn (never stop) when the signal channel is not the dimmest.
SANITY_CHECK_CHANNELS = True

# Warn when mean(signal) > mean(brightest other channel) * this ratio.
SANITY_MAX_RATIO = 1.0

# ---- SAVING INTERMEDIATE IMAGES
# Subfolders created inside the output folder.
SAVE_THRESHOLDED = True
THRESHOLDED_SUBFOLDER = "thresholded"

SAVE_WATERSHED = True                 # when watershed is ticked
WATERSHED_SUBFOLDER = "watershed"

# QC images (when 'Show' is not "Nothing").
QC_SUBFOLDER = "QC"

# ---- PARTICLE ROI EXPORT
# "Individual": a RoiSet .zip, each particle named after the smallest ROI
# holding its centre. Stage 4 looks for these suffixes: change them there too.
PARTICLE_ROI_SUBFOLDER = "particle_rois"
PARTICLE_COMBINED_SUFFIX = "_particles_combined"     # -> .roi
PARTICLE_INDIVIDUAL_SUFFIX = "_particles"            # -> .zip

# <region>_<index>, numbered per region (widen past 9999 per region).
PARTICLE_ROI_NAME_TEMPLATE = "%s_%04d"

# ---- FILENAME STANDARD
# Files pair by the LEADING RegionXXXX token.
KEY_PATTERN = r"^(Region\d+)"
CASE_INSENSITIVE_KEYS = True

# True warns (never stops) when the input folders are not in one slide
# folder (two slides' folders would pair without any error).
WARN_ON_DIFFERENT_SLIDE_FOLDERS = True

# Filename filters on the probability images (blank = off), e.g. "_C2". The
# dialog's "Only use images whose name contains" replaces REQUIRE_IN_NAME.
REQUIRE_IN_NAME = ""
EXCLUDE_IN_NAME = ""

# ---- WHICH ROIs TO COUNT IN
# Every ROI in the zip by default; restrict with either list (any case).
ONLY_THESE_ROIS = []          # e.g. ["Caudoputamen", "Nucleus accumbens"]
SKIP_THESE_ROIS = []          # e.g. ["Tissue"]  - the whole-tissue outline

# Also report a count over the whole image, ignoring every ROI?
INCLUDE_WHOLE_IMAGE_COLUMN = False

# ---- SIZE UNITS
# True -> min/max size in PIXELS (recommended); False -> calibrated um^2.
SIZE_IN_PIXELS = True

# ---- OUTPUT
# Output folder goes one level ABOVE the "tif" (probability) or "roi" folder.
OUTPUT_PARENT_SOURCE = "tif"

# An existing results CSV is kept as particle_counts_previous_<YYYYMMDD-
# HHMMSS>.csv unless 'Overwrite an existing results CSV' is ticked.
RESULTS_CSV_NAME = "particle_counts.csv"

# One row per image and ROI with its count, area (pixels and mm2) and
# cells per mm2; the pixel size comes from 2a (stored in the ROIs).
WRITE_REGION_TABLE = True
REGION_TABLE_NAME = "particle_counts_by_region.csv"

# For an ROI missing from an image, or entirely outside it.
MISSING_VALUE = "NA"

TIF_EXTENSIONS = [".tif", ".tiff"]

# ---- PARAMETER RECORD
# True -> save _run_..._<time>.txt (every setting used).
WRITE_PARAMETER_RECORD = True

# ---- SAFETY CHECKS
# Show the "Check settings" window first. False skips it (warnings logged).
CONFIRM_BEFORE_RUN = True

# =========================================================================
# ===  END OF USER CONFIGURATION  =========================================
# =========================================================================

SCRIPT_NAME = "3_Count_Particles_per_ROI"
SCRIPT_VERSION = "2.0"

import os
import re
from collections import OrderedDict

from ij import IJ, ImagePlus, Prefs
from java.lang import Exception as JavaException
ANY_ERROR = (Exception, JavaException)
from ij.gui import Overlay
from ij.io import RoiEncoder
from ij.measure import ResultsTable, Calibration, Measurements
from ij.plugin import Duplicator, ChannelSplitter
from ij.plugin.filter import ParticleAnalyzer
from ij.process import ImageProcessor, ByteProcessor

# ---- slide-folder check
# A region folder (Set Up Slide Folders) has the word MBF in its name.
MBF_FOLDER_RE = re.compile(r"(^|[^A-Za-z0-9])MBF([^A-Za-z0-9]|$)", re.IGNORECASE)

def slide_folder_warning(entries):
	"""Warning lines, or None. entries: [(label, path, levels up)]."""
	if not WARN_ON_DIFFERENT_SLIDE_FOLDERS or len(entries) < 2:
		return None
	slides, regions = set(), set()
	for _label, path, levels in entries:
		p = os.path.normpath(os.path.abspath(path))
		for _k in range(levels):
			p = os.path.dirname(p)
		# A "<region> MBF" folder is part of its slide folder: step out.
		if MBF_FOLDER_RE.search(os.path.basename(p)):
			regions.add(os.path.normcase(p))
			p = os.path.dirname(p)
		slides.add(os.path.normcase(p))
	if len(slides) <= 1 and len(regions) <= 1:
		return None
	one = len(slides) <= 1
	return ([one and "the inputs come from different region (MBF) folders of one slide:"
	         or "the inputs do not come from the same slide folder:"]
	        + ["   %s: %s" % (label, path) for label, path, _l in entries]
	        + ["Check that these folders belong to the same %s."
	           % (one and "region" or "slide")])

def log_slide_warning(lines):
	for ln in (["  " + "!" * 62, "  ! WARNING: " + lines[0]]
	           + ["  !   " + line.strip() for line in lines[1:]]
	           + ["  ! Files pair by RegionXXXX only, so folders from two slides or",
	              "  ! regions would pair without any error. Processing continues.",
	              "  " + "!" * 62]):
		IJ.log(ln)

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

# ---- settings check helpers
# A probability folder named like another stage's output is probably wrong.
_OWN = "a subfolder this script writes"
_DEF = "the default output folder of "
OTHER_STAGE_FOLDERS = {
    "tifs": _DEF + "1 Convert to Tif",
    "processed_bgsub_cleared": _DEF + "2b BG Subtract and Clear",
    "rois": _DEF + "2a NeuroInfo XML to ROI",
    "thresholded": _OWN, "watershed": _OWN, "qc": _OWN, "particle_rois": _OWN,
    "particle_counts": _DEF + "this script",
    "pipeline_composites": _DEF + "4 Build Pipeline Composite",
}
BGSUB_FOLDER_NAME = "processed_bgsub_cleared"

def short_list(names, n=3):
	names = list(names)
	return ", ".join(names[:n]) + (" and %d more" % (len(names) - n)
	                               if len(names) > n else "")

def threshold_text(lo, hi):
	if hi >= 255:
		return ("Threshold: %d-%d (8-bit), i.e. probability p >= %.2f"
		        % (lo, hi, lo / 255.0))
	return ("Threshold: %d-%d (8-bit), i.e. probability %.2f <= p <= %.2f"
	        % (lo, hi, lo / 255.0, hi / 255.0))

def tiff_header(path):
	"""(bits (24 = RGB), channels or None, planes) from the header."""
	from ij.io import TiffDecoder, FileInfo
	try:
		infos = TiffDecoder(os.path.dirname(path),
		                    os.path.basename(path)).getTiffInfo()
		if not infos:
			return None
		fi = infos[0]
		bits = 24
		for b, nms in ((8, "GRAY8 COLOR8 BITMAP"), (16, "GRAY16_SIGNED "
		                "GRAY16_UNSIGNED GRAY12_UNSIGNED"), (32, "GRAY32_INT "
		                "GRAY32_UNSIGNED GRAY32_FLOAT GRAY24_UNSIGNED"),
		               (64, "GRAY64_FLOAT"), (48, "RGB48 RGB48_PLANAR")):
			if bits == 24 and fi.fileType in [getattr(FileInfo, n) for n in
			                                  nms.split() if hasattr(FileInfo, n)]:
				bits = b
		channels = 3 if bits == 48 else None
		bits = 16 if bits == 48 else bits
		planes = fi.nImages if fi.nImages > 1 else len(infos)
		m = re.search(r"channels=(\d+)", fi.description or "")
		if m:
			channels = int(m.group(1))
		return bits, channels, planes
	except ANY_ERROR:
		pass
	try:
		from loci.formats import ImageReader, FormatTools
		r = ImageReader()
		try:
			r.setId(path)
			pt = r.getPixelType()
			if r.isRGB() and r.getRGBChannelCount() == 3 and pt == FormatTools.UINT8:
				return 24, None, r.getImageCount()
			bits = FormatTools.getBytesPerPixel(pt) * 8
			return bits, r.getSizeC(), r.getImageCount()
		finally:
			r.close()
	except ANY_ERROR:
		return None

def image_header_lines(name, path, what="first probability image"):
	head = what[0].upper() + what[1:]
	hdr = tiff_header(path)
	if hdr is None:
		return ["%s: header could not be read (%s)" % (head, name)]
	bits, channels, planes = hdr
	if bits == 24:
		return ["%s: RGB colour" % head]
	sc = "is counted (SIGNAL_CHANNEL in the script)"
	if channels is not None and channels > 1:
		return ["%s: %d-bit, %d channels; channel %d %s"
		        % (head, bits, channels, SIGNAL_CHANNEL, sc)]
	if planes > 1:
		return ["%s: %d-bit, %d planes; plane %d %s"
		        % (head, bits, planes, SIGNAL_CHANNEL, sc)]
	return ["%s: %d-bit, 1 channel (counted as it is)" % (head, bits)]

def header_warnings(items):
	rgb, deep, few = [], [], []
	for name, path in items:
		hdr = tiff_header(path)
		if hdr is None:
			continue
		bits, channels, planes = hdr
		if bits == 24:
			rgb.append(name)
			continue
		if bits != 8:
			deep.append("%s %d-bit" % (name, bits))
		n = channels if channels is not None else planes
		if n < SIGNAL_CHANNEL:
			few.append("%s has %d" % (name, n))
	lines = []
	if rgb:
		lines.append("! %d probability image(s) are RGB colour images, not "
		             "ilastik probability maps (%s). RGB files fail with an "
		             "error, so check that this is the probabilities/ folder."
		             % (len(rgb), short_list(rgb)))
	if deep:
		lines.append("! %d probability map(s) are not 8-bit (%s). Each is "
		             "converted to 8-bit on a fixed scale: 16-bit 0-65535 and "
		             "32-bit probability 0-1 (or 0-255) are mapped onto 0-255, "
		             "so the threshold means the same probability in every "
		             "map. A 32-bit map with values outside 0-255 fails with "
		             "an error. Exporting from ilastik as integer 8-bit "
		             "(renormalize 0.00-1.00 to 0-255) avoids the conversion."
		             % (len(deep), short_list(deep)))
	if few:
		lines.append("! %d probability image(s) have fewer channels than "
		             "SIGNAL_CHANNEL (%d), so counting them fails (%s)."
		             % (len(few), SIGNAL_CHANNEL, short_list(few)))
	return lines

def other_stage_warning(folder, what):
	base = os.path.basename(os.path.normpath(folder))
	desc = OTHER_STAGE_FOLDERS.get(base.lower())
	if desc is None:
		return None
	return ("! The %s is named '%s', which is %s. Counting needs the ilastik "
	        "probability maps (probabilities/), so check that this is the "
	        "right folder." % (what, base, desc))

def stale_lines(pairs):
	"""'!' lines: maps older than their bgsub image; ROI sets newer than
	either. pairs: (map, ROI zip)."""
	if not pairs:
		return []
	prob_dir = os.path.dirname(pairs[0][0])
	src_dir = os.path.join(os.path.dirname(os.path.normpath(prob_dir)),
	                       BGSUB_FOLDER_NAME)
	src_files = []
	if (os.path.isdir(src_dir) and os.path.normcase(os.path.abspath(src_dir))
	        != os.path.normcase(os.path.abspath(prob_dir))):
		try:
			src_files = tifs_in(src_dir)
		except (OSError, IOError):
			pass
	by_key = {}
	for f in src_files:
		by_key.setdefault(key_from(f), []).append(f)
	older, newer = [], []
	for p, z in pairs:
		name = os.path.basename(p)
		c = [name] if name in src_files else by_key.get(key_from(name) or 0, [])
		src = len(c) == 1 and os.path.join(src_dir, c[0]) or None
		try:   # 2 s of slack for coarse file times
			tp = os.path.getmtime(p)
			ts = src and os.path.getmtime(src) or tp
			if tp + 2.0 < ts:
				older.append(name)
			if os.path.getmtime(z) > min(tp, ts) + 2.0:
				newer.append(key_from(name) or name)
		except (OSError, IOError):
			pass
	return ["! %d probability map(s) are older than the matching image in %s/ "
	        "(%s). Re-export them from ilastik if the images were redone."
	        % (len(older), BGSUB_FOLDER_NAME, short_list(older))] * bool(older) + [
	    "! The ROI sets of %d section(s) are newer than their probability map "
	    "or %s/ image (%s): if an outer edge moved, run 2b and ilastik again for "
	    "them." % (len(newer), BGSUB_FOLDER_NAME, short_list(newer))] * bool(newer)

def roi_overlap_lines(set_name, rois):
	"""Lines on ROIs inside another (info) or overlapping >= 1% (warning)."""
	from ij.process import Blitter
	items = [(n, r, r.getBounds()) for n, r in rois.items() if r is not None]
	nested, partial, areas, checked = [], [], {}, 0
	for i, (na, ra, ba) in enumerate(items):
		for nb, rb, bb in items[i + 1:]:
			x0, y0 = max(ba.x, bb.x), max(ba.y, bb.y)
			x1 = min(ba.x + ba.width, bb.x + bb.width)
			y1 = min(ba.y + ba.height, bb.y + bb.height)
			if x1 <= x0 or y1 <= y0:
				continue
			checked += 1
			if checked > 2000:
				break
			try:
				both = []
				for r, b in ((ra, ba), (rb, bb)):
					bp = ByteProcessor(x1 - x0, y1 - y0)
					bp.setColor(255)
					r = r.clone()
					r.setLocation(b.x - x0, b.y - y0)
					bp.fill(r)
					both.append(bp)
				both[0].copyBits(both[1], 0, 0, Blitter.AND)
				inter = both[0].getHistogram()[255]
				if inter == 0:
					continue
				for n_, r_ in ((na, ra), (nb, rb)):
					if n_ not in areas:
						areas[n_] = roi_area_px(r_)
				smaller = min(areas[na], areas[nb])
				if smaller <= 0:
					continue
				if inter >= 0.98 * smaller:
					inner, outer = (na, nb) if areas[na] <= areas[nb] else (nb, na)
					nested.append("%s in %s" % (inner, outer))
				elif inter >= 0.01 * smaller:
					partial.append("%s / %s" % (na, nb))
			except ANY_ERROR:
				continue
	lines = []
	if nested:
		lines.append("ROI set %s: %d ROI(s) lie inside another (%s); their "
		             "particles count in both columns" %
		             (set_name, len(nested), short_list(nested)))
	if partial:
		lines.append("! In ROI set %s, %d pair(s) of ROIs partly overlap "
		             "(%s). A particle whose centre is in the shared area "
		             "counts in both columns, so the ROI columns do not add "
		             "up to total_particles (which counts each particle once)."
		             % (set_name, len(partial), short_list(partial)))
	return lines

EDGE_WARNING = ("! 'Exclude particles on edges' is ticked: particles that "
                "touch the edge of the IMAGE are left out of every count. "
                "Particles that touch an ROI outline are still counted, in "
                "the ROI that contains their centre.")
COUNTING_TEXT = ("Counting: Analyze Particles runs once on the whole image; "
                 "each particle is counted once, in every ROI that contains "
                 "its centre")

TUNED_KEYS = ("thresholdMin thresholdMax doWatershed minSize maxSize minCirc "
              "maxCirc includeHoles excludeEdges").split()

def find_tuned(folder, region):
	"""(path, {key: text}, note) of this region's tuned file."""
	d, dirs = os.path.abspath(folder), []
	for _k in range(9):
		dirs.append(d)
		d = os.path.dirname(d)
	tag = re.sub(r"[^A-Za-z0-9]+", "_", region).strip("_")
	for d in LAYOUT_CSV and [os.path.dirname(LAYOUT_CSV)] or dirs:
		for s in [(f, n) for f in ("counting_tuning", "") for n in (tag and "_" + tag, "")]:
			p = os.path.join(d, s[0], "tuned_counting_parameters%s.txt" % s[1])
			if not os.path.isfile(p):
				continue
			with open(p) as fh:         # closed at once: Tune may replace it later
				v = dict([[x.strip() for x in ln.split("=", 1)] for ln in
				          fh.read().splitlines() if "=" in ln and "#" != ln[:1]])
			r = layout_text(v.get("region", "\0"))
			if r in (region, "\0"):
				return p, v, r != region and region and ("! %s records no region "
				    "(older Tune); check it was tuned on %s." % (p, region)) or ""
			return None, {}, ("! %s was tuned on region '%s', not '%s'; not used."
			                  % (p, r, region or "(none)"))
	return None, {}, ""

def as_type(k, v):
	if k in ("doWatershed", "includeHoles", "excludeEdges"):
		return str(v).strip().lower() in ("true", "1", "yes")
	return int(float(v)) if k.startswith("threshold") else float(v)

def tuned_lines():
	if USE_TUNED:
		out = [x for x in (TUNED_NOTE, "Counting settings: " + COUNT_SRC) if x]
		ch = TUNED.get("SIGNAL_CHANNEL", "")
		if ch and ch != str(SIGNAL_CHANNEL):
			out.append("! The tuned values were found on channel %s, but "
			           "SIGNAL_CHANNEL in this script is %d." % (ch, SIGNAL_CHANNEL))
		return out
	if WANT_TUNED:
		return [TUNED_NOTE or "No tuned values for region '%s' were found in the "
		        "experiment folder; using the values below." % (REGION_NAME or
		                                                        "(none)")]
	try:
		diff = ["%s %s (tuned %s)" % (k, DIALOG_VALUES[k], TUNED[k])
		        for k in TUNED_KEYS if k in TUNED and
		        as_type(k, TUNED[k]) != as_type(k, DIALOG_VALUES[k])]
	except ValueError:
		return ["! %s could not be read." % TUNED_PATH]
	return diff and ["! Settings differ from the tuned values in %s: %s. Use "
	                 "the tuned values for every slide of the experiment."
	                 % (TUNED_PATH, ", ".join(sorted(diff)))] or []

def slide_check_line(lines):
	what = "region" if "region (MBF)" in lines[0] else "slide"
	head = lines[0].rstrip(":")
	return ("! %s%s (%s). Files pair by RegionXXXX only, so check that they "
	        "belong to the same %s."
	        % (head[:1].upper(), head[1:],
	           "; ".join([ln.strip() for ln in lines[1:-1]]), what))

def remove_if_new_and_empty(path, existed):
	if existed or not path or not os.path.isdir(path):
		return
	try:
		if not os.listdir(path):
			os.rmdir(path)
	except (OSError, IOError):
		pass

def ind(lines):
	return [ln if ln.startswith("!") else "   " + ln for ln in lines]

def prob_scale(note):
	"""Scale label from the probability_to_8bit note."""
	if note.startswith("32-bit"):
		return "32-bit 0-255" if "0-255 scale" in note else "32-bit 0-1"
	return note.split(",")[0].split(":")[0]

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

# ---- slide folder -> folders/files (skipped when given directly: tests)
if globals().get("slideDir") is not None:
	from java.io import File as _F
	_SLIDE = slideDir.getAbsolutePath()
	_REGION = layout_pick_region(_SLIDE, regionName)
	if _REGION is None:
		raise SystemExit
	_got = layout_confirm(SCRIPT_NAME + " - folders", _SLIDE, _REGION, [
	    ('Folder of ilastik probability .tif files (probabilities/)', "dir", layout_find(_SLIDE, _REGION, "probabilities"), None, True),
	    ('Folder of ROI .zip files (rois/)', "dir", layout_find(_SLIDE, _REGION, "rois"), None, True),
	])
	if _got is None:
		raise SystemExit
	probDir = _F(_got[0]) if _got[0] else None
	roiDir = _F(_got[1]) if _got[1] else None

PROB_DIR = probDir.getAbsolutePath()
ROI_DIR = roiDir.getAbsolutePath()

NAME_FILTER = (nameFilter or "").strip()
if NAME_FILTER:
	REQUIRE_IN_NAME = NAME_FILTER

# Experiment table row; counting settings (tuned values replace the dialog's).
LAYOUT_FOLDER = globals().get("_SLIDE") or PROB_DIR
_r = globals().get("_REGION") or os.path.dirname(os.path.normpath(PROB_DIR))
REGION_NAME = (_r != globals().get("_SLIDE") and layout_is_region(_r)
               and os.path.basename(_r) or "")
LAYOUT_CSV, _lv, LAYOUT_ROW = layout_csv_row(LAYOUT_FOLDER)
GROUP_COLS = LAYOUT_ROW and _lv + ["slide"] or []
GROUP_VALS = [LAYOUT_ROW.get(c, "") for c in GROUP_COLS]
LAYOUT_TEXT = LAYOUT_ROW and "; ".join(["%s=%s" % (c, LAYOUT_ROW.get(c, ""))
    for c in ["include"] + GROUP_COLS + ["slide_path"]]) or "(none)"
TUNED_PATH, TUNED, TUNED_NOTE = find_tuned(LAYOUT_FOLDER, REGION_NAME)
DIALOG_VALUES = dict([(k, globals()[k]) for k in TUNED_KEYS])
SOURCE = globals().get("settingsSource") or "The values below"
WANT_TUNED = SOURCE.startswith("Tuned")
USE_TUNED = WANT_TUNED and bool(TUNED_PATH)
COUNT_SRC = "the values in the dialog"
if USE_TUNED:
	try:
		for _k in TUNED_KEYS:
			if _k in TUNED:
				globals()[_k] = as_type(_k, TUNED[_k])
	except ValueError:
		IJ.error("Tuned values", "%s\ncould not be read ('%s = %s').\n\nRun "
		         "Tune Counting Parameters again, or choose 'The values below'."
		         % (TUNED_PATH, _k, TUNED.get(_k)))
		raise SystemExit
	try:
		_f1 = "%.2f" % float(TUNED["F1"])
	except (KeyError, ValueError):
		_f1 = TUNED.get("F1", "?")
	COUNT_SRC = "tuned values from %s (F1 %s on %s sections), region '%s'" % (
	    TUNED_PATH, _f1, TUNED.get("sections", "?"), REGION_NAME or "(none)")
	if not SIZE_IN_PIXELS:
		IJ.error("Tuned values", "The tuned sizes are in pixels, but SIZE_IN_PIXELS "
		         "is False. Set it to True, or choose 'The values below'.")
		raise SystemExit

MAX_SIZE = float(maxSize) if float(maxSize) > 0 else float("inf")
MIN_SIZE = float(minSize)

QC_NONE = (showMode == "Nothing")
QC_OVERLAY = showMode.startswith("Overlay")
QC_MASKS = showMode.startswith("Masks")

EXPORT_NONE = (particleExport == "Nothing")
EXPORT_COMBINED = particleExport in ("One combined ROI per image", "Both")
EXPORT_INDIVIDUAL = particleExport in ("Individual particle ROIs", "Both")

MASK_THRESHOLD = (128, 255)

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


def filter_rois(rois):
	only = [s.lower() for s in ONLY_THESE_ROIS]
	skip = [s.lower() for s in SKIP_THESE_ROIS]
	out = OrderedDict()
	for name, roi in rois.items():
		low = name.lower()
		base = re.sub(r"_\d+$", "", low)      # Name_2 -> Name
		if only and low not in only and base not in only:
			continue
		if low in skip or base in skip:
			continue
		out[name] = roi
	return out

# ---- image prep
def mean_of(imp):
	try:
		return imp.getStatistics(Measurements.MEAN).mean
	except ANY_ERROR:
		return float("nan")

def close_quietly(*imps):
	for obj in imps:
		if obj is not None:
			try:
				obj.changes = False
				obj.close()
			except ANY_ERROR:
				pass

def open_and_prepare(path):
	"""Open, keep the signal channel, make fixed-scale 8-bit: (imp, notes,
	info, channel_means)."""
	notes, info = [], []
	imp, n_series = bf_open(path, 0)
	if n_series > 1:
		notes.append("file contains %d series; series 0 (the first) was "
		             "used" % n_series)
	try:
		if imp.getBitDepth() == 24:
			raise StepError("this is an RGB image, not a multi-channel "
			                "probability map.")
		from ij.process import StackStatistics
		file_max = imp.getBitDepth() == 32 and StackStatistics(imp).max or None
		nch = imp.getNChannels()
		if nch < 2:
			nplanes = imp.getStackSize()
			if nplanes > 1:
				# Planes open as slices or time points: pick by position.
				if nplanes < SIGNAL_CHANNEL:
					raise StepError(
					    "SIGNAL_CHANNEL is %d but the file has no channel "
					    "dimension and only %d plane(s)."
					    % (SIGNAL_CHANNEL, nplanes))
				stack = imp.getStack()
				channel_means = []
				for j in range(1, nplanes + 1):
					try:
						channel_means.append(
						    stack.getProcessor(j).getStatistics().mean)
					except ANY_ERROR:
						channel_means.append(float("nan"))
				notes.append(
				    "no channel dimension: the file opened as %d plane(s) "
				    "(%d slice(s) x %d time point(s)), so plane %d of the "
				    "stack was used as the signal channel"
				    % (nplanes, imp.getNSlices(), imp.getNFrames(),
				       SIGNAL_CHANNEL))
				picked = ImagePlus(imp.getTitle(),
				                   stack.getProcessor(SIGNAL_CHANNEL).duplicate())
				picked.setCalibration(imp.getCalibration().copy())
				close_quietly(imp)
				imp = picked
			else:
				info.append("single-channel image; nothing to split")
				channel_means = [mean_of(imp)]
		else:
			if nch < SIGNAL_CHANNEL:
				raise StepError("SIGNAL_CHANNEL is %d but the image has only "
				                "%d channel(s)." % (SIGNAL_CHANNEL, nch))
			try:
				channels = ChannelSplitter.split(imp)
			except ANY_ERROR, e:
				raise StepError("channel splitting failed: %s" % str(e))
			channel_means = [mean_of(c) for c in channels]
			picked = channels[SIGNAL_CHANNEL - 1]
			close_quietly(*[c for j, c in enumerate(channels)
			                if j != SIGNAL_CHANNEL - 1])
			close_quietly(imp)
			imp = picked
			info.append("split %d channels, kept channel %d"
			            % (nch, SIGNAL_CHANNEL))

		if SANITY_CHECK_CHANNELS and len(channel_means) > 1:
			sig = channel_means[SIGNAL_CHANNEL - 1]
			brightest_other = max([m for j, m in enumerate(channel_means)
			                       if j != SIGNAL_CHANNEL - 1])
			if sig > brightest_other * SANITY_MAX_RATIO:
				notes.append(
				    "CHANNEL SANITY CHECK: channel %d has mean %.1f, not "
				    "clearly below the brightest other channel (%.1f); the "
				    "signal channel should be the dimmest, so the channel "
				    "order may be wrong. Means: %s. (Warning only - counting "
				    "continued.)"
				    % (SIGNAL_CHANNEL, sig, brightest_other,
				       ", ".join(["ch%d=%.1f" % (j + 1, m)
				                  for j, m in enumerate(channel_means)])))

		info.append("probability map: " + probability_to_8bit(imp, file_max))
		if SIZE_IN_PIXELS:
			imp.setCalibration(Calibration())
	except:
		close_quietly(imp)
		raise
	return imp, notes, info, channel_means

def make_mask(imp):
	mask = Duplicator().run(imp)
	mask.getProcessor().setThreshold(THRESHOLD_MIN, THRESHOLD_MAX,
	                                 ImageProcessor.NO_LUT_UPDATE)
	try:
		IJ.run(mask, "Convert to Mask", "")
	except ANY_ERROR, e:
		close_quietly(mask)
		raise StepError("Convert to Mask failed: %s" % str(e))
	return mask

def find_particles(imp, lo, hi, want_outlines):
	"""Analyze Particles ONCE over the image: [(xc, yc, outline)] in px."""
	ip = imp.getProcessor()
	imp.deleteRoi()
	ip.resetRoi()
	ip.setThreshold(lo, hi, ImageProcessor.NO_LUT_UPDATE)
	opts = ((includeHoles and ParticleAnalyzer.INCLUDE_HOLES or 0)
	        | (excludeEdges and ParticleAnalyzer.EXCLUDE_EDGE_PARTICLES or 0)
	        | (ParticleAnalyzer.SHOW_OVERLAY_OUTLINES if want_outlines
	           else ParticleAnalyzer.SHOW_NONE))
	imp.setOverlay(None)
	rt = ResultsTable()
	pa = ParticleAnalyzer(opts, Measurements.AREA | Measurements.CENTROID
	                      | Measurements.SHAPE_DESCRIPTORS, rt,
	                      MIN_SIZE, MAX_SIZE, float(minCirc), float(maxCirc))
	pa.setHideOutputImage(True)
	if not pa.analyze(imp, ip):
		raise StepError("Analyze Particles reported a failure.")
	n = rt.size()
	outlines = [None] * n
	if want_outlines:
		ov = imp.getOverlay()
		got = [ov.get(j) for j in range(ov.size())] if ov is not None else []
		imp.setOverlay(None)
		if len(got) != n:
			raise StepError("Analyze Particles gave %d outline(s) for %d "
			                "particle(s)." % (len(got), n))
		outlines = got
	cal = imp.getCalibration()
	h = imp.getHeight()
	return [(cal.getRawX(rt.getValue("X", j)),
	         cal.getRawY(rt.getValue("Y", j), h), outlines[j])
	        for j in range(n)]

def assign_particles(particles, rois):
	"""(counts per ROI, homes[j] = ROIs whose pixel mask holds particle j's
	centroid pixel). Roi.containsPoint fails for sub-pixel ROIs in 1.54f."""
	import math
	shapes = [(name, roi.getBounds(), roi.getMask()) for name, roi in rois.items()]
	counts = OrderedDict([(name, 0) for name in rois])
	homes = []
	for xc, yc, _outline in particles:
		ix, iy = int(math.floor(xc)), int(math.floor(yc))
		inside = []
		for name, b, mask in shapes:
			if not (b.x <= ix < b.x + b.width and b.y <= iy < b.y + b.height):
				continue
			if mask is None or mask.get(ix - b.x, iy - b.y) != 0:
				inside.append(name)
				counts[name] += 1
		homes.append(inside)
	return counts, homes

def particle_rois_to_export(particles, homes, rois):
	"""[(name, outline)]: each particle once, named by its smallest ROI."""
	areas, seq, out = {}, {}, []
	for (_xc, _yc, outline), inside in zip(particles, homes):
		if not inside or outline is None:
			continue
		for name in inside:
			if name not in areas:
				areas[name] = roi_area_px(rois[name])
		best = min(inside, key=lambda nm: areas[nm])
		seq[best] = seq.get(best, 0) + 1
		out.append((PARTICLE_ROI_NAME_TEMPLATE % (best, seq[best]), outline))
	return out

def particles_to_mask(particles, w, h):
	bp = ByteProcessor(w, h)
	bp.setColor(255)
	for _name, r in particles:
		try:
			bp.fill(r)
		except ANY_ERROR:
			pass
	return bp

def archive_results_csv(path):
	"""Rename to <name>_previous_<date-time>.csv; new path, or IOError."""
	import time
	stem, ext = os.path.splitext(path)
	stamp = time.strftime("%Y%m%d-%H%M%S")
	target = "%s_previous_%s%s" % (stem, stamp, ext)
	n = 2
	while os.path.exists(target):
		target = "%s_previous_%s_%d%s" % (stem, stamp, n, ext)
		n += 1
	try:
		os.rename(path, target)
	except ANY_ERROR, e:
		raise IOError("the existing %s could not be renamed to %s (%s), so "
		              "it was left as it was" % (os.path.basename(path),
		                                         os.path.basename(target),
		                                         str(e)))
	return target

def csv_cell(v):
	v = isinstance(v, unicode) and v.encode("utf-8") or str(v)
	return '"%s"' % v.replace('"', "'")

def write_csv(path, head, rows):
	fh = open(path, "w")
	try:
		if head:
			fh.write(head + "\n")
		for r in rows:
			fh.write(",".join([csv_cell(c) for c in r]) + "\n")
	finally:
		fh.close()

def remove_stale_outputs(stem, written):
	"""Delete this image's outputs this run did not write; log notes."""
	lines = []
	for sub, suffix in ((THRESHOLDED_SUBFOLDER, "_thresh.tif"),
	                    (WATERSHED_SUBFOLDER, "_watershed.tif"),
	                    (QC_SUBFOLDER, "_QC.tif"),
	                    (PARTICLE_ROI_SUBFOLDER, PARTICLE_INDIVIDUAL_SUFFIX + ".zip"),
	                    (PARTICLE_ROI_SUBFOLDER, PARTICLE_COMBINED_SUFFIX + ".roi")):
		path = os.path.join(OUT_DIR, sub, stem + suffix)
		if path in written or not os.path.isfile(path):
			continue
		shown_name = sub + "/" + stem + suffix
		try:
			os.remove(path)
			lines.append("removed stale %s from an earlier run" % shown_name)
		except (OSError, IOError), e:
			lines.append("could not remove stale %s from an earlier run: %s"
			             % (shown_name, str(e)))
	return lines

def make_subfolder(name):
	p = os.path.join(OUT_DIR, name)
	if not os.path.isdir(p):
		try:
			os.makedirs(p)
		except OSError, e:
			IJ.log("WARNING: could not create '%s' (%s); continuing without it."
			       % (name, str(e)))
			return None
	return p

def stop(title, msg):
	IJ.error(title, msg)
	raise SystemExit

def tifs_in(d):
	return [f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))
	        and os.path.splitext(f)[1].lower() in TIF_EXTENSIONS]

def by_key(files):
	"""(key -> file, files with no key, key -> files sharing it)."""
	found, nokey, dupes = {}, [], {}
	for f in sorted(files):
		k = key_from(f)
		if k is None:
			nokey.append(f)
		elif k in found:
			dupes.setdefault(k, [found[k]]).append(f)
		else:
			found[k] = f
	return found, nokey, dupes

SCALE_TEXT = ("read on a different probability scale from the others; check "
              "its ilastik export")

_prev_black_background = Prefs.blackBackground
# ==== pre-flight validation
try:
	from loci.plugins import BF
except ImportError:
	stop("Bio-Formats not available", "Install Bio-Formats (Help > Update..."
	     " > Manage update sites), then restart Fiji.")

THRESHOLD_MIN = int(thresholdMin)
THRESHOLD_MAX = int(thresholdMax)
if THRESHOLD_MIN > THRESHOLD_MAX:
	stop("Threshold", "The minimum threshold (%d) is greater than the maximum "
	     "(%d)." % (THRESHOLD_MIN, THRESHOLD_MAX))
if THRESHOLD_MIN == 0:
	stop("Threshold", "A minimum threshold of 0 includes every pixel, so all "
	     "of it is signal. 128 is p = 0.50.")
if SIGNAL_CHANNEL < 1:
	stop("Signal channel", "SIGNAL_CHANNEL (CHANNELS section of the "
	     "configuration block) must be 1 or greater (got %s)." % SIGNAL_CHANNEL)
if MIN_SIZE < 0:
	stop("Particle size", "Minimum size cannot be negative (got %s)." % MIN_SIZE)
if MIN_SIZE > MAX_SIZE:
	stop("Particle size", "Minimum size (%s) is greater than maximum size "
	     "(%s); enter 0 for no upper limit." % (MIN_SIZE, MAX_SIZE))
if minCirc > maxCirc:
	stop("Circularity", "Minimum circularity (%s) is greater than maximum "
	     "(%s)." % (minCirc, maxCirc))

for label, d in (("probability image", PROB_DIR), ("ROI", ROI_DIR)):
	if not os.path.isdir(d):
		stop("Input folder", "The %s folder does not exist:\n%s\n\nChoose "
		     "an existing folder in the dialog." % (label, d))

# ---- inventory
tif_files = [f for f in tifs_in(PROB_DIR) if name_allowed(f)]
roi_files = [f for f in os.listdir(ROI_DIR)
             if os.path.isfile(os.path.join(ROI_DIR, f))
             and f.lower().endswith(".zip") and not f.startswith("_")]
if not tif_files:
	msg = "No %s files in:\n%s" % (" / ".join(TIF_EXTENSIONS), PROB_DIR)
	if REQUIRE_IN_NAME or EXCLUDE_IN_NAME:
		msg += ("\n\nwith the filename filter: must contain %r, must not "
		        "contain %r (too strict?)." % (REQUIRE_IN_NAME, EXCLUDE_IN_NAME))
	else:
		msg += "\n\nChoose the probabilities/ folder written by ilastik."
	stop("No probability images", msg)
if not roi_files:
	stop("No ROI sets", "No .zip ROI files in:\n%s\n\nChoose the rois/ "
	     "folder written by 2a NeuroInfo XML to ROI." % ROI_DIR)

tif_by_key, tif_nokey, tif_dupes = by_key(tif_files)
roi_by_key, roi_nokey, roi_dupes = by_key(roi_files)
matched = sorted([k for k in tif_by_key if k in roi_by_key])
tif_only = sorted([k for k in tif_by_key if k not in roi_by_key])
roi_only = sorted([k for k in roi_by_key if k not in tif_by_key])

IJ.log("=" * 64)
IJ.log("Particle counting per ROI  (%s v%s)" % (SCRIPT_NAME, SCRIPT_VERSION))
IJ.log("  probabilities : %s  (%d file(s))" % (PROB_DIR, len(tif_files)))
IJ.log("  ROIs          : %s  (%d file(s))" % (ROI_DIR, len(roi_files)))
IJ.log("  open with Bio-Formats, split channels, analyse channel %d"
       % SIGNAL_CHANNEL)
IJ.log("  threshold %d-%d (8-bit)   watershed=%s"
       % (THRESHOLD_MIN, THRESHOLD_MAX, doWatershed))
IJ.log("  size %s-%s %s   circularity %s-%s"
       % (MIN_SIZE, "inf" if MAX_SIZE == float("inf") else MAX_SIZE,
          "px" if SIZE_IN_PIXELS else "calibrated", minCirc, maxCirc))
IJ.log("  include holes=%s   exclude on edges=%s   show=%s"
       % (includeHoles, excludeEdges, showMode))
IJ.log("  particle ROI export: %s" % particleExport)
IJ.log("  counting settings: %s" % COUNT_SRC)
IJ.log("  " + COUNTING_TEXT)
IJ.log("  key pattern %r   ->   %d matched pair(s)"
       % (KEY_PATTERN, len(matched)))
if REQUIRE_IN_NAME or EXCLUDE_IN_NAME:
	IJ.log("  filename filter: require %r, exclude %r"
	       % (REQUIRE_IN_NAME, EXCLUDE_IN_NAME))
IJ.log("=" * 64)

if tif_dupes or roi_dupes:
	lines = (["  images   '%s': %s" % (k, ", ".join(fs))
	          for k, fs in sorted(tif_dupes.items())]
	         + ["  ROI sets '%s': %s" % (k, ", ".join(fs))
	            for k, fs in sorted(roi_dupes.items())])
	for ln in lines:
		IJ.log("  ! duplicate key -> " + ln.strip())
	stop("Duplicate keys",
	     "More than one file shares the same RegionXXXX key, so the script "
	     "cannot tell which one you mean:\n\n%s\n\n"
	     "Type the text that identifies the one you want (e.g. \"_C2\") "
	     "into 'Only use images whose name contains', or set REQUIRE_IN_NAME."
	     % "\n".join(lines[:15]))
SLIDE_WARNING = slide_folder_warning([("probability folder", PROB_DIR, 1),
                                      ("ROI folder", ROI_DIR, 1)])
if SLIDE_WARNING:
	log_slide_warning(SLIDE_WARNING)
for f in tif_nokey:
	IJ.log("  ! no key extracted from image '%s' - ignored" % f)
for f in roi_nokey:
	IJ.log("  ! no key extracted from ROI set '%s' - ignored" % f)
if tif_only:
	IJ.log("  ! %d image(s) with no matching ROI set: %s"
	       % (len(tif_only), ", ".join([tif_by_key[k] for k in tif_only[:15]])))
if roi_only:
	IJ.log("  ! %d ROI set(s) with no matching image: %s"
	       % (len(roi_only), ", ".join([roi_by_key[k] for k in roi_only[:15]])))

if not matched:
	stop("No matched pairs",
	     "Found %d probability image(s) and %d ROI set(s), but nothing "
	     "paired up.\n\n"
	     "Example image name : %s\n"
	     "Example ROI name   : %s\n\n"
	     "Pairing uses the leading token matched by KEY_PATTERN, "
	     "currently %r: every file needs that token at the start of its "
	     "name.\n\nSee the Log for the full inventory."
	     % (len(tif_files), len(roi_files),
	        sorted(tif_files)[0], sorted(roi_files)[0], KEY_PATTERN))

# ---- output folder (after checks)
parent_src = PROB_DIR if OUTPUT_PARENT_SOURCE == "tif" else ROI_DIR
_out_name = (re.sub(r'[\\/:*?"<>|]', "_", (outFolderName or "").strip()).strip()
             or "particle_counts")
_out_parent = (outParentDir.getAbsolutePath() if outParentDir is not None
               else os.path.dirname(os.path.normpath(parent_src)))
OUT_EXISTED = os.path.isdir(os.path.join(_out_parent, _out_name))
OUT_DIR = resolve_output_dir(parent_src, outFolderName, "particle_counts",
                             outParentDir)
if OUT_DIR is None:
	raise SystemExit

CSV_PATH = os.path.join(OUT_DIR, RESULTS_CSV_NAME)
CSV_ARCHIVE = None
CSV_WILL_ARCHIVE = os.path.exists(CSV_PATH) and not overwrite
CSV_PREV = os.path.splitext(RESULTS_CSV_NAME)[0] + "_previous_<date-time>.csv"

# ---- settings check
n_tif_all = len(tifs_in(PROB_DIR))
first_tif = tif_by_key[matched[0]]
first_roi = roi_by_key[matched[0]]
first_stem = os.path.splitext(first_tif)[0]
check = [w_ for w_ in (
    other_stage_warning(PROB_DIR, "probability folder"),
    SLIDE_WARNING and slide_check_line(SLIDE_WARNING),
    None,
    excludeEdges and EDGE_WARNING) if w_] + stale_lines(
    [(os.path.join(PROB_DIR, tif_by_key[k]), os.path.join(ROI_DIR, roi_by_key[k]))
     for k in matched])
check.append("Probability maps: %s" % PROB_DIR)
counted = "%d image(s) will be counted (paired with an ROI set)" % len(matched)
left = []
if n_tif_all > len(tif_files):
	left.append("%d left out by the name filter" % (n_tif_all - len(tif_files)))
if tif_nokey:
	left.append("%d with no RegionXXXX key" % len(tif_nokey))
if left:
	counted += "; " + ", ".join(left)
check.append("   " + counted)
check.append("ROI sets: %s  (%d .zip file(s))" % (ROI_DIR, len(roi_files)))
if tif_only:
	check.append("Images with no ROI set: %d (%s)" % (
	    len(tif_only), short_list([tif_by_key[k] for k in tif_only])))
if roi_only:
	check.append("ROI sets with no image: %d (%s)" % (
	    len(roi_only), short_list([roi_by_key[k] for k in roi_only])))
if not tif_only and not roi_only:
	check.append("Unmatched files: none")
filt = (["must contain '%s'" % REQUIRE_IN_NAME] if REQUIRE_IN_NAME else []) + \
       (["must not contain '%s'" % EXCLUDE_IN_NAME] if EXCLUDE_IN_NAME else [])
check.append("Name filter: " + (filt and "image names " + " and ".join(filt)
                                or "none (every .tif is used)"))
check.append("First pair: %s + %s" % (first_tif, first_roi))
check.extend(ind(image_header_lines(first_tif, os.path.join(PROB_DIR, first_tif))))
check.extend(header_warnings([(tif_by_key[k],
                               os.path.join(PROB_DIR, tif_by_key[k]))
                              for k in matched]))
try:
	first_rois = filter_rois(read_roiset(os.path.join(ROI_DIR, first_roi)))
	check.append("   %d ROI(s) counted in %s" % (len(first_rois), first_roi))
	check.extend(ind(roi_overlap_lines(first_roi, first_rois)))
except StepError, e:
	check.append("   ROI set %s could not be read: %s" % (first_roi, str(e)))
check += tuned_lines() + [threshold_text(THRESHOLD_MIN, THRESHOLD_MAX),
                          COUNTING_TEXT]
check += ["Watershed: %s" % ("on" if doWatershed else "off"),
          "Particle size (%s): %s to %s; circularity %s to %s" % (
              "pixels" if SIZE_IN_PIXELS else "calibrated units^2", MIN_SIZE,
              "no limit" if MAX_SIZE == float("inf") else MAX_SIZE, minCirc,
              maxCirc),
          "Include holes: %s; exclude particles on edges: %s" % (
              "yes" if includeHoles else "no", "yes" if excludeEdges else "no"),
          "Output folder: %s (%s)" % (
              OUT_DIR, "already there" if OUT_EXISTED else "new")]
if CSV_WILL_ARCHIVE:
	csv_state = ("already there: it will be kept as %s and a new one "
	             "written" % CSV_PREV)
elif os.path.exists(CSV_PATH):
	csv_state = "already there: it will be replaced (Overwrite is ticked)"
else:
	csv_state = "new file"
check.append("Results CSV: %s in the output folder (%s)"
             % (RESULTS_CSV_NAME, csv_state))
saved = ["%s/%s%s" % (d_, first_stem, x_) for on_, d_, x_ in (
    (SAVE_THRESHOLDED, THRESHOLDED_SUBFOLDER, "_thresh.tif"),
    (doWatershed and SAVE_WATERSHED, WATERSHED_SUBFOLDER, "_watershed.tif"),
    (not QC_NONE, QC_SUBFOLDER, "_QC.tif")) if on_]
check.append("Saved per image: %s" % (", ".join(saved) or "no images"))
exports = [first_stem + x_ for on_, x_ in (
    (EXPORT_INDIVIDUAL, PARTICLE_INDIVIDUAL_SUFFIX + ".zip"),
    (EXPORT_COMBINED, PARTICLE_COMBINED_SUFFIX + ".roi")) if on_]
check.append("Particle ROIs: " + (exports and "%s/%s" % (
    PARTICLE_ROI_SUBFOLDER, " and ".join(exports)) or "not exported"))
if writeLog:
	check.append("Debug log: _counting_log.csv")
if not confirm_settings(SCRIPT_NAME, experiment_lines(LAYOUT_FOLDER) + check, CONFIRM_BEFORE_RUN):
	remove_if_new_and_empty(OUT_DIR, OUT_EXISTED)
	IJ.log("%s: cancelled at the settings check; nothing was processed."
	       % SCRIPT_NAME)
	raise SystemExit

THRESH_DIR, WSHED_DIR, QC_DIR, PART_DIR = [
    on_ and make_subfolder(d_) or None for on_, d_ in (
        (SAVE_THRESHOLDED, THRESHOLDED_SUBFOLDER),
        (doWatershed and SAVE_WATERSHED, WATERSHED_SUBFOLDER),
        (not QC_NONE, QC_SUBFOLDER), (not EXPORT_NONE, PARTICLE_ROI_SUBFOLDER))]

IJ.log("  output        : %s" % OUT_DIR)
if CSV_WILL_ARCHIVE:
	IJ.log("  ! %s already exists: it will be kept as %s and a new one "
	       "written" % (RESULTS_CSV_NAME, CSV_PREV))
for d_, what in ((THRESH_DIR, "thresholded images"),
                 (WSHED_DIR, "watershed images  "),
                 (PART_DIR, "particle ROIs     ")):
	if d_:
		IJ.log("  %s -> %s" % (what, d_))

# ==== RUN
rows = OrderedDict()
all_roi_names = []
done, failed, warned, sanity_flagged = [], [], [], []
converted = []
scales = {}                 # image -> prob_scale()
debug_rows = []
WHOLE = "__WHOLE_IMAGE__"
want_outlines = bool(QC_DIR) or bool(PART_DIR)

def count_one(i, key):
	tif_name = tif_by_key[key]
	roi_name = roi_by_key[key]
	stem = os.path.splitext(tif_name)[0]
	tag = "[%d/%d] %s" % (i + 1, len(matched), tif_name)
	IJ.showProgress(i, len(matched))
	IJ.showStatus(tag + " - opening")
	imp = mask = None
	notes, info = [], []
	counts = OrderedDict()
	means_txt = ""
	written = set()

	def save_tif(img, path, what):
		if IJ.saveAsTiff(img, path):
			written.add(path)
		elif what:
			notes.append(what + " image could not be saved")

	try:
		rois = read_roiset(os.path.join(ROI_DIR, roi_name))
		n_all = len(rois)
		rois = filter_rois(rois)
		if not rois:
			raise StepError(
			    "every ROI in %s was excluded by ONLY_THESE_ROIS / "
			    "SKIP_THESE_ROIS (%d ROI(s) in the file)." % (roi_name, n_all))
		if len(rois) != n_all:
			info.append("%d of %d ROI(s) analysed after filtering"
			            % (len(rois), n_all))

		imp, notes, info2, channel_means = open_and_prepare(
		    os.path.join(PROB_DIR, tif_name))
		info.extend(info2)
		means_txt = " ".join(["ch%d=%.1f" % (j + 1, m)
		                      for j, m in enumerate(channel_means)])
		if any("CHANNEL SANITY CHECK" in n for n in notes):
			sanity_flagged.append(tif_name)
		for n in info2:
			if n.startswith("probability map: "):
				if "fixed scale" in n:
					converted.append(tif_name)
				scales[tif_name] = prob_scale(n[17:])
		w, h = imp.getWidth(), imp.getHeight()

		IJ.showStatus(tag + " - thresholding")
		mask = make_mask(imp)
		if THRESH_DIR:
			save_tif(mask, os.path.join(THRESH_DIR, stem + "_thresh.tif"),
			         "thresholded")
		if doWatershed:
			IJ.showStatus(tag + " - watershed")
			try:
				IJ.run(mask, "Watershed", "")
			except ANY_ERROR, e:
				raise StepError("Watershed failed: %s" % str(e))
			if WSHED_DIR:
				save_tif(mask, os.path.join(WSHED_DIR, stem + "_watershed.tif"),
				         "watershed")
			work = mask
			lo, hi = MASK_THRESHOLD
		else:
			work = imp
			lo, hi = THRESHOLD_MIN, THRESHOLD_MAX

		IJ.showStatus(tag + " - counting")
		particles = find_particles(work, lo, hi, want_outlines)
		if INCLUDE_WHOLE_IMAGE_COLUMN:
			counts[WHOLE] = len(particles)
		off_image = []
		on_image = OrderedDict()
		for rname, roi in rois.items():
			b = roi.getBounds()
			if b.x >= w or b.y >= h or b.x + b.width <= 0 or b.y + b.height <= 0:
				off_image.append(rname)
			else:
				on_image[rname] = roi
		add_in_order(all_roi_names, list(rois.keys()))
		in_roi, homes = assign_particles(particles, on_image)
		areas = dict([(n, area_in_image(r, w, h)) for n, r in on_image.items()])
		for rname in rois:
			counts[rname] = in_roi.get(rname, MISSING_VALUE)

		# total_particles: each particle once if its centre is in any ROI
		total = len([hm for hm in homes if hm])
		n_multi = len([hm for hm in homes if len(hm) > 1])
		n_outside = len(particles) - total
		if n_multi:
			info.append("%d particle(s) have their centre in more than one "
			            "ROI and count in each of them" % n_multi)
		if n_outside:
			info.append("%d particle(s) have their centre outside every ROI "
			            "and are not counted" % n_outside)
		collected = []
		if want_outlines:
			collected = particle_rois_to_export(particles, homes, on_image)
		if off_image:
			notes.append(
			    "%d ROI(s) lie entirely outside the image, so their "
			    "column is %s (not counted): %s. Usually a mismatched pair "
			    "or a Y-flip in the conversion step."
			    % (len(off_image), MISSING_VALUE, ", ".join(off_image[:8])))
		work.deleteRoi()

		IJ.showStatus(tag + " - saving")
		if QC_DIR and collected:
			qc_path = os.path.join(QC_DIR, stem + "_QC.tif")
			try:
				if QC_OVERLAY:
					ov = Overlay()
					for _n, r in collected:
						ov.add(r)
					work.setOverlay(ov)
					flat = work.flatten()
					save_tif(flat, qc_path, None)
					close_quietly(flat)
					work.setOverlay(None)
				elif QC_MASKS:
					mimp = ImagePlus(stem + "_QC",
					                 particles_to_mask(collected, w, h))
					save_tif(mimp, qc_path, None)
					close_quietly(mimp)
			except ANY_ERROR, e:
				notes.append("QC image could not be saved: %s" % str(e))

		if PART_DIR and not collected:
			info.append("no particles found, so no ROIs were exported")
		elif PART_DIR:
			if EXPORT_INDIVIDUAL:
				zpath = os.path.join(
				    PART_DIR, stem + PARTICLE_INDIVIDUAL_SUFFIX + ".zip")
				try:
					write_roiset(collected, zpath)
					written.add(zpath)
				except ANY_ERROR, e:
					notes.append("individual particle ROIs could not "
					             "be written: %s" % str(e))
			if EXPORT_COMBINED:
				rpath = os.path.join(
				    PART_DIR, stem + PARTICLE_COMBINED_SUFFIX + ".roi")
				try:
					comb = raster_union([r for _n, r in collected])
					if comb is collected[0][1]:
						comb = comb.clone()   # keep the particle's name
					comb.setName(stem + PARTICLE_COMBINED_SUFFIX)
					RoiEncoder(rpath).write(comb)
					written.add(rpath)
				except StepError, e:
					notes.append("combined particle ROI: %s" % str(e))
				except ANY_ERROR, e:
					notes.append("combined particle ROI could not be "
					             "written: %s" % str(e))

		info.extend(remove_stale_outputs(stem, written))
		rows[key] = {"image": tif_name, "roi_file": roi_name, "areas": areas,
		             "um": um_per_px(rois, imp),
		             "counts": counts, "means": means_txt, "total": total}
		done.append(tif_name)
		if notes:
			warned.append(tif_name)
		IJ.log("%s   %d ROI(s), %d particle(s) total   [%s]"
		       % (tag, len(counts), total, means_txt))
		for nte in info:
			IJ.log("      - %s" % nte)
		for nte in notes:
			IJ.log("      ! %s" % nte)
		for rname, c in counts.items():
			debug_rows.append([key, tif_name, roi_name, rname, str(c),
			                   "%dx%d" % (w, h),
			                   "%d-%d" % (THRESHOLD_MIN, THRESHOLD_MAX),
			                   str(doWatershed), means_txt,
			                   "ok" if not notes else " | ".join(notes)])
	except ANY_ERROR, e:
		failed.append(tif_name)
		se = isinstance(e, StepError)
		msg = str(e) if se else "%s: %s" % (type(e).__name__, str(e))
		IJ.log("%s  FAILED%s: %s" % (tag, "" if se else " - UNEXPECTED ERROR", msg))
		debug_rows.append([key, tif_name, roi_name, "", "", "", "",
		                   str(doWatershed), means_txt,
		                   ("FAILED: " if se else "UNEXPECTED ERROR: ")
		                   + msg.replace("\n", " ")])
	finally:
		close_quietly(mask, imp)

# Convert to Mask and Watershed need Prefs.blackBackground; restored below.
Prefs.blackBackground = True
try:
	for i, key in enumerate(matched):
		count_one(i, key)
finally:
	Prefs.blackBackground = _prev_black_background

IJ.showProgress(1.0)
IJ.showStatus("")

# 32-bit maps on different scales (0-1, 0-255): flag the minority (all on a tie).
odd_scale = []
_s01 = [n for n in done if scales.get(n) == "32-bit 0-1"]
_s255 = [n for n in done if scales.get(n) == "32-bit 0-255"]
if _s01 and _s255:
	odd_scale = (_s01 if len(_s01) < len(_s255) else _s255
	             if len(_s255) < len(_s01) else _s01 + _s255)
	IJ.log("")
	for n in odd_scale:
		IJ.log("WARNING: %s (%s): %s" % (n, scales[n], SCALE_TEXT))

# ---- write CSV
csv_written = False
REGION_PATH = None
columns = list(all_roi_names)
if INCLUDE_WHOLE_IMAGE_COLUMN:
	columns = [WHOLE] + columns
if rows:
	try:
		if CSV_WILL_ARCHIVE and os.path.exists(CSV_PATH):
			CSV_ARCHIVE = archive_results_csv(CSV_PATH)
			IJ.log("Existing results CSV kept as: %s" % CSV_ARCHIVE)
		write_csv(CSV_PATH, None, [
		    ["image"] + GROUP_COLS + ["roi_file", "n_rois", "total_particles", "threshold",
		     "watershed", "channel_means"]
		    + ["whole_image" if c == WHOLE else c for c in columns]] + [
		    [r["image"]] + GROUP_VALS + [r["roi_file"], len(r["counts"]), r["total"],
		     "%d-%d" % (THRESHOLD_MIN, THRESHOLD_MAX), doWatershed, r["means"]]
		    + [r["counts"].get(c, MISSING_VALUE) for c in columns]
		    for r in rows.values()])
		csv_written = True
		IJ.log("-" * 64)
		IJ.log("Results: %s" % CSV_PATH)
		IJ.log("  %d row(s) x %d ROI column(s)" % (len(rows), len(columns)))
	except IOError, e:
		IJ.log("ERROR: the results CSV could not be written: %s" % str(e))
		IJ.error("Could not write results",
		         "The counts were computed but the CSV could not be saved:"
		         "\n\n%s\n\n%s\n\nCheck that it is not open in Excel, "
		         "then run again." % (CSV_PATH, str(e)))

	REGION_PATH = WRITE_REGION_TABLE and os.path.join(OUT_DIR, REGION_TABLE_NAME)
	try:
		if REGION_PATH:
			if os.path.exists(REGION_PATH) and not overwrite:
				IJ.log("Existing region table kept as: %s"
				       % archive_results_csv(REGION_PATH))
			reg_rows = []
			for r in rows.values():
				reg_rows += region_rows(r["image"], r["roi_file"], r["counts"],
				                        r["areas"], r["um"])
			write_csv(REGION_PATH, None, [["image"] + GROUP_COLS + REGION_TABLE_HEADER]
			          + reg_rows)
			IJ.log("Counts by region: %s (%d row(s))" % (REGION_PATH, len(reg_rows)))
			no_um = [r["image"] for r in rows.values() if not r["um"]]
			if no_um:
				IJ.log("  ! area_mm2 and cells_per_mm2 are %s for %d image(s): the "
				       "pixel size is unknown (run 2a again, which stores it in the "
				       "ROIs): %s" % (MISSING_VALUE, len(no_um), ", ".join(no_um[:5])))
	except ANY_ERROR, e:
		IJ.log("ERROR: the region table could not be written: %s" % str(e))
		REGION_PATH = None

	inconsistent = [rows[k]["image"] for k in rows
	                if len(rows[k]["counts"]) != len(columns)]
	if inconsistent:
		IJ.log("  ! %d image(s) did not contain every ROI; missing cells "
		       "are '%s': %s" % (len(inconsistent), MISSING_VALUE,
		                         ", ".join(inconsistent[:10])))

# ---- debug log
log_path = None
if writeLog:
	log_path = os.path.join(OUT_DIR, "_counting_log.csv")
	if os.path.exists(log_path) and not overwrite:
		IJ.log("Debug log NOT saved - the file already exists (tick "
		       "'Overwrite an existing results CSV' to replace it): %s" % log_path)
		log_path = None
	else:
		try:
			lay = LAYOUT_ROW and [LAYOUT_CSV, LAYOUT_TEXT] or []
			write_csv(log_path, "key,image_file,roi_file,roi_name,count,"
			          "dimensions,threshold,watershed,channel_means,status,"
			          "probability_scale" + (lay and ",layout_csv,layout_row" or ""), [
			    r[:-1] + [r[-1] + (" | " + SCALE_TEXT if r[1] in odd_scale
			                       else ""), scales.get(r[1], "")] + lay
			    for r in debug_rows]
			    + [[k, tif_by_key[k]] + [""] * 7 + ["no matching ROI set", ""] + lay
			       for k in tif_only]
			    + [[k, "", roi_by_key[k]] + [""] * 6 + ["no matching image", ""] + lay
			       for k in roi_only])
			IJ.log("Debug log: %s" % log_path)
		except IOError, e:
			log_path = None
			IJ.log("WARNING: could not write the debug log: %s" % str(e))

# ---- parameter record
record_path = None
if WRITE_PARAMETER_RECORD and OUT_DIR:
	record_path = write_run_record(OUT_DIR, SCRIPT_NAME, SCRIPT_VERSION, [
	    ("#Dialog", ""),
	] + layout_record() + [
	    ("Folder of ilastik probability .tif files (probabilities/)", PROB_DIR),
	    ("Folder of ROI .zip files (rois/)", ROI_DIR),
	    ("Only use images whose name contains (blank = all)", NAME_FILTER),
	    ("Counting settings", SOURCE),
	] + [(l, DIALOG_VALUES[k]) for l, k in zip((
	    "Threshold: minimum (8-bit)", "Threshold: maximum (8-bit)",
	    "Watershed before Analyze Particles", "Analyze Particles: minimum size",
	    "Analyze Particles: maximum size (0 = no limit)",
	    "Analyze Particles: minimum circularity",
	    "Analyze Particles: maximum circularity", "Include holes",
	    "Exclude particles on edges"), TUNED_KEYS)] + [
	    ("Show", showMode),
	    ("Export particle ROIs", particleExport),
	    ("Output location (blank = one level above the input)",
	     outParentDir.getAbsolutePath() if outParentDir is not None
	     else "(blank)"),
	    ("Name for the new output folder", outFolderName),
	    ("Overwrite an existing results CSV", overwrite),
	    ("Write a debug log CSV to the output folder", writeLog),
	    ("#Counting settings used", ""),
	    ("source", COUNT_SRC),
	] + [(k, globals()[k]) for k in TUNED_KEYS] + [
	    ("#Configuration", ""),
	] + [(n, globals()[n]) for n in (
	    "SIGNAL_CHANNEL SANITY_CHECK_CHANNELS SANITY_MAX_RATIO "
	    "SIZE_IN_PIXELS KEY_PATTERN CASE_INSENSITIVE_KEYS").split()] + [
	    ("REQUIRE_IN_NAME (effective)", REQUIRE_IN_NAME)] + [
	    (n, globals()[n]) for n in (
	    "EXCLUDE_IN_NAME ONLY_THESE_ROIS SKIP_THESE_ROIS "
	    "INCLUDE_WHOLE_IMAGE_COLUMN PARTICLE_ROI_NAME_TEMPLATE "
	    "SAVE_THRESHOLDED SAVE_WATERSHED OUTPUT_PARENT_SOURCE "
	    "RESULTS_CSV_NAME MISSING_VALUE TIF_EXTENSIONS "
	    "CONFIRM_BEFORE_RUN").split()] + [
	    ("#Inputs", ""),
	    ("probability folder", PROB_DIR),
	    ("ROI folder", ROI_DIR),
	    ("output folder", OUT_DIR),
	    ("experiment layout", LAYOUT_CSV or "(none)"),
	    ("layout row", LAYOUT_TEXT),
	    ("matched pairs", len(matched)),
	] + [("pair %s" % k, "%s + %s" % (tif_by_key[k], roi_by_key[k]))
	     for k in matched])
	if record_path:
		IJ.log("Parameter record: %s" % record_path)

# ---- completion notice
IJ.log("-" * 64)
summary = ["Images counted : %d" % len(done)]
if sanity_flagged:
	summary.append("Channel check  : %d image(s) FLAGGED - see Log"
	               % len(sanity_flagged))
if warned:
	summary.append("With warnings  : %d  (see Log)" % len(warned))
if failed:
	summary.append("FAILED         : %d  (see Log)" % len(failed))
	summary.extend(["   FAILED: %s" % f for f in failed[:10]])
	if len(failed) > 10:
		summary.append("   ... and %d more" % (len(failed) - 10))
if tif_only or roi_only:
	summary.append("Unmatched      : %d image(s), %d ROI set(s)"
	               % (len(tif_only), len(roi_only)))
if converted:
	summary.append("16/32-bit maps : %d converted to 8-bit on a fixed "
	               "scale (see Log)" % len(converted))
summary.append("ROI columns    : %d" % len(all_roi_names))
for line in summary:
	IJ.log(line)
IJ.log("-" * 64)

IJ.beep()
problems = (sanity_flagged or warned or SLIDE_WARNING or tif_only
            or roi_only or odd_scale)
title = "Counting complete" + (" - with failures" if failed or not csv_written
                                else " - with problems" if problems else "")
body = ["Finished %d matched pair(s)." % len(matched), ""] + summary + [""]
if csv_written:
	body += ["Results CSV:", "   " + CSV_PATH]
	if REGION_PATH and os.path.exists(REGION_PATH):
		body += ["Counts, areas and cells per mm2 by region:", "   " + REGION_PATH]
else:
	body.append("NO results CSV was written - see the Log.")
if CSV_ARCHIVE:
	body += ["The results CSV that was already there was kept as:",
	         "   " + CSV_ARCHIVE,
	         "(tick 'Overwrite an existing results CSV' to replace it "
	         "instead)"]
body.append("")
for label, p in (("Output folder", OUT_DIR), ("Thresholded images", THRESH_DIR),
                 ("Watershed images", WSHED_DIR), ("QC images", QC_DIR),
                 ("Particle ROIs", PART_DIR), ("Parameter record", record_path),
                 ("Debug log", log_path)):
	if p:
		body.append((label + ":").ljust(20) + p)
if SLIDE_WARNING:
	body += ["", "WARNING: " + SLIDE_WARNING[0]] + SLIDE_WARNING[1:]
if odd_scale:
	body += ["", "WARNING: %d image(s) %s:" % (len(odd_scale), SCALE_TEXT)]
	body += ["   %s (%s)" % (n, scales[n]) for n in odd_scale[:10]]
if sanity_flagged:
	body += ["", "%d image(s) failed the channel sanity check: still "
	         "counted, but check the Log before trusting them."
	         % len(sanity_flagged)]
elif failed or problems:
	body += ["", "Check the Log window for details."]
IJ.showMessage(title, "\n".join(body))
