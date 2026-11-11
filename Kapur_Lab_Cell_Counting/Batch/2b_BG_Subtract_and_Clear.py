# 2b_BG_Subtract_and_Clear.py
#
# Rolling-ball background subtraction, then clear everything outside the
# tissue ROI, for a whole folder of images (the images fed to ilastik).
#
# Menu:   Plugins > Kapur Lab Cell Counting > Batch > 2b BG Subtract and Clear
# Reads:  a folder of raw .tif/.tiff images (tifs/) and a folder of RoiSet
#         .zip files (rois/, from step 2a), paired by the leading RegionXXXX
#         token of the file names.
# Writes: <image stem>_bgsub[_C<n>].tif into a new folder (default
#         processed_bgsub_cleared) one level above tifs/, a parameter record
#         _run_...txt, and optionally _processing_log.csv.
#
# Fiji / ImageJ Jython script.
#
# For every raw .tif that has a matching RoiSet .zip:
#   1. open the image
#   2. optionally keep a single channel (the one destined for ilastik)
#   3. subtract background over the WHOLE image (rolling ball)
#   4. build the 'clear' ROI and set every pixel outside it to CLEAR_VALUE
#   5. save to a new folder created one level above the input folder
#
# Why this order: the rolling ball needs to see the real off-tissue
# background. Clearing first would replace it with a hard zero edge and the
# radius you optimised would no longer mean the same thing.
#
# The 'clear' ROI is, by default, the union of every ROI in the set (this
# works with any 2a composition, e.g. 'Unify by hemisphere', which writes
# Left / Right / Unpaired ROIs). It can instead be one named ROI (such as
# "Tissue") or the union of a subset you pick from a list built by
# scanning the actual ROI files.
#
# Before it runs, the script shows a Check settings window that lists the
# folders, how many image/ROI pairs will be processed, the first file name
# and the output name it gives, and the settings that change the result
# (rolling ball radius, clear mode, channel). It also warns about likely
# mistakes, such as keeping every channel of a multi-channel image or
# pointing the image folder at a later stage's output. Press Run to go
# ahead or Cancel to stop before anything is written.
#
# Usage: Plugins > Kapur Lab Cell Counting > Batch > 2b BG Subtract and
#        Clear, or open this file in the Script Editor (File > New >
#        Script..., or Plugins > Scripting > Script Editor) with Language =
#        Python (Jython) and press Run.

#@ File    (label="Slide folder (the scripts find its subfolders)", style="directory") slideDir
#@ String  (label="Region (its MBF folder; blank = choose from a list)", value="", required=false) regionName
#@ String  (label="Only use images whose name contains (blank = all; e.g. _C2)", value="", required=false) nameFilter
#@ Double  (label="Rolling ball radius (pixels)", value=50.0, min=0.1) rollingBall
#@ String  (label="Clear outside...", choices={"union of ALL ROIs in the set", "one named ROI", "union of ROIs I pick from a list"}, style="listBox") clearMode
#@ String  (label="   ...name of that ROI (named mode only)", value="Tissue") allTissueName
#@ Integer (label="Channel to process (0 = all channels)", value=0, min=0) processChannel
#@ File    (label="Output location (blank = one level above the input)", style="directory", required=false) outParentDir
#@ String  (label="Name for the new output folder", value="processed_bgsub_cleared") outFolderName
#@ Boolean (label="Overwrite existing output files", value=false) overwrite
#@ Boolean (label="Write a debug log CSV to the output folder", value=false) writeLog


# =========================================================================
# ===  USER CONFIGURATION  ================================================
# =========================================================================

# ---- THE 'CLEAR' ROI ----------------------------------------------------
#
# Mode is chosen in the dialog; the default is "union of ALL ROIs in the
# set". These refine the two union modes only; named mode ignores them and
# uses just the one ROI you name. Named mode needs an ROI of that name in
# every set: 2a's 'Unify by hemisphere' composition writes Left / Right /
# Unpaired and no "Tissue" ROI, so keep the union mode for those sets.
#
# Names are matched case-insensitively, and a name here also matches its
# split pieces (listing "Tissue" also covers Tissue_2, Tissue_3, ...).
#
# CLEAR_INCLUDE_NAMES  non-empty -> ONLY these ROIs are considered.
# CLEAR_EXCLUDE_NAMES  these ROIs are always dropped.
#
# Picking from the list in the dialog fills these in for you, and the Log
# prints a paste-ready copy so a run can be reproduced exactly later.

CLEAR_INCLUDE_NAMES = []       # e.g. ["Caudoputamen", "Nucleus accumbens"]
CLEAR_EXCLUDE_NAMES = []       # e.g. ["Ventricle", "Fiber tracts"]

# The converter suffixes repeated names as Name_2, Name_3, ... A region
# split into several pieces arrives that way. True merges every piece.
# False uses only the exact-named ROI and warns that pieces were ignored.
# (Named mode only; union modes always include every piece.)
MERGE_TISSUE_PIECES = True

# How many ROI files to scan when building the pick list. The list is the
# union of names found. 0 scans every matched file.
SCAN_MAX_FILES = 25


# ---- BACKGROUND SUBTRACTION --------------------------------------------
#
# The radius is a dialog parameter. These are the remaining Subtract
# Background options, matching the checkboxes in the ImageJ dialog.

BG_LIGHT_BACKGROUND = False      # True for dark objects on a light field
BG_SLIDING_PARABOLOID = False    # True copes better with uneven illumination
BG_DISABLE_SMOOTHING = False     # True preserves noise; usually leave False

# Process every slice of the (possibly channel-reduced) stack?
PROCESS_ALL_SLICES = True


# ---- CLEARING -----------------------------------------------------------
#
# Value written outside the clear ROI. 0 is almost always what you want for
# fluorescence, so cleared area contributes nothing to a later threshold.
# It is written as a raw pixel value (e.g. 0-65535 for 16-bit images; for
# RGB images it becomes the grey colour CLEAR_VALUE,CLEAR_VALUE,CLEAR_VALUE).
# ImageJ's own background colour is not touched.
CLEAR_VALUE = 0


# ---- OUTPUT -------------------------------------------------------------
#
# The output folder is created one level ABOVE this folder:
#   "roi"  -> alongside the ROI folder (default). In the protocol layout
#             tifs/ and rois/ share the slide folder, so this is the same
#             place; in the Set Up Slide Folders layout rois/ is in the
#             region's "<region> MBF" folder, so the output goes there too.
#   "tif"  -> alongside the raw image folder
OUTPUT_PARENT_SOURCE = "roi"

# Appended to build the output filename:
#   Region0011_ChannelFITCTRITC_Seq0011_MAX_C2_bgsub.tif
OUTPUT_SUFFIX = "_bgsub"

