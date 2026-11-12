# 3_Count_Particles_per_ROI_(single).py - count thresholded ilastik
# detections inside every anatomical ROI of ONE image (as the batch does).
# Menu: Plugins > Kapur Lab Cell Counting > Single image >
#       3 Count Particles per ROI (single)
# Reads : one probability .tif/.tiff (probabilities/) and its ROI .zip (rois/).
# Writes: into particle_counts/ (default) as the batch does, adding or
#   replacing this image's row in particle_counts.csv.

#@ File    (label="Slide folder (the scripts find its subfolders)", style="directory") slideDir
#@ String  (label="Region (its MBF folder; blank = choose from a list)", value="", required=false) regionName
#@ String  (label="Section (e.g. Region0011; blank = choose from a list)", value="", required=false) sectionKey
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
#@ File    (label="Output location (blank = beside the folder that holds the input file)", style="directory", required=false) outParentDir
#@ String  (label="Name for the new output folder", value="particle_counts") outFolderName
#@ Boolean (label="Overwrite an existing results CSV", value=false) overwrite
#@ Boolean (label="Write a debug log CSV to the output folder", value=false) writeLog
#@ Boolean (label="Show the result on screen when done", value=true) showResult

# =========================================================================
# ===  USER CONFIGURATION  ================================================
# =========================================================================
# Nothing below the END banner needs editing for routine use.

# ---- THRESHOLD
# Set in the DIALOG on the fixed 8-bit scale: 128 = p 0.50, 179 ~ 0.70, 204 ~ 0.80.

# ---- CHANNELS
# The channel (or plane, with no channel dimension) analysed; 1 = 'signal'.
SIGNAL_CHANNEL = 1

# Warn when the signal channel is not the dimmest.
SANITY_CHECK_CHANNELS = True

# Warn when mean(signal) > mean(brightest other channel) * this ratio.
SANITY_MAX_RATIO = 1.0

# ---- SAVING INTERMEDIATE IMAGES (subfolders of the output folder)
SAVE_THRESHOLDED = True
THRESHOLDED_SUBFOLDER = "thresholded"

SAVE_WATERSHED = True                 # when watershed is ticked
WATERSHED_SUBFOLDER = "watershed"

# QC images (when 'Show' is not "Nothing").
QC_SUBFOLDER = "QC"

# ---- PARTICLE ROI EXPORT
# Stage 4 looks for these suffixes: change them there too.
PARTICLE_ROI_SUBFOLDER = "particle_rois"
PARTICLE_COMBINED_SUFFIX = "_particles_combined"     # -> .roi
PARTICLE_INDIVIDUAL_SUFFIX = "_particles"            # -> .zip

# <region>_<index>, numbered per region (widen past 9999 per region).
PARTICLE_ROI_NAME_TEMPLATE = "%s_%04d"

# ---- FILENAME STANDARD
# Files pair by the LEADING RegionXXXX token.
KEY_PATTERN = r"^(Region\d+)"
CASE_INSENSITIVE_KEYS = True

# True warns (never stops) when the chosen files are not from one slide.
WARN_ON_DIFFERENT_SLIDE_FOLDERS = True

# The BATCH version's filename filters; not applied here.
REQUIRE_IN_NAME = ""
EXCLUDE_IN_NAME = ""

# ---- WHICH ROIs TO COUNT IN
# Every ROI in the zip by default; restrict with either list (any case).
ONLY_THESE_ROIS = []          # e.g. ["Caudoputamen", "Nucleus accumbens"]
SKIP_THESE_ROIS = []          # e.g. ["Tissue"]  - the whole-tissue outline

# Also report a count over the whole image, ignoring every ROI?
INCLUDE_WHOLE_IMAGE_COLUMN = False

# ---- SIZE UNITS: True = pixels (recommended); False = calibrated um^2.
SIZE_IN_PIXELS = True

# ---- OUTPUT
# Output folder goes one level ABOVE the folder of the "tif" or the "roi".
OUTPUT_PARENT_SOURCE = "tif"

# The batch's CSV: this section's row is added (replaced only with Overwrite).
RESULTS_CSV_NAME = "particle_counts.csv"

# One row per image and ROI with its count, area (pixels and mm2) and
# cells per mm2; the pixel size comes from 2a (stored in the ROIs).
WRITE_REGION_TABLE = True
REGION_TABLE_NAME = "particle_counts_by_region.csv"