# Appended as well when a single channel was extracted: ..._bgsub_C2.tif
# A 'Channel to process' other than 0 on a single-channel image fails that
# image (there is nothing to extract, and the _C<n> name could be wrong).
CHANNEL_SUFFIX_TEMPLATE = "_C%d"

# Extensions treated as input images.
TIF_EXTENSIONS = [".tif", ".tiff"]

# Save a plain-text parameter record (_run_...txt) in the output folder,
# listing every setting this run used.
WRITE_PARAMETER_RECORD = True


# ---- FILENAME STANDARD --------------------------------------------------
#
# Pairing key is the leading RegionXXXX token. Everything after it is
# ignored, so every stage of the workflow still pairs correctly no matter
# how much has been appended:
#
#   tifs/Region0011_ChannelFITCTRITC_Seq0011_MAX_C2.tif
#   processed_bgsub_cleared/Region0011_ChannelFITCTRITC_Seq0011_MAX_C2_bgsub.tif
#   probabilities/Region0011_ChannelFITCTRITC_Seq0011_MAX_C2_bgsub.tif (ilastik)
#   particle_counts/thresholded/..._bgsub_thresh.tif, particle_rois/..._particles.zip
#
# (When this script keeps one channel of a multi-channel image, the
# channel goes after _bgsub: ..._MAX_bgsub_C2.tif.)
#
# Anchoring at the FRONT matters. Keying on the last number in the name
# would read "_C2" as the section number and collide every channel-2 file.
KEY_PATTERN = r"^(Region\d+)"
CASE_INSENSITIVE_KEYS = True

# Files are paired by their RegionXXXX token only, so an image folder from
# one slide and a ROI folder from another would pair up without any error
# (and Fiji remembers the folders chosen last time, which makes this an
# easy slip). True warns - in the Log and in the completion message - when
# the paired input folders do not sit in the same slide folder (the folder
# that holds tifs/, rois/, probabilities/, ...). It never stops the run.
WARN_ON_DIFFERENT_SLIDE_FOLDERS = True

# Filename filters for the images, applied before pairing. Use
# REQUIRE_IN_NAME when one folder holds several channels or variants per
# section, so that only one of them is picked up (e.g. "_C2"). Blank
# disables the filter. The dialog field "Only use images whose name
# contains" overrides REQUIRE_IN_NAME for one run when it is filled in.
REQUIRE_IN_NAME = ""
EXCLUDE_IN_NAME = ""


# ---- SAFETY CHECKS ------------------------------------------------------
#
# Show the "Check settings" window before processing starts. False skips
# it, e.g. for unattended runs (warnings are still written to the Log).
CONFIRM_BEFORE_RUN = True

# =========================================================================
# ===  END OF USER CONFIGURATION  =========================================
# =========================================================================
# Nothing below this line needs editing for routine use.

SCRIPT_NAME = "2b_BG_Subtract_and_Clear"
SCRIPT_VERSION = "2.0"


import os
import re

from ij import IJ
from java.lang import Exception as JavaException
from ij.plugin import Duplicator

from javax.swing import (JList, JScrollPane, JOptionPane, JPanel, JLabel,
                         JComboBox, BoxLayout, ListSelectionModel)
from java.awt import Dimension


# ------------------------------------------------ slide-folder check
# A folder whose name holds the word MBF ("hippocampus MBF") is a region
# folder made by Set Up Slide Folders inside a slide folder.
MBF_FOLDER_RE = re.compile(r"(^|[^A-Za-z0-9])MBF([^A-Za-z0-9]|$)", re.IGNORECASE)


def slide_folder_warning(entries):
	"""Warning lines when the inputs are not from one slide folder, else None.

	entries is a list of (label, path, levels): the slide folder of path is
	found by going up 'levels' folders (1 for tifs/, rois/, ...; 2 for a
	file inside one of them, or for particle_counts/thresholded/).
	"""
	if not WARN_ON_DIFFERENT_SLIDE_FOLDERS or len(entries) < 2:
		return None
	slides = []
	regions = set()       # distinct "<region> MBF" folders used
	for _label, path, levels in entries:
		p = os.path.normpath(os.path.abspath(path))
		for _k in range(levels):
			p = os.path.dirname(p)
		# A region's "<region> MBF" folder is part of its slide folder
		# (Set Up Slide Folders layout: tifs/ in the slide, rois/ etc. in
		# the MBF folder), so step out of it.
		if MBF_FOLDER_RE.search(os.path.basename(p)):
			regions.add(os.path.normcase(p))
			p = os.path.dirname(p)
		slides.append(os.path.normcase(p))
	if len(set(slides)) <= 1 and len(regions) <= 1:
		return None
	if len(set(slides)) <= 1:
		return (["the inputs come from different region (MBF) folders of one slide:"]
		        + ["   %s: %s" % (label, path) for label, path, _l in entries]
		        + ["Check that these folders belong to the same region."])
	lines = ["the inputs do not come from the same slide folder:"]
	for label, path, _levels in entries:
		lines.append("   %s: %s" % (label, path))
	lines.append("Check that these folders belong to the same slide.")
	return lines


def log_slide_warning(lines):
	"""Write the slide-folder warning to the Log, prominently."""
	IJ.log("  " + "!" * 62)
	IJ.log("  ! WARNING: " + lines[0])
	for line in lines[1:]:
		IJ.log("  !   " + line.strip())
	IJ.log("  ! Files pair by RegionXXXX only, so folders from two slides or")
	IJ.log("  ! regions would pair without any error. Processing continues.")
	IJ.log("  " + "!" * 62)


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
	    ('Folder of raw .tif images (tifs/)', "dir", layout_find(_SLIDE, _REGION, "tifs"), None, True),
	    ('Folder of ROI .zip files (rois/)', "dir", layout_find(_SLIDE, _REGION, "rois"), None, True),
	])
	if _got is None:
		raise SystemExit
	tifDir = _F(_got[0]) if _got[0] else None
	roiDir = _F(_got[1]) if _got[1] else None


TIF_DIR = tifDir.getAbsolutePath()
ROI_DIR = roiDir.getAbsolutePath()
RADIUS = float(rollingBall)
TISSUE = allTissueName.strip()
CHANNEL = int(processChannel)

MODE_NAMED = clearMode.startswith("one named")
MODE_ALL = clearMode.startswith("union of ALL")
MODE_PICK = clearMode.startswith("union of ROIs I pick")

# The dialog's name filter overrides REQUIRE_IN_NAME for this run only.
NAME_FILTER = (nameFilter or "").strip()
REQUIRE_IN_NAME_CONFIG = REQUIRE_IN_NAME
if NAME_FILTER:
	REQUIRE_IN_NAME = NAME_FILTER
	REQUIRE_SOURCE = "dialog field 'Only use images whose name contains'"
else:
	REQUIRE_SOURCE = "REQUIRE_IN_NAME in the configuration block"