# For an ROI missing from an image, or entirely outside it.
MISSING_VALUE = "NA"

TIF_EXTENSIONS = [".tif", ".tiff"]

# ---- PARAMETER RECORD (_run_..._<time>.txt, every setting used)
WRITE_PARAMETER_RECORD = True

# ---- SAFETY CHECKS
# Show the "Check settings" window first. False skips it (warnings logged).
CONFIRM_BEFORE_RUN = True

# =========================================================================
# ===  END OF USER CONFIGURATION  =========================================
# =========================================================================

SCRIPT_NAME = "3_Count_Particles_per_ROI_(single)"
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
from java.awt import Color

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
			v = dict([[x.strip() for x in ln.split("=", 1)] for ln in
			          open(p).read().splitlines() if "=" in ln and "#" != ln[:1]])
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

# First columns of every results CSV (group columns after image).
CSV_BASE_HEADER = ["image", "roi_file", "n_rois", "total_particles",
                   "threshold", "watershed", "channel_means"]

def split_header(header):
	"""(group columns: between image and roi_file, ROI columns)."""
	n = header.index("roi_file") if "roi_file" in header else 1
	return header[1:n], header[n + len(CSV_BASE_HEADER) - 1:]

def read_results_csv(path):
	"""(header, rows) of a results CSV, or StepError (text after "it")."""
	import csv
	try:
		fh = open(path, "rb")
		try:
			raw = fh.read()
			data = [r for r in csv.reader(raw.splitlines(), delimiter=";" if
			        raw.split("\n")[0].count(";") > raw.split("\n")[0].count(",")
			        else ",")]
		finally:
			fh.close()
	except (IOError, csv.Error), e:
		raise StepError("it could not be read (%s)" % str(e))
	data = [r for r in data if [c for c in r if c.strip()]]
	if not data:
		raise StepError("it is empty")
	header = list(data[0])
	if header and header[0].startswith("\xef\xbb\xbf"):
		header[0] = header[0][3:]
	g = split_header(header)[0]
	if header[:1] + header[1 + len(g):len(g) + len(CSV_BASE_HEADER)] != CSV_BASE_HEADER:
		raise StepError("its first columns are not %s"
		                % ", ".join(CSV_BASE_HEADER))
	rows = [list(r) for r in data[1:]]
	for i, r in enumerate(rows):
		if len(r) != len(header):
			raise StepError("line %d has %d cells but the header has %d"
			                % (i + 2, len(r), len(header)))
	return header, rows

def same_section(name):
	"""A row of this section (this file, or another with its key)."""
	k = key_from(TIF_NAME)
	return name == TIF_NAME or (k is not None and key_from(name) == k)

def merge_results_row(header, rows, base_cells, roi_cells):
	"""(header, rows, "added"/"replaced", extra rows dropped); new group
	columns are filled from the layout row."""
	old_g, roi_cols = split_header(header)
	roi_cols = list(roi_cols)
	add_in_order(roi_cols, [col for col, _v in roi_cells])
	gv = dict(zip(GROUP_COLS, GROUP_VALS))
	new_g = [c for c in GROUP_COLS if c not in old_g]
	groups = old_g + new_g
	new_g = [gv[c] for c in new_g]
	new_header = ["image"] + groups + CSV_BASE_HEADER[1:] + roi_cols
	pad = len(new_header) - len(header) - len(new_g)
	values = dict(roi_cells)
	line = [str(base_cells[0])] + [gv.get(c, "") for c in groups] + [
	    str(x) for x in base_cells[1:]] + [
	    str(values[c]) if c in values else MISSING_VALUE for c in roi_cols]
	out, action, extra, n = [], "added", 0, 1 + len(old_g)
	for r in rows:
		if same_section(r[0]):
			if action == "added":
				out.append(line)
				action = "replaced"
			else:
				extra += 1
			continue
		out.append(r[:n] + new_g + r[n:] + [MISSING_VALUE] * pad)
	if action == "added":
		out.append(line)
	return new_header, out, action, extra

def write_region_table(path, new):
	"""This section's rows replace its old ones in the region table."""
	import csv
	head, old = ["image"] + GROUP_COLS + REGION_TABLE_HEADER, []
	if os.path.exists(path):
		fh = open(path, "rb")
		try:
			raw = fh.read()
		finally:
			fh.close()
		first = raw.split("\n")[0]
		data = [r for r in csv.reader(raw.splitlines(), delimiter=first.count(";")
		        > first.count(",") and ";" or ",") if r]
		if data and "roi_file" in data[0]:
			oh = [c.replace("\xef\xbb\xbf", "") for c in data[0]]
			groups = oh[1:oh.index("roi_file")]
			head = ["image"] + groups + [c for c in GROUP_COLS if c not in groups] \
			    + REGION_TABLE_HEADER
			old = [[dict(zip(oh, r)).get(c, "") for c in head] for r in data[1:]
			       if r and not same_section(r[0])]
	gv = dict(zip(GROUP_COLS, GROUP_VALS))
	n = 1 + len(GROUP_VALS)
	rows = [[x[0]] + [gv.get(c, "") for c in head[1:len(head) - len(REGION_TABLE_HEADER)]]
	        + x[n:] for x in new]
	write_csv_atomic(path, head, old + rows)
	IJ.log("Counts by region: %s (%d row(s) for this image)" % (path, len(rows)))
	if new and not um:
		IJ.log("  ! area_mm2 and cells_per_mm2 are %s: the pixel size is unknown "
		       "(run 2a again, which stores it in the ROIs)" % MISSING_VALUE)


def write_csv_atomic(path, header, rows):
	"""Write a temporary file beside path, then move it into place."""
	import time
	from java.io import File
	from java.nio.file import Files, StandardCopyOption, \
	    AtomicMoveNotSupportedException
	tmp = os.path.join(os.path.dirname(path), "_%s.%d.tmp"
	                   % (os.path.basename(path), int(time.time() * 1000)))
	try:
		write_csv(tmp, None, [header] + rows)
		src, dst = File(tmp).toPath(), File(path).toPath()
		try:
			Files.move(src, dst, StandardCopyOption.REPLACE_EXISTING,
			           StandardCopyOption.ATOMIC_MOVE)
		except AtomicMoveNotSupportedException:
			Files.move(src, dst, StandardCopyOption.REPLACE_EXISTING)
	except ANY_ERROR, e:
		try:
			if os.path.exists(tmp):
				os.remove(tmp)
		except ANY_ERROR:
			pass
		raise IOError(str(e))

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

# ---- slide folder -> folders/files (skipped when given directly: tests)
if globals().get("slideDir") is not None:
	from java.io import File as _F
	_SLIDE = slideDir.getAbsolutePath()
	_REGION = layout_pick_region(_SLIDE, regionName)
	if _REGION is None:
		raise SystemExit
	_KEYS = layout_keys(layout_find(_SLIDE, _REGION, "probabilities"), ('.tif', '.tiff'))
	_SEC = layout_pick_section(_KEYS, sectionKey)
	if _SEC is None:
		raise SystemExit
	_K = key_from(_SEC)
	_HINTS = layout_files_for(layout_find(_SLIDE, _REGION, "processed_bgsub_cleared"), _K, (".tif", ".tiff"))
	_c_probFile = layout_files_for(layout_find(_SLIDE, _REGION, "probabilities"), _K, ('.tif', '.tiff'))
	_c_roiFile = layout_files_for(layout_find(_SLIDE, _REGION, "rois"), _K, ('.zip',))
	_got = layout_confirm(SCRIPT_NAME + " - " + _SEC, _SLIDE, _REGION, [
	    ('ilastik probability .tif file (from probabilities/)', "choice", layout_default(_c_probFile, _HINTS), _c_probFile, True),
	    ('ROI .zip file (from rois/)', "choice", layout_default(_c_roiFile, _HINTS), _c_roiFile, True),
	])
	if _got is None:
		raise SystemExit
	probFile = _F(_got[0]) if _got[0] else None
	roiFile = _F(_got[1]) if _got[1] else None

PROB_PATH = probFile.getAbsolutePath()
ROI_PATH = roiFile.getAbsolutePath()
TIF_NAME = os.path.basename(PROB_PATH)
ROI_NAME = os.path.basename(ROI_PATH)
STEM = os.path.splitext(TIF_NAME)[0]

# Experiment table row; counting settings (tuned values replace the dialog's).
LAYOUT_FOLDER = globals().get("_SLIDE") or os.path.dirname(PROB_PATH)
_r = globals().get("_REGION") or os.path.dirname(os.path.dirname(PROB_PATH))
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