# ------------------------------------------------------------ clear ROI
def base_name(name):
	"""Strip the _2 / _3 piece suffix added by the converter."""
	return re.sub(r"_\d+$", "", name).lower()


def union_of(rois, names):
	"""Union of several ROIs, by name (raster union: fast with many ROIs)."""
	return raster_union([rois[n] for n in names])


def apply_include_exclude(names):
	inc = [s.lower() for s in CLEAR_INCLUDE_NAMES]
	exc = [s.lower() for s in CLEAR_EXCLUDE_NAMES]
	out = []
	for n in names:
		low, base = n.lower(), base_name(n)
		if inc and low not in inc and base not in inc:
			continue
		if low in exc or base in exc:
			continue
		out.append(n)
	return out


def build_clear_roi(rois, zipname):
	"""Return (roi, note, is_warning) for the region to keep.

	note is None or a line for the Log; is_warning is True when the note
	points at something the user should look at (not just information).
	"""
	note = None
	is_warning = False

	if MODE_NAMED:
		target = TISSUE.lower()
		exact = [n for n in rois.keys() if n.lower() == target]
		pieces = [n for n in rois.keys()
		          if re.match(r"^" + re.escape(target) + r"_\d+$", n.lower())]

		if not exact and not pieces:
			available = ", ".join(list(rois.keys())[:30])
			if len(rois) > 30:
				available += ", ... (%d more)" % (len(rois) - 30)
			raise StepError(
			    "no ROI named '%s' in %s.\n"
			    "      ROIs present: %s\n"
			    "      Choose 'union of ALL ROIs in the set' under 'Clear "
			    "outside...' (it works with any ROI set, including 2a's "
			    "Left / Right / Unpaired), or fix the ROI name in the "
			    "dialog, or check that this region was included in the "
			    "NeuroInfo export." % (TISSUE, zipname, available))

		if not exact and pieces:
			if not MERGE_TISSUE_PIECES:
				raise StepError(
				    "there is no ROI named exactly '%s' in %s, only split "
				    "pieces (%s). Set MERGE_TISSUE_PIECES = True to combine "
				    "them." % (TISSUE, zipname, ", ".join(pieces)))
			note = ("'%s' exists only as %d split piece(s); merged"
			        % (TISSUE, len(pieces)))
			chosen = pieces
		elif exact and pieces:
			if MERGE_TISSUE_PIECES:
				note = ("'%s' was split into %d piece(s); merged"
				        % (TISSUE, len(exact) + len(pieces)))
				chosen = exact + pieces
			else:
				note = ("'%s' has %d extra piece(s) (%s) that were IGNORED"
				        % (TISSUE, len(pieces), ", ".join(pieces)))
				is_warning = True
				chosen = exact
		else:
			chosen = exact

	else:
		# union modes
		chosen = apply_include_exclude(list(rois.keys()))
		if not chosen:
			raise StepError(
			    "every ROI in %s was removed by CLEAR_INCLUDE_NAMES / "
			    "CLEAR_EXCLUDE_NAMES, so there is nothing to keep.\n"
			    "      ROIs present: %s"
			    % (zipname, ", ".join(list(rois.keys())[:30])))
		if len(chosen) != len(rois):
			note = ("union of %d of %d ROI(s) after include/exclude"
			        % (len(chosen), len(rois)))
		else:
			note = "union of all %d ROI(s)" % len(chosen)

	if len(chosen) == 1:
		return rois[chosen[0]], note, is_warning
	return union_of(rois, chosen), note, is_warning


# ------------------------------------------------------------ processing
def open_image(path):
	"""Open with ImageJ's own TIFF reader, falling back to Bio-Formats.

	Never picks up whatever window happens to be open. Raises StepError.
	"""
	# ImageJ's TIFF reader opens a cut-off file silently (zero-filled).
	truncated = tiff_truncation_error(path)
	if truncated:
		raise StepError(truncated)
	try:
		# Opener errors go to the Log instead of a modal dialog. The flag is
		# static and survives a successful open, so it is always switched
		# off again: later IJ.error calls in this Fiji session must still
		# show a dialog.
		IJ.redirectErrorMessages()
		try:
			imp = IJ.openImage(path)
		finally:
			IJ.redirectErrorMessages(False)
	except (Exception, JavaException):
		imp = None
	if imp is not None:
		return imp
	try:
		imp, n_series = bf_open(path, 0)
	except StepError, e:
		raise StepError("the image could not be opened. ImageJ's TIFF "
		                "reader failed, then %s" % str(e))
	return imp


def image_type_warning(imp):
	"""A warning for bit depths this step does not expect, else None."""
	bd = imp.getBitDepth()
	if bd == 24:
		return ("RGB image: the rolling ball works on a brightness channel "
		        "computed from R, G and B (not on each colour separately), "
		        "and ilastik would receive colour data. Convert to separate "
		        "greyscale channels (step 1) if that was not intended.")
	if bd == 32:
		return ("32-bit (floating-point) image: processed and saved as "
		        "32-bit. Check that ilastik and your later thresholds "
		        "expect float values.")
	return None


def extract_channel(imp):
	"""Keep one channel, if requested. Returns (imp, note)."""
	if CHANNEL <= 0:
		return imp, None

	nch = imp.getNChannels()
	tag = CHANNEL_SUFFIX_TEMPLATE % CHANNEL
	title = imp.getTitle() or ""
	if nch == 1 and (tag + "_") in (os.path.splitext(title)[0] + "_"):
		# A stage 1 single-channel file already named for this channel
		# (e.g. ..._MAX_C2.tif with 'Channel to process' = 2): use it as is.
		return imp, "image has a single channel and its name says %s; used as is" % tag
	if nch == 1:
		# Nothing to extract. Saving it as ..._bgsub_C<n>.tif would label
		# the file with a channel number that may not be the stain it holds
		# (e.g. a stage 1 ..._C1.tif saved as ..._C1_bgsub_C2.tif).
		imp.close()
		raise StepError(
		    "'Channel to process' is %d, but the image has a single channel, "
		    "so there is no channel to extract. It would be saved as "
		    "..._bgsub%s.tif, a name that may not match the stain it holds.\n"
		    "      Set 'Channel to process' to 0 for single-channel images, "
		    "or to the channel named in the file (e.g. 2 for ..._C2.tif)."
		    % (CHANNEL, CHANNEL_SUFFIX_TEMPLATE % CHANNEL))
	if nch < CHANNEL:
		total = imp.getStackSize()
		imp.close()
		raise StepError(
		    "channel %d was requested but the image has only %d channel(s) "
		    "(%d slice(s) total).\n"
		    "      Set 'Channel to process' to 0 to keep every channel, or "
		    "to a valid channel index." % (CHANNEL, nch, total))

	picked = Duplicator().run(imp, CHANNEL, CHANNEL,
	                          1, imp.getNSlices(), 1, imp.getNFrames())
	imp.close()
	return picked, "extracted channel %d of %d" % (CHANNEL, nch)