WHOLE = "__WHOLE_IMAGE__"

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
if not os.path.isfile(PROB_PATH):
	stop("Probability image", "The probability image does not exist:\n%s\n\n"
	     "Choose an existing file in the dialog." % PROB_PATH)
if os.path.splitext(TIF_NAME)[1].lower() not in TIF_EXTENSIONS:
	stop("Probability image", "This does not look like a probability "
	     "image:\n%s\n\nExpected one of: %s (from probabilities/)."
	     % (PROB_PATH, " ".join(TIF_EXTENSIONS)))
if not os.path.isfile(ROI_PATH):
	stop("ROI file", "The ROI file does not exist:\n%s\n\nChoose an existing "
	     "file in the dialog." % ROI_PATH)
if not ROI_NAME.lower().endswith((".zip", ".roi")):
	stop("ROI file", "This does not look like an ROI set:\n%s\n\nExpected a "
	     ".zip RoiSet (or a single .roi) from rois/." % ROI_PATH)

# ==== SETUP
src_file = PROB_PATH if OUTPUT_PARENT_SOURCE == "tif" else ROI_PATH
_out_name = (re.sub(r'[\\/:*?"<>|]', "_", (outFolderName or "").strip()).strip()
             or "particle_counts")
_out_parent = (outParentDir.getAbsolutePath() if outParentDir is not None
               else os.path.dirname(os.path.normpath(os.path.dirname(src_file))))
OUT_EXISTED = os.path.isdir(os.path.join(_out_parent, _out_name))
OUT_DIR = resolve_output_dir(os.path.dirname(src_file), outFolderName,
                             "particle_counts", outParentDir)
if OUT_DIR is None:
	raise SystemExit

# The shared results CSV: check it now, before any work.
CSV_PATH = os.path.join(OUT_DIR, RESULTS_CSV_NAME)
CSV_EXISTED = os.path.exists(CSV_PATH)
CSV_ROWS_BEFORE, CSV_ROW_EXISTS = 0, False
if CSV_EXISTED:
	try:
		_hdr, _rows = read_results_csv(CSV_PATH)
	except StepError, e:
		stop("Results file not readable",
		     "%s\nalready exists, but %s.\n\nIt must be a results CSV "
		     "written by 3 Count Particles per ROI; it was left untouched. "
		     "Move or rename it, or choose a different output folder."
		     % (CSV_PATH, str(e)))
	CSV_SAME = [r[0] for r in _rows if same_section(r[0])]
	CSV_ROW_EXISTS = bool(CSV_SAME)
	if CSV_ROW_EXISTS and not overwrite:
		stop("Results row already exists",
		     "A row for %s already exists in %s - tick 'Overwrite "
		     "an existing results CSV' to replace that row.\n\n"
		     "%s\n\nStopping now so an earlier run is not lost."
		     % (", ".join(CSV_SAME), RESULTS_CSV_NAME, CSV_PATH))
	CSV_ROWS_BEFORE = len(_rows)
	_hdr = _rows = None

# Files picked by hand: a key mismatch is only a warning.
img_key, roi_key = key_from(TIF_NAME), key_from(ROI_NAME)
key_warning = None
if img_key != roi_key and not (img_key is None and roi_key is None):
	key_warning = ("The two files do not share the same RegionXXXX key "
	               "(image: %s, ROI set: %s): check that this is the right "
	               "pair."
	               % (img_key or "none", roi_key or "none"))
SLIDE_WARNING = slide_folder_warning([("probability image", PROB_PATH, 2),
                                      ("ROI set", ROI_PATH, 2)])

# ---- settings check
check = [w_ for w_ in (
    other_stage_warning(os.path.dirname(PROB_PATH),
                        "folder that holds the probability image"),
    key_warning and "! " + key_warning,
    SLIDE_WARNING and slide_check_line(SLIDE_WARNING),
    excludeEdges and EDGE_WARNING) if w_] + stale_lines([(PROB_PATH, ROI_PATH)])
check.append("Probability image: %s" % PROB_PATH)
check.extend(ind(image_header_lines(TIF_NAME, PROB_PATH, "probability image")))
check.extend(header_warnings([(TIF_NAME, PROB_PATH)]))
check.append("ROI set: %s" % ROI_PATH)
try:
	first_rois = filter_rois(read_roiset(ROI_PATH))
	check.append("   %d ROI(s) counted" % len(first_rois))
	check.extend(ind(roi_overlap_lines(ROI_NAME, first_rois)))