def subtract_background(imp):
	opts = "rolling=%s" % RADIUS
	if BG_LIGHT_BACKGROUND:
		opts += " light"
	if BG_SLIDING_PARABOLOID:
		opts += " sliding"
	if BG_DISABLE_SMOOTHING:
		opts += " disable"
	if PROCESS_ALL_SLICES and imp.getStackSize() > 1:
		opts += " stack"
	try:
		IJ.run(imp, "Subtract Background...", opts)
	except (Exception, JavaException), e:
		raise StepError("background subtraction failed (options '%s'): %s"
		                % (opts, str(e)))
	return opts


def clear_outside(imp, roi):
	"""Set every pixel outside roi to CLEAR_VALUE. Returns a warning or None.

	Works directly on the pixel data (ip.fillOutside), so ImageJ's
	background colour is never changed and CLEAR_VALUE is written exactly,
	at any bit depth.
	"""
	if not roi.isArea():
		raise StepError("the clear ROI is a line or point selection, not an "
		                "area, so there is nothing to clear outside of.")
	b = roi.getBounds()
	w, h = imp.getWidth(), imp.getHeight()

	if b.width <= 0 or b.height <= 0:
		raise StepError("the clear ROI has zero area.")

	if b.x >= w or b.y >= h or b.x + b.width <= 0 or b.y + b.height <= 0:
		raise StepError(
		    "the clear ROI lies completely outside the image.\n"
		    "      ROI bounds %d,%d %dx%d vs image %dx%d.\n"
		    "      This is the classic symptom of a Y-flip or scale mismatch "
		    "in the XML-to-ROI conversion, or of pairing an image with the "
		    "wrong ROI set." % (b.x, b.y, b.width, b.height, w, h))

	clipped = None
	if b.x < 0 or b.y < 0 or b.x + b.width > w or b.y + b.height > h:
		clipped = ("the clear ROI extends past the image edge "
		           "(bounds %d,%d %dx%d vs image %dx%d)"
		           % (b.x, b.y, b.width, b.height, w, h))

	if imp.getBitDepth() == 24:
		v = max(0, min(255, int(CLEAR_VALUE)))
		fill_value = (v << 16) | (v << 8) | v
	else:
		fill_value = CLEAR_VALUE

	stack = imp.getStack()
	if PROCESS_ALL_SLICES:
		slices = range(1, stack.getSize() + 1)
	else:
		slices = [imp.getCurrentSlice()]
	try:
		for s in slices:
			ip = stack.getProcessor(s)
			ip.setValue(fill_value)
			ip.fillOutside(roi)
	except (Exception, JavaException), e:
		raise StepError("clearing outside the ROI failed: %s" % str(e))
	return clipped


# ------------------------------------------------------ settings check
# Folder names written by the later stages. Background subtraction is meant
# to run on the converted images, not on one of these.
LATER_STAGE_FOLDERS = ["processed_bgsub_cleared", "probabilities",
                       "particle_counts", "thresholded"]


def few(names, n=3):
	"""Up to n names joined by commas, with ', ...' when there are more."""
	names = list(names)
	text = ", ".join(names[:n])
	if len(names) > n:
		text += ", ..."
	return text


def channel_check_lines(img_path, img_name):
	"""Check-window lines about the channels of one image (cheap: header only)."""
	lines = []
	chans = describe_channels(img_path)
	if not chans:
		lines.append("Channels in %s: could not be read from the file." % img_name)
		return lines
	n = len(chans)
	lines.append("Channels in %s (%d):" % (img_name, n))
	for c, text in enumerate(chans[:8]):
		mark = ""
		if CHANNEL <= 0 or CHANNEL == c + 1:
			mark = "   <- processed"
		lines.append("   " + text + mark)
	if n > 8:
		lines.append("   ... (%d more)" % (n - 8))
	if CHANNEL <= 0 and n > 1:
		lines.append("!%s has %d channels and 'Channel to process' is 0, so "
		             "every channel is processed and kept together in one "
		             "output file. ilastik and stage 3 would then see a "
		             "multi-channel image. Enter the number of the channel "
		             "you want if only one should go on." % (img_name, n))
	elif CHANNEL > n:
		lines.append("!'Channel to process' is %d but %s has only %d "
		             "channel(s), so images like it will FAIL. Check the "
		             "channel number against the list below."
		             % (CHANNEL, img_name, n))
	elif CHANNEL >= 1 and n == 1 and ((CHANNEL_SUFFIX_TEMPLATE % CHANNEL) + "_") in (os.path.splitext(img_name)[0] + "_"):
		lines.append("   %s has a single channel and its name says %s; it is used as is"
		             % (img_name, CHANNEL_SUFFIX_TEMPLATE % CHANNEL))
	elif CHANNEL >= 1 and n == 1:
		lines.append("!%s has a single channel, so 'Channel to process' = %d "
		             "has nothing to extract, and single-channel images like "
		             "it will FAIL rather than be saved under a '%s' name "
		             "that may not match their stain. Set 'Channel to "
		             "process' to 0 for single-channel images, or to the "
		             "channel named in the file."
		             % (img_name, CHANNEL, CHANNEL_SUFFIX_TEMPLATE % CHANNEL))
	return lines


def later_stage_folder_line(folder, what):
	"""A '!' line when a folder is named like a later stage's output, else None."""
	name = os.path.basename(os.path.normpath(folder))
	if name.lower() in LATER_STAGE_FOLDERS:
		return ("!The %s is named '%s', the name of a later stage's output "
		        "folder. Background subtraction is meant to run on the "
		        "converted images (usually tifs/)." % (what, name))
	return None


def already_bgsub(names):
	"""The image names that already carry this step's suffix."""
	return [n for n in names if OUTPUT_SUFFIX.lower() in n.lower()]


def particle_roi_line(folder, roi_names):
	"""A '!' line when the ROI input looks like stage 3's particle ROIs."""
	stems = [os.path.splitext(n)[0] for n in roi_names]
	odd = [n for n, s in zip(roi_names, stems)
	       if s.lower().endswith("_particles")]
	if os.path.basename(os.path.normpath(folder)).lower() == "particle_rois" or odd:
		return ("!The ROI input looks like stage 3's particle ROIs (%s), not "
		        "the region ROI sets from step 2a (rois/). Clearing outside "
		        "them would keep only the counted particles."
		        % few(odd or roi_names))
	return None


def named_roi_line(rois, roi_name):
	"""A '!' line when named mode will not find its ROI in this set, else None."""
	if not MODE_NAMED:
		return None
	target = TISSUE.lower()
	for n in rois.keys():
		low = n.lower()
		if low == target or re.match(r"^" + re.escape(target) + r"_\d+$", low):
			return None
	return ("!'Clear outside...' is 'one named ROI' with the name '%s', but "
	        "%s has no ROI of that name (it has: %s). Files like it will "
	        "FAIL; 'union of ALL ROIs in the set' works with any ROI set."
	        % (TISSUE, roi_name, few(rois.keys(), 6)))


def would_be_output_dir(anchor_dir, requested_name, default_name, parent_override):
	"""The folder resolve_output_dir will use, without creating it."""
	name = (requested_name or "").strip() or default_name
	name = re.sub(r'[\\/:*?"<>|]', "_", name).strip() or default_name
	if parent_override is not None:
		parent = parent_override.getAbsolutePath()
	else:
		parent = os.path.dirname(os.path.normpath(anchor_dir))
	return os.path.join(parent, name)


def remove_if_new_and_empty(path, existed_before):
	"""Undo creating the output folder when the run is cancelled."""
	if existed_before:
		return
	try:
		if os.path.isdir(path) and not os.listdir(path):
			os.rmdir(path)
	except OSError:
		pass


# ================================================================= SETUP
for label, d in (("raw image", TIF_DIR), ("ROI", ROI_DIR)):
	if not os.path.isdir(d):
		IJ.error("Folder not found",
		         "The %s folder does not exist:\n%s\n\nChoose an existing "
		         "folder in the dialog." % (label, d))
		raise SystemExit

if RADIUS <= 0:
	IJ.error("Rolling ball radius",
	         "Rolling ball radius must be greater than zero (got %s)." % RADIUS)
	raise SystemExit

if MODE_NAMED and not TISSUE:
	IJ.error("ROI name missing",
	         "The ROI name is blank.\n\n"
	         "Enter the name exactly as it appears in the RoiSet, or switch "
	         "'Clear outside...' to one of the union modes.")
	raise SystemExit

if os.path.abspath(TIF_DIR) == os.path.abspath(ROI_DIR):
	IJ.error("Same folder twice",
	         "The image folder and the ROI folder are the same:\n%s\n\n"
	         "Choose separate folders (usually tifs/ and rois/)." % TIF_DIR)
	raise SystemExit

SLIDE_WARNING = slide_folder_warning([("image folder", TIF_DIR, 1),
                                      ("ROI folder", ROI_DIR, 1)])


# ------------------------------------------------------------- inventory
all_tifs = [f for f in os.listdir(TIF_DIR)
            if os.path.isfile(os.path.join(TIF_DIR, f))
            and os.path.splitext(f)[1].lower() in TIF_EXTENSIONS]
tif_files = [f for f in all_tifs if name_allowed(f)]
roi_files = [f for f in os.listdir(ROI_DIR)
             if os.path.isfile(os.path.join(ROI_DIR, f))
             and f.lower().endswith(".zip") and not f.startswith("_")]

if not tif_files:
	if all_tifs:
		IJ.error("No images left after the name filter",
		         "%d image(s) in:\n%s\n\nbut none passed the filename "
		         "filter (must contain %r, must not contain %r; the "
		         "'must contain' text comes from the %s).\n\n"
		         "Example image name: %s\n\n"
		         "Fix 'Only use images whose name contains', or leave it "
		         "blank to use every image."
		         % (len(all_tifs), TIF_DIR, REQUIRE_IN_NAME, EXCLUDE_IN_NAME,
		            REQUIRE_SOURCE, sorted(all_tifs)[0]))
	else:
		IJ.error("No images",
		         "No %s files in:\n%s\n\nChoose the folder that holds the "
		         "raw .tif images (usually tifs/)."
		         % (" / ".join(TIF_EXTENSIONS), TIF_DIR))
	raise SystemExit
if not roi_files:
	IJ.error("No ROI sets",
	         "No .zip ROI files in:\n%s\n\nChoose the folder written by step "
	         "2a (usually rois/)." % ROI_DIR)
	raise SystemExit

tif_by_key, roi_by_key = {}, {}
tif_nokey, roi_nokey = [], []
tif_dupes, roi_dupes = {}, {}

for f in sorted(tif_files):
	k = key_from(f)
	if k is None:
		tif_nokey.append(f)
	elif k in tif_by_key:
		tif_dupes.setdefault(k, [tif_by_key[k]]).append(f)
	else:
		tif_by_key[k] = f

for f in sorted(roi_files):
	k = key_from(f)
	if k is None:
		roi_nokey.append(f)
	elif k in roi_by_key:
		roi_dupes.setdefault(k, [roi_by_key[k]]).append(f)
	else:
		roi_by_key[k] = f

if tif_dupes or roi_dupes:
	lines = []
	for k, fs in sorted(tif_dupes.items()):
		lines.append("  images  '%s': %s" % (k, ", ".join(fs)))
	for k, fs in sorted(roi_dupes.items()):
		lines.append("  ROI sets '%s': %s" % (k, ", ".join(fs)))
	for ln in lines:
		IJ.log("  ! duplicate key -> " + ln.strip())
	IJ.error(
	    "Duplicate keys",
	    "More than one file shares the same RegionXXXX key, so the script "
	    "cannot tell which one you mean:\n\n%s\n\n"
	    "This usually happens when a folder holds several channels or "
	    "variants of the same section (for example the _C1 and _C2 files "
	    "written by step 1). Type the text that identifies the one you want "
	    "(for example \"_C2\") into the dialog field 'Only use images whose "
	    "name contains (blank = all; e.g. _C2)', or set REQUIRE_IN_NAME in the "
	    "configuration block, or split them into separate folders.\n\n"
	    "Current 'must contain' filter: %r (from the %s).\n\n"
	    "Stopping rather than silently processing one of them."
	    % ("\n".join(lines[:15]), REQUIRE_IN_NAME, REQUIRE_SOURCE))
	raise SystemExit

matched = sorted([k for k in tif_by_key if k in roi_by_key])
tif_only = sorted([k for k in tif_by_key if k not in roi_by_key])
roi_only = sorted([k for k in roi_by_key if k not in tif_by_key])

if not matched:
	IJ.error("No matched pairs",
	         "Found %d image(s) and %d ROI set(s), but nothing paired up.\n\n"
	         "Example image name : %s\n"
	         "Example ROI name   : %s\n\n"
	         "Pairing uses the leading token matched by KEY_PATTERN, "
	         "currently %r. Every file needs that token at the start of its "
	         "name. Adjust KEY_PATTERN in the configuration block if your "
	         "sections are named differently."
	         % (len(tif_files), len(roi_files),
	            sorted(tif_files)[0], sorted(roi_files)[0], KEY_PATTERN))
	raise SystemExit


# ------------------------------------------------- ROI picker (pick mode)
def scan_roi_names(keys):
	"""Union of ROI names across the matched ROI files, in first-seen order."""
	names = []
	seen = set()
	scanned, unreadable = 0, []
	limit = len(keys) if SCAN_MAX_FILES <= 0 else min(SCAN_MAX_FILES, len(keys))

	for k in keys[:limit]:
		p = os.path.join(ROI_DIR, roi_by_key[k])
		try:
			for n in read_roiset(p).keys():
				b = base_name(n)
				if b not in seen:
					seen.add(b)
					names.append(re.sub(r"_\d+$", "", n))
			scanned += 1
		except StepError, e:
			unreadable.append("%s (%s)" % (roi_by_key[k], str(e)))
	return names, scanned, unreadable, limit