except StepError, e:
	check.append("   the ROI set could not be read: %s" % str(e))
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
if not CSV_EXISTED:
	csv_state = "new file; this image's row will be its first row"
elif CSV_ROW_EXISTS:
	csv_state = ("%d row(s) already; the row of this section (%s) will be "
	             "replaced (Overwrite is ticked)" % (CSV_ROWS_BEFORE, ", ".join(CSV_SAME)))
else:
	csv_state = ("%d row(s) already; this image's row will be added"
	             % CSV_ROWS_BEFORE)
check.append("Results CSV: %s in the output folder (%s)"
             % (RESULTS_CSV_NAME, csv_state))
saved = ["%s/%s%s" % (d_, STEM, x_) for on_, d_, x_ in (
    (SAVE_THRESHOLDED, THRESHOLDED_SUBFOLDER, "_thresh.tif"),
    (doWatershed and SAVE_WATERSHED, WATERSHED_SUBFOLDER, "_watershed.tif"),
    (not QC_NONE, QC_SUBFOLDER, "_QC.tif")) if on_]
check.append("Saved: %s" % (", ".join(saved) or "no images"))
exports = [STEM + x_ for on_, x_ in (
    (EXPORT_INDIVIDUAL, PARTICLE_INDIVIDUAL_SUFFIX + ".zip"),
    (EXPORT_COMBINED, PARTICLE_COMBINED_SUFFIX + ".roi")) if on_]
check.append("Particle ROIs: " + (exports and "%s/%s" % (
    PARTICLE_ROI_SUBFOLDER, " and ".join(exports)) or "not exported"))
if writeLog:
	check.append("Debug log: _counting_log_%s.csv" % STEM)
check.append("Show the result on screen: %s" % ("yes" if showResult else "no"))
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

for _ln in ("=" * 64, "Particle counting per ROI, single image  (%s v%s)"
            % (SCRIPT_NAME, SCRIPT_VERSION),
            "  probability image : %s" % PROB_PATH,
            "  ROI set           : %s" % ROI_PATH,
            "  output            : %s" % OUT_DIR,
            "  open with Bio-Formats, split channels, analyse channel %d"
            % SIGNAL_CHANNEL,
            "  threshold %d-%d (8-bit)   watershed=%s"
            % (THRESHOLD_MIN, THRESHOLD_MAX, doWatershed),
            "  size %s-%s %s   circularity %s-%s"
            % (MIN_SIZE, "inf" if MAX_SIZE == float("inf") else MAX_SIZE,
               "px" if SIZE_IN_PIXELS else "calibrated", minCirc, maxCirc),
            "  include holes=%s   exclude on edges=%s   show=%s"
            % (includeHoles, excludeEdges, showMode),
            "  particle ROI export: %s" % particleExport,
            "  counting settings: %s" % COUNT_SRC,
            "  " + COUNTING_TEXT):
	IJ.log(_ln)
if key_warning:
	IJ.log("  ! WARNING: " + key_warning)
if SLIDE_WARNING:
	log_slide_warning(SLIDE_WARNING)
IJ.log("=" * 64)

# ==== RUN
tag = "[1/1] %s" % TIF_NAME
IJ.showProgress(0, 1)
IJ.showStatus(tag + " - opening")
imp = mask = failure = None
keep_open, notes, info, collected = False, [], [], []
counts, rois = OrderedDict(), OrderedDict()
areas, um = {}, None
means_txt = scale = ""
total = w = h = 0
written = set()

def col_name(c):
	return "whole_image" if c == WHOLE else c

def save_tif(img, path, what):
	if IJ.saveAsTiff(img, path):
		written.add(path)
	elif what:
		notes.append(what + " image could not be saved")