def pick_rois(names):
	"""Swing multi-select picker. Returns (include_list, exclude_list) or None."""
	panel = JPanel()
	panel.setLayout(BoxLayout(panel, BoxLayout.Y_AXIS))
	panel.add(JLabel("Select ROIs, then choose how to use them:"))

	combo = JComboBox(["Keep ONLY the selected ROIs",
	                   "Keep everything EXCEPT the selected ROIs"])
	panel.add(combo)

	jlist = JList(names)
	jlist.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)
	scroll = JScrollPane(jlist)
	scroll.setPreferredSize(Dimension(420, 360))
	panel.add(scroll)
	panel.add(JLabel("%d ROI name(s) found. Ctrl-click / shift-click to "
	                 "multi-select." % len(names)))

	res = JOptionPane.showConfirmDialog(
	    None, panel, "Choose the ROIs to clear outside of",
	    JOptionPane.OK_CANCEL_OPTION, JOptionPane.PLAIN_MESSAGE)

	if res != JOptionPane.OK_OPTION:
		return None

	idx = jlist.getSelectedIndices()
	picked = [names[j] for j in idx]
	if not picked:
		return ([], [])
	if combo.getSelectedIndex() == 0:
		return (picked, [])
	return ([], picked)


if MODE_PICK:
	scanned_names, n_scanned, unreadable, limit = scan_roi_names(matched)

	if not scanned_names:
		IJ.error("Could not build a ROI list",
		         "Scanned %d ROI file(s) and found no readable ROI names.\n\n"
		         "%s" % (limit, "\n".join(unreadable[:5]) if unreadable
		                 else "The files may be empty."))
		raise SystemExit

	choice = pick_rois(scanned_names)
	if choice is None:
		IJ.log("ROI selection cancelled; nothing was processed.")
		raise SystemExit

	inc, exc = choice
	if not inc and not exc:
		IJ.error("Nothing selected",
		         "No ROIs were selected, so there is nothing to keep.\n\n"
		         "Re-run and select at least one, or choose 'union of ALL "
		         "ROIs in the set'.")
		raise SystemExit

	CLEAR_INCLUDE_NAMES = inc
	CLEAR_EXCLUDE_NAMES = exc


# Output folder: created only once every pre-flight check has passed.
parent_src = TIF_DIR if OUTPUT_PARENT_SOURCE == "tif" else ROI_DIR
OUT_EXISTED = os.path.isdir(would_be_output_dir(
    parent_src, outFolderName, "processed_bgsub_cleared", outParentDir))
OUT_DIR = resolve_output_dir(parent_src, outFolderName,
                             "processed_bgsub_cleared", outParentDir)
if OUT_DIR is None:
	raise SystemExit


# ------------------------------------------------------ settings check
def output_name_for(tif_name):
	"""Output file name for an input image (same rule as the run loop)."""
	chan = "" if CHANNEL <= 0 else (CHANNEL_SUFFIX_TEMPLATE % CHANNEL)
	return os.path.splitext(tif_name)[0] + OUTPUT_SUFFIX + chan + ".tif"


check = []
check.append("Images: %s" % TIF_DIR)
if REQUIRE_IN_NAME:
	check.append("   name filter: must contain %r (from the %s)"
	             % (REQUIRE_IN_NAME, REQUIRE_SOURCE))
else:
	check.append("   name filter: none, every image in the folder is used")
if EXCLUDE_IN_NAME:
	check.append("   name filter: must NOT contain %r (EXCLUDE_IN_NAME)"
	             % EXCLUDE_IN_NAME)
if len(tif_files) != len(all_tifs):
	check.append("   %d of %d image(s) left out by the name filter"
	             % (len(all_tifs) - len(tif_files), len(all_tifs)))
check.append("ROI sets: %s" % ROI_DIR)
check.append("%d image/ROI pair(s) will be processed." % len(matched))
if tif_only:
	check.append("   %d image(s) have no ROI zip and are skipped: %s"
	             % (len(tif_only), few([tif_by_key[k] for k in tif_only])))
if roi_only:
	check.append("   %d ROI zip(s) have no image: %s"
	             % (len(roi_only), few([roi_by_key[k] for k in roi_only])))
if tif_nokey or roi_nokey:
	check.append("   %d file(s) have no RegionXXXX key and are ignored: %s"
	             % (len(tif_nokey) + len(roi_nokey), few(tif_nokey + roi_nokey)))
first_tif = tif_by_key[matched[0]]
first_roi = roi_by_key[matched[0]]
check.append("First pair: %s -> %s -> %s"
             % (first_tif, first_roi, output_name_for(first_tif)))
check.append("Output folder: %s" % OUT_DIR)
n_exist = len([k for k in matched if os.path.exists(
    os.path.join(OUT_DIR, output_name_for(tif_by_key[k])))])
if n_exist:
	check.append("   %d of %d output file(s) already exist and will be %s"
	             % (n_exist, len(matched),
	                "replaced (Overwrite is on)" if overwrite
	                else "skipped (Overwrite is off)"))
check.append("Rolling ball radius: %s px" % RADIUS)
check.append("Clear outside: %s" % clearMode)
if MODE_NAMED:
	check.append("   ROI name: '%s'" % TISSUE)
if CLEAR_INCLUDE_NAMES:
	check.append("   only these ROIs: %s" % ", ".join(CLEAR_INCLUDE_NAMES))
if CLEAR_EXCLUDE_NAMES:
	check.append("   leaving out: %s" % ", ".join(CLEAR_EXCLUDE_NAMES))
if CHANNEL <= 0:
	check.append("Channel to process: 0 = all channels, kept together in one file")
else:
	check.append("Channel to process: %d (only this channel is kept)" % CHANNEL)
check.extend(channel_check_lines(os.path.join(TIF_DIR, first_tif), first_tif))

wl = later_stage_folder_line(TIF_DIR, "image folder")
if wl:
	check.append(wl)
bg_named = already_bgsub([tif_by_key[k] for k in matched])
if bg_named:
	check.append("!%d of %d image(s) to process already have '%s' in their "
	             "name (%s). They look like this step's output; running it "
	             "again subtracts the background twice."
	             % (len(bg_named), len(matched), OUTPUT_SUFFIX, few(bg_named)))
wl = particle_roi_line(ROI_DIR, [roi_by_key[k] for k in matched])
if wl:
	check.append(wl)