# Convert to Mask and Watershed need Prefs.blackBackground; restored below.
_prev_black_background = Prefs.blackBackground
Prefs.blackBackground = True
try:
	rois = read_roiset(ROI_PATH)
	n_all = len(rois)
	rois = filter_rois(rois)
	if not rois:
		raise StepError(
		    "every ROI in %s was excluded by ONLY_THESE_ROIS / "
		    "SKIP_THESE_ROIS (%d ROI(s) in the file)." % (ROI_NAME, n_all))
	if len(rois) != n_all:
		info.append("%d of %d ROI(s) analysed after filtering"
		            % (len(rois), n_all))

	imp, notes, info2, channel_means = open_and_prepare(PROB_PATH)
	info.extend(info2)
	for n in info2:
		if n.startswith("probability map: "):
			scale = prob_scale(n[17:])
			info.append("probability scale: " + scale)
	means_txt = " ".join(["ch%d=%.1f" % (j + 1, m)
	                      for j, m in enumerate(channel_means)])
	w, h = imp.getWidth(), imp.getHeight()

	IJ.showStatus(tag + " - thresholding")
	mask = make_mask(imp)
	if THRESH_DIR:
		save_tif(mask, os.path.join(THRESH_DIR, STEM + "_thresh.tif"),
		         "thresholded")
	if doWatershed:
		IJ.showStatus(tag + " - watershed")
		try:
			IJ.run(mask, "Watershed", "")
		except ANY_ERROR, e:
			raise StepError("Watershed failed: %s" % str(e))
		if WSHED_DIR:
			save_tif(mask, os.path.join(WSHED_DIR, STEM + "_watershed.tif"),
			         "watershed")
		work = mask
		lo, hi = MASK_THRESHOLD
	else:
		work = imp
		lo, hi = THRESHOLD_MIN, THRESHOLD_MAX

	IJ.showStatus(tag + " - counting")
	want_outlines = bool(QC_DIR) or bool(PART_DIR) or bool(showResult)
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
	in_roi, homes = assign_particles(particles, on_image)
	areas = dict([(n, area_in_image(r, w, h)) for n, r in on_image.items()])
	um = um_per_px(rois, imp)
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
	if want_outlines:
		collected = particle_rois_to_export(particles, homes, on_image)
	if off_image:
		notes.append(
		    "%d ROI(s) lie entirely outside the image, so their column "
		    "is %s (not counted): %s. Usually a mismatched pair or a "
		    "Y-flip in the conversion step."
		    % (len(off_image), MISSING_VALUE, ", ".join(off_image[:8])))
	work.deleteRoi()

	IJ.showStatus(tag + " - saving")
	if QC_DIR and collected:
		qc_path = os.path.join(QC_DIR, STEM + "_QC.tif")
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
				mimp = ImagePlus(STEM + "_QC", particles_to_mask(collected, w, h))
				save_tif(mimp, qc_path, None)
				close_quietly(mimp)
		except ANY_ERROR, e:
			notes.append("QC image could not be saved: %s" % str(e))

	if PART_DIR and not collected:
		info.append("no particles found, so no ROIs were exported")
	elif PART_DIR:
		if EXPORT_INDIVIDUAL:
			zpath = os.path.join(
			    PART_DIR, STEM + PARTICLE_INDIVIDUAL_SUFFIX + ".zip")
			try:
				write_roiset(collected, zpath)
				written.add(zpath)
			except ANY_ERROR, e:
				notes.append("individual particle ROIs could not be "
				             "written: %s" % str(e))
		if EXPORT_COMBINED:
			rpath = os.path.join(
			    PART_DIR, STEM + PARTICLE_COMBINED_SUFFIX + ".roi")
			try:
				comb = raster_union([r for _n, r in collected])
				if comb is collected[0][1]:
					comb = comb.clone()   # keep the particle's name
				comb.setName(STEM + PARTICLE_COMBINED_SUFFIX)
				RoiEncoder(rpath).write(comb)
				written.add(rpath)
			except StepError, e:
				notes.append("combined particle ROI: %s" % str(e))
			except ANY_ERROR, e:
				notes.append("combined particle ROI could not be "
				             "written: %s" % str(e))

	info.extend(remove_stale_outputs(STEM, written))
	keep_open = bool(showResult)
except StepError, e:
	failure = str(e)
except ANY_ERROR, e:
	failure = "UNEXPECTED ERROR: %s: %s" % (type(e).__name__, str(e))
finally:
	Prefs.blackBackground = _prev_black_background
	close_quietly(*([mask] if keep_open else [mask, imp]))

IJ.showProgress(1.0)
IJ.showStatus("")
if failure is None:
	IJ.log("%s   %d ROI(s), %d particle(s) total   [%s]"
	       % (tag, len(counts), total, means_txt))
	for nte in info:
		IJ.log("      - %s" % nte)
	for nte in notes:
		IJ.log("      ! %s" % nte)
else:
	IJ.log("%s  FAILED: %s" % (tag, failure))

# ---- write CSV
# Read again in case it changed while this image was counted.
csv_written, csv_action, csv_rows = False, None, 0
if failure is None:
	try:
		old_header, old_rows = list(CSV_BASE_HEADER), []
		if os.path.exists(CSV_PATH):
			try:
				old_header, old_rows = read_results_csv(CSV_PATH)
			except StepError, e:
				raise IOError("the existing file changed during the run "
				              "and %s" % str(e))
		base = [TIF_NAME, ROI_NAME, len(counts), total,
		        "%d-%d" % (THRESHOLD_MIN, THRESHOLD_MAX),
		        doWatershed, means_txt]
		roi_cells = [(col_name(c), counts[c]) for c in counts]
		new_header, new_rows, csv_action, extra = merge_results_row(
		    old_header, old_rows, base, roi_cells)
		if csv_action == "replaced" and not overwrite:
			raise IOError("a row for %s was added to %s by another run "
			              "meanwhile - tick 'Overwrite an existing results "
			              "CSV' to replace that row" % (TIF_NAME, RESULTS_CSV_NAME))
		write_csv_atomic(CSV_PATH, new_header, new_rows)
		csv_written = True
		csv_rows = len(new_rows)
		if WRITE_REGION_TABLE:
			try:
				write_region_table(os.path.join(OUT_DIR, REGION_TABLE_NAME),
				                   region_rows(TIF_NAME, ROI_NAME, counts, areas, um))
			except ANY_ERROR, e:
				IJ.log("ERROR: the region table could not be written: %s" % str(e))
		IJ.log("-" * 64)
		IJ.log("Results: %s" % CSV_PATH)
		IJ.log("  row for %s %s; the file now has %d row(s) x %d ROI "
		       "column(s)" % (TIF_NAME, csv_action, csv_rows,
		                      len(split_header(new_header)[1])))
		if extra:
			IJ.log("  ! %d further row(s) for %s were removed (one row "
			       "per section)" % (extra, key_from(TIF_NAME) or TIF_NAME))
	except IOError, e:
		IJ.log("ERROR: the results CSV could not be written: %s" % str(e))
		IJ.error("Could not write results",
		         "The counts were computed but the CSV could not be saved:"
		         "\n\n%s\n\n%s\n\nCheck that it is not open in Excel, then "
		         "run again. The existing file was not changed."
		         % (CSV_PATH, str(e)))

# ---- debug log
log_path = None
if writeLog:
	log_path = os.path.join(OUT_DIR, "_counting_log_%s.csv" % STEM)
	if os.path.exists(log_path) and not overwrite:
		IJ.log("Debug log NOT saved - the file already exists (tick "
		       "'Overwrite an existing results CSV' to replace it): %s" % log_path)
		log_path = None
	else:
		lead = [img_key or "", TIF_NAME, ROI_NAME]
		thr = "%d-%d" % (THRESHOLD_MIN, THRESHOLD_MAX)
		lay = LAYOUT_ROW and [LAYOUT_CSV, LAYOUT_TEXT] or []
		try:
			write_csv(log_path, "key,image_file,roi_file,roi_name,count,"
			          "dimensions,threshold,watershed,channel_means,status,"
			          "probability_scale" + (lay and ",layout_csv,layout_row" or ""), [
			    lead + [col_name(rname), str(c),
			            "%dx%d" % (w, h), thr, str(doWatershed), means_txt,
			            "ok" if not notes else " | ".join(notes), scale] + lay
			    for rname, c in counts.items()] if failure is None else [
			    lead + ["", "", "", "", str(doWatershed), means_txt,
			            "FAILED: " + failure.replace("\n", " "), scale] + lay])
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
	    ("ilastik probability .tif file (from probabilities/)", PROB_PATH),
	    ("ROI .zip file (from rois/)", ROI_PATH),
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
	    ("Output location (blank = beside the folder that holds the input file)",
	     outParentDir.getAbsolutePath() if outParentDir is not None
	     else "(blank)"),
	    ("Name for the new output folder", outFolderName),
	    ("Overwrite an existing results CSV", overwrite),
	    ("Write a debug log CSV to the output folder", writeLog),
	    ("Show the result on screen when done", showResult),
	    ("#Counting settings used", ""),
	    ("source", COUNT_SRC),
	] + [(k, globals()[k]) for k in TUNED_KEYS] + [
	    ("#Configuration", ""),
	] + [(n, globals()[n]) for n in (
	    "SIGNAL_CHANNEL SANITY_CHECK_CHANNELS SANITY_MAX_RATIO SIZE_IN_PIXELS "
	    "KEY_PATTERN CASE_INSENSITIVE_KEYS ONLY_THESE_ROIS SKIP_THESE_ROIS "
	    "INCLUDE_WHOLE_IMAGE_COLUMN PARTICLE_ROI_NAME_TEMPLATE "
	    "SAVE_THRESHOLDED SAVE_WATERSHED OUTPUT_PARENT_SOURCE "
	    "RESULTS_CSV_NAME MISSING_VALUE TIF_EXTENSIONS "
	    "CONFIRM_BEFORE_RUN").split()] + [
	    ("#Inputs", ""),
	    ("probability image", PROB_PATH),
	    ("ROI set", ROI_PATH),
	    ("image key / ROI key", "%s / %s" % (img_key, roi_key)),
	    ("output folder", OUT_DIR),
	    ("experiment layout", LAYOUT_CSV or "(none)"),
	    ("layout row", LAYOUT_TEXT),
	])
	if record_path:
		IJ.log("Parameter record: %s" % record_path)