if os.path.normcase(os.path.abspath(OUT_DIR)) == os.path.normcase(os.path.abspath(TIF_DIR)):
	check.append("!The output folder is the image folder itself. The outputs "
	             "will sit among the input images, and a later run of this "
	             "step would pick them up as inputs.")
if MODE_NAMED:
	try:
		wl = named_roi_line(read_roiset(os.path.join(ROI_DIR, first_roi)), first_roi)
	except StepError, e:
		wl = ("!The first ROI zip (%s) could not be read: %s" % (first_roi, str(e)))
	if wl:
		check.append(wl)
if SLIDE_WARNING:
	check.append("!" + SLIDE_WARNING[0][:1].upper() + SLIDE_WARNING[0][1:]
	             + " " + " ".join(
	    [ln.strip() for ln in SLIDE_WARNING[1:]]))

if not confirm_settings(SCRIPT_NAME, experiment_lines(globals().get("_SLIDE") or TIF_DIR) + check, CONFIRM_BEFORE_RUN):
	remove_if_new_and_empty(OUT_DIR, OUT_EXISTED)
	IJ.log("%s: cancelled at the settings check; nothing was processed."
	       % SCRIPT_NAME)
	raise SystemExit


# ------------------------------------------------------------- run header
IJ.log("=" * 64)
IJ.log("%s  (version %s)" % (SCRIPT_NAME, SCRIPT_VERSION))
IJ.log("Background subtraction + clear outside")
IJ.log("  images : %s  (%d file(s))" % (TIF_DIR, len(tif_files)))
IJ.log("  ROIs   : %s  (%d file(s))" % (ROI_DIR, len(roi_files)))
IJ.log("  output : %s" % OUT_DIR)
IJ.log("  rolling ball = %s px" % RADIUS)
IJ.log("  channel = %s" % ("all" if CHANNEL <= 0 else str(CHANNEL)))
IJ.log("  clear outside: %s" % clearMode)
if MODE_NAMED:
	IJ.log("     ROI name = '%s'" % TISSUE)
if CLEAR_INCLUDE_NAMES:
	IJ.log("     including ONLY: %s" % ", ".join(CLEAR_INCLUDE_NAMES))
	IJ.log("     reproduce with: CLEAR_INCLUDE_NAMES = %r" % (CLEAR_INCLUDE_NAMES,))
if CLEAR_EXCLUDE_NAMES:
	IJ.log("     excluding: %s" % ", ".join(CLEAR_EXCLUDE_NAMES))
	IJ.log("     reproduce with: CLEAR_EXCLUDE_NAMES = %r" % (CLEAR_EXCLUDE_NAMES,))
IJ.log("  key pattern %r   ->   %d matched pair(s)" % (KEY_PATTERN, len(matched)))
if REQUIRE_IN_NAME:
	IJ.log("  filename filter: images must contain %r  (from the %s)"
	       % (REQUIRE_IN_NAME, REQUIRE_SOURCE))
else:
	IJ.log("  filename filter: none (dialog field blank, REQUIRE_IN_NAME blank)")
if EXCLUDE_IN_NAME:
	IJ.log("  filename filter: images must NOT contain %r  (EXCLUDE_IN_NAME)"
	       % EXCLUDE_IN_NAME)
if len(tif_files) != len(all_tifs):
	IJ.log("  %d of %d image(s) left out by the filename filter"
	       % (len(all_tifs) - len(tif_files), len(all_tifs)))
IJ.log("=" * 64)

if SLIDE_WARNING:
	log_slide_warning(SLIDE_WARNING)
for f in tif_nokey:
	IJ.log("  ! no key could be extracted from image '%s' - ignored" % f)
for f in roi_nokey:
	IJ.log("  ! no key could be extracted from ROI set '%s' - ignored" % f)
if tif_only:
	IJ.log("  ! %d image(s) with no matching ROI set: %s"
	       % (len(tif_only), ", ".join([tif_by_key[k] for k in tif_only[:15]])))
if roi_only:
	IJ.log("  ! %d ROI set(s) with no matching image: %s"
	       % (len(roi_only), ", ".join([roi_by_key[k] for k in roi_only[:15]])))


# ================================================================= RUN
log_rows = []
done, failed, warned, skipped = [], [], [], []

chan_suffix = "" if CHANNEL <= 0 else (CHANNEL_SUFFIX_TEMPLATE % CHANNEL)
n_total = len(matched)

for i, key in enumerate(matched):
	tif_name = tif_by_key[key]
	roi_name = roi_by_key[key]
	tif_path = os.path.join(TIF_DIR, tif_name)
	roi_path = os.path.join(ROI_DIR, roi_name)

	# FILENAME STANDARD: append only, never rebuild from the key.
	base = os.path.splitext(tif_name)[0]
	out_name = base + OUTPUT_SUFFIX + chan_suffix + ".tif"
	out_path = os.path.join(OUT_DIR, out_name)

	IJ.showProgress(i, n_total)
	tag = "[%d/%d] %s" % (i + 1, n_total, tif_name)

	if os.path.exists(out_path) and not overwrite:
		IJ.log("%s  SKIPPED (output exists; tick Overwrite to replace)" % tag)
		skipped.append(tif_name)
		log_rows.append([key, tif_name, roi_name, "", "", "", "", "", "no",
		                 "skipped - output already existed"])
		continue

	imp = None
	infos = []       # information only
	warns = []       # something the user should look at
	try:
		IJ.showStatus(tag + " - reading ROIs")
		rois = read_roiset(roi_path)
		clear_roi, cnote, cwarn = build_clear_roi(rois, roi_name)
		if cnote:
			(warns if cwarn else infos).append(cnote)

		IJ.showStatus(tag + " - opening image")
		imp = open_image(tif_path)
		imp, chnote = extract_channel(imp)
		if chnote:
			infos.append(chnote)
		tnote = image_type_warning(imp)
		if tnote:
			warns.append(tnote)

		dims = "%dx%d" % (imp.getWidth(), imp.getHeight())
		nslices = imp.getStackSize()

		IJ.showStatus(tag + " - subtracting background")
		opts = subtract_background(imp)

		IJ.showStatus(tag + " - clearing outside the ROI")
		clipped = clear_outside(imp, clear_roi)
		if clipped:
			warns.append(clipped)

		IJ.showStatus(tag + " - saving")
		if not IJ.saveAsTiff(imp, out_path):
			raise StepError("the processed image could not be saved to %s"
			                % out_path)

		done.append(out_name)
		if warns:
			warned.append(tif_name)
		IJ.log("%s -> %s   [%s, %d slice(s)]%s"
		       % (tag, out_name, dims, nslices,
		          "   WITH WARNINGS" if warns else ""))
		for nte in infos:
			IJ.log("      - %s" % nte)
		for nte in warns:
			IJ.log("      ! %s" % nte)

		notes = infos + warns
		log_rows.append([key, tif_name, roi_name, dims, str(nslices),
		                 str(CHANNEL), str(RADIUS), opts, "yes",
		                 "ok" if not notes else "ok: " + " | ".join(notes)])

	except StepError, e:
		failed.append(tif_name)
		IJ.log("%s  FAILED: %s" % (tag, str(e)))
		log_rows.append([key, tif_name, roi_name, "", "", str(CHANNEL),
		                 str(RADIUS), "", "no",
		                 "FAILED: " + str(e).replace("\n", " ")])

	except (Exception, JavaException), e:
		failed.append(tif_name)
		msg = "%s: %s" % (type(e).__name__, str(e))
		IJ.log("%s  UNEXPECTED ERROR: %s" % (tag, msg))
		log_rows.append([key, tif_name, roi_name, "", "", str(CHANNEL),
		                 str(RADIUS), "", "no",
		                 "UNEXPECTED ERROR: " + msg.replace("\n", " ")])

	finally:
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
	log_path = os.path.join(OUT_DIR, "_processing_log.csv")
	if os.path.exists(log_path) and not overwrite:
		IJ.log("Debug log NOT saved - the file already exists (tick "
		       "'Overwrite existing output files' to replace it): %s" % log_path)
		log_path = None
	else:
		try:
			fh = open(log_path, "w")
			try:
				fh.write("key,image_file,roi_file,dimensions,slices,channel,"
				         "rolling_ball,bg_options,saved,status\n")
				for r in log_rows:
					fh.write(",".join(['"%s"' % str(c).replace('"', "'") for c in r]) + "\n")
				for k in tif_only:
					fh.write('"%s","%s","","","","","","","no","no matching ROI set"\n'
					         % (k, tif_by_key[k]))
				for k in roi_only:
					fh.write('"%s","","%s","","","","","","no","no matching image"\n'
					         % (k, roi_by_key[k]))
			finally:
				fh.close()
			IJ.log("Log written: %s" % log_path)
		except IOError, e:
			log_path = None
			IJ.log("WARNING: could not write the log CSV: %s" % str(e))