# ---- show the result
if keep_open and imp is not None:
	try:
		ov = Overlay()
		for roi_, col_ in ([(r, Color.CYAN) for r in rois.values()]
		                   + [(r, Color.YELLOW) for _n, r in collected]):
			r = roi_.clone()
			r.setStrokeColor(col_)
			ov.add(r)
		imp.deleteRoi()
		imp.setOverlay(ov)
		imp.setTitle(STEM)
		imp.changes = False
		imp.show()
		rt = ResultsTable()
		for rname, c in counts.items():
			rt.incrementCounter()
			rt.addValue("ROI", col_name(rname))
			rt.addValue("Count", c)
		rt.show("Counts - %s" % STEM)
	except ANY_ERROR, e:
		IJ.log("WARNING: the result could not be shown on screen: %s: %s"
		       % (type(e).__name__, str(e)))

# ---- completion notice
IJ.log("-" * 64)
if failure is None:
	summary = ["Image counted  : %s" % TIF_NAME,
	           "ROIs           : %d, %d particle(s) in total"
	           % (len(counts), total)]
	summary += ["   %s: %s" % (col_name(rname), c) for rname, c in counts.items()]
	maps = [n for n in info if n.startswith("probability map: ")]
	if maps:
		summary.append("Probability map: " + maps[0][len("probability map: "):])
else:
	summary = ["FAILED         : %s" % TIF_NAME, "   " + failure]
if key_warning:
	summary += ["", "WARNING: " + key_warning]
if SLIDE_WARNING:
	summary += ["", "WARNING: " + SLIDE_WARNING[0]] + SLIDE_WARNING[1:]
for line in summary:
	IJ.log(line)
IJ.log("-" * 64)

IJ.beep()
sanity_flagged = any("CHANNEL SANITY CHECK" in n for n in notes)
title = "Counting complete" + (
    " - with failures" if failure is not None or not csv_written else
    " - with problems" if notes or key_warning or SLIDE_WARNING else "")
body = summary + [""]
if csv_written:
	body += ["Results CSV (row for this image %s; %d row(s) in the file):"
	         % (csv_action, csv_rows), "   " + CSV_PATH]
	if WRITE_REGION_TABLE:
		body += ["Counts, areas and cells per mm2 by region:",
		         "   " + os.path.join(OUT_DIR, REGION_TABLE_NAME)]
else:
	body.append("NO results CSV was written - see the Log.")
body.append("")
for label, p in (("Output folder", OUT_DIR), ("Thresholded images", THRESH_DIR),
                 ("Watershed images", WSHED_DIR), ("QC images", QC_DIR),
                 ("Particle ROIs", PART_DIR), ("Parameter record", record_path),
                 ("Debug log", log_path)):
	if p:
		body.append((label + ":").ljust(20) + p)
if sanity_flagged:
	body += ["", "The image failed the channel sanity check: still counted, "
	         "but check the Log before trusting it."]
elif failure is not None or notes:
	body += ["", "Check the Log window for details."]
IJ.showMessage(title, "\n".join(body))