# ------------------------------------------------------ parameter record
record_path = None
if WRITE_PARAMETER_RECORD:
	items = [
	    ("#Dialog", "")] + layout_record() + [
	    ("Folder of raw .tif images (tifs/)", TIF_DIR),
	    ("Folder of ROI .zip files (rois/)", ROI_DIR),
	    ("Only use images whose name contains (blank = all; e.g. _C2)",
	     NAME_FILTER or "(blank)"),
	    ("Rolling ball radius (pixels)", RADIUS),
	    ("Clear outside...", clearMode),
	    ("...name of that ROI (named mode only)", TISSUE),
	    ("Channel to process (0 = all channels)", CHANNEL),
	    ("Output location (blank = one level above the input)",
	     outParentDir.getAbsolutePath()
	     if outParentDir is not None else "(blank)"),
	    ("Name for the new output folder", outFolderName),
	    ("Overwrite existing output files", overwrite),
	    ("Write a debug log CSV to the output folder", writeLog),
	    ("#Configuration", ""),
	    ("CLEAR_INCLUDE_NAMES (as used)", CLEAR_INCLUDE_NAMES),
	    ("CLEAR_EXCLUDE_NAMES (as used)", CLEAR_EXCLUDE_NAMES),
	    ("MERGE_TISSUE_PIECES", MERGE_TISSUE_PIECES),
	    ("SCAN_MAX_FILES", SCAN_MAX_FILES),
	    ("BG_LIGHT_BACKGROUND", BG_LIGHT_BACKGROUND),
	    ("BG_SLIDING_PARABOLOID", BG_SLIDING_PARABOLOID),
	    ("BG_DISABLE_SMOOTHING", BG_DISABLE_SMOOTHING),
	    ("PROCESS_ALL_SLICES", PROCESS_ALL_SLICES),
	    ("CLEAR_VALUE", CLEAR_VALUE),
	    ("OUTPUT_PARENT_SOURCE", OUTPUT_PARENT_SOURCE),
	    ("OUTPUT_SUFFIX", OUTPUT_SUFFIX),
	    ("CHANNEL_SUFFIX_TEMPLATE", CHANNEL_SUFFIX_TEMPLATE),
	    ("TIF_EXTENSIONS", TIF_EXTENSIONS),
	    ("KEY_PATTERN", KEY_PATTERN),
	    ("CASE_INSENSITIVE_KEYS", CASE_INSENSITIVE_KEYS),
	    ("REQUIRE_IN_NAME (config block)", REQUIRE_IN_NAME_CONFIG),
	    ("REQUIRE_IN_NAME (as used)", REQUIRE_IN_NAME),
	    ("EXCLUDE_IN_NAME", EXCLUDE_IN_NAME),
	    ("CONFIRM_BEFORE_RUN", CONFIRM_BEFORE_RUN),
	    ("#Inputs", ""),
	    ("image folder", TIF_DIR),
	    ("ROI folder", ROI_DIR),
	    ("output folder", OUT_DIR),
	]
	for k in matched:
		items.append(("pair " + k, "%s + %s" % (tif_by_key[k], roi_by_key[k])))
	record_path = write_run_record(OUT_DIR, SCRIPT_NAME, SCRIPT_VERSION, items)
	if record_path:
		IJ.log("Parameter record: %s" % record_path)


# ---------------------------------------------------- completion notice
IJ.log("-" * 64)
summary = ["Processed : %d" % len(done)]
if warned:
	summary.append("Warnings  : %d  (see Log)" % len(warned))
if failed:
	summary.append("Failed    : %d  (see Log)" % len(failed))
if skipped:
	summary.append("Skipped   : %d  (output existed)" % len(skipped))
if tif_only or roi_only:
	summary.append("Unmatched : %d image(s), %d ROI set(s)"
	               % (len(tif_only), len(roi_only)))
for line in summary:
	IJ.log(line)
IJ.log("-" * 64)

IJ.beep()

if failed:
	title = "Batch complete - with failures"
elif warned or tif_only or roi_only or SLIDE_WARNING:
	title = "Batch complete - with problems"
else:
	title = "Batch complete"
body = ["Finished %d matched pair(s)." % len(matched), ""]
body.extend(summary)
body.append("")
body.append("Output folder:")
body.append("   " + OUT_DIR)
if CHANNEL > 0:
	body.append("")
	body.append("Single channel %d written, ready for ilastik." % CHANNEL)
if SLIDE_WARNING:
	body.append("")
	body.append("WARNING: " + SLIDE_WARNING[0])
	body.extend(SLIDE_WARNING[1:])
if failed or warned or tif_only or roi_only or SLIDE_WARNING:
	body.append("")
	body.append("Check the Log window for details.")
if record_path:
	body.append("")
	body.append("Parameter record: " + record_path)
if log_path:
	body.append("")
	body.append("Log: " + log_path)
IJ.log("Finished: " + title)
IJ.showMessage(title, "\n".join(body))
