# 4_Build_Pipeline_Composite_(single).py
#
# Stacks ONE section's pipeline stages into a multi-channel QC image, with
# anatomical ROIs and counted particles laid over it.
#
# Menu: Plugins > Kapur Lab Cell Counting > Single image >
#       4 Build Pipeline Composite (single)
#
# Fiji / ImageJ Jython script. Single-image version of
# Batch/4_Build_Pipeline_Composite.py: same processing, same settings and
# the same output name, but you pick files instead of folders.
#
# Assembles every stage of the pipeline for one section into a single
# multi-channel image, so you can scroll the channel slider and watch the
# same field of view move through the workflow:
#
#   C1  Raw
#   C2  Background subtracted and cleared
#   C3  ilastik probabilities
#   C4  Thresholded mask
#
# Counted particles and anatomical regions can be laid over the top as an
# overlay that shows on every channel, which is the main thing this is for:
# seeing the counted cells on the ORIGINAL image.
#
# Every file is OPTIONAL. Give it two images and you get a two-channel
# image; give it four and you get four. Stages you leave blank are simply
# absent, and the channel numbering closes up around them.
#
# The composite is named after the RegionXXXX token of the first image
# given (in the order Raw, BgSub, Probabilities, Thresholded). If the files
# you picked carry different RegionXXXX tokens it is still built, with a
# warning in the Log and in the completion message.
#
# Reads (every file is optional; at least one image is needed):
#   an image from tifs/                          raw (stage 1)
#   an image from processed_bgsub_cleared/       bgsub + cleared (2b)
#   an image from probabilities/                 ilastik probabilities
#   <stem>_thresh.tif from particle_counts/thresholded/          mask (3)
#   <stem>_particles.zip or <stem>_particles_combined.roi from
#     particle_counts/particle_rois/             counted particles (3)
#   a RoiSet .zip from rois/                     anatomical ROIs (2a)
# Writes (into a new folder, default pipeline_composites/, one level above
# the folder of the first image given - where the batch version puts it):
#   RegionXXXX_composite.tif         the multi-channel image
#   _run_4_Build_Pipeline_Composite_single_<date-time>.txt  parameter record
#   _composite_log_RegionXXXX.csv    only if the debug log CSV is ticked
#
# Read-only: nothing here modifies the inputs.
#
# Before it runs, the script shows a Check settings window that lists the
# files given, the output folder and file name, the channel taken from
# multi-channel images, and the display and save choices, plus warnings
# about likely mistakes (for example a probability map older than the
# image it should come from). Press Run to go ahead or Cancel to stop
# with nothing built. CONFIRM_BEFORE_RUN in the configuration block turns
# the window off.
#
# Usage: Plugins > Kapur Lab Cell Counting > Single image > 4 Build
#        Pipeline Composite (single), or open this file in the Script Editor
#        (File > New > Script..., or Plugins > Scripting > Script Editor)
#        with Language = Python (Jython) and press Run.

#@ File    (label="Slide folder (the scripts find its subfolders)", style="directory") slideDir
#@ String  (label="Region (its MBF folder; blank = choose from a list)", value="", required=false) regionName
#@ String  (label="Section (e.g. Region0011; blank = choose from a list)", value="", required=false) sectionKey
#@ Integer (label="Channel to take from multi-channel RAW", value=1, min=0) rawChannel
#@ Integer (label="Channel to take from multi-channel PROBABILITIES", value=1, min=0) probChannel
#@ String  (label="Display mode", choices={"Grayscale - scroll one stage at a time", "Color - one LUT per stage", "Composite - all stages merged"}, style="listBox") displayMode
#@ String  (label="Load ROIs as", choices={"Overlay", "ROI Manager", "Both"}, style="radioButtonHorizontal") roiLoadMode
#@ File    (label="Output location (blank = beside the folder that holds the input file)", style="directory", required=false) outParentDir
#@ String  (label="Name for the new output folder", value="pipeline_composites") outFolderName
#@ Boolean (label="Leave the result open on screen", value=true) showResult
#@ Boolean (label="Save the composite to disk", value=true) saveComposites
#@ Boolean (label="Overwrite an existing composite", value=false) overwrite
#@ Boolean (label="Write a debug log CSV", value=false) writeLog


# =========================================================================
# ===  USER CONFIGURATION  ================================================
# =========================================================================
# Everything you may want to change is in this block. Nothing below the
# END OF USER CONFIGURATION banner needs editing for routine use.
# The settings match the batch version's, so a single-image composite
# looks exactly like the batch one.

# ---- STAGES -------------------------------------------------------------
#
# Channel order is the order of this list. Rename the labels freely - they
# become the channel labels shown in the title bar as you scroll. To add a
# stage, add an entry here and a matching file parameter above.
#
#   (label, file variable name, which channel to take from that file)
#
# The background-subtracted image takes the same channel as the raw image
# ("Channel to take from multi-channel RAW"): 2b keeps every channel by
# default, so a multi-channel ..._bgsub.tif holds the raw channels in the
# same order. A single-channel image is always used as it is.

STAGE_ORDER = [
    ("Raw",            "rawFile",    "rawChannel"),
    ("BgSub_Cleared",  "bgsubFile",  "rawChannel"),
    ("Probabilities",  "probFile",   "probChannel"),
    ("Thresholded",    "threshFile", None),
]


# ---- FILENAME STANDARD --------------------------------------------------
#
# The key is the leading RegionXXXX token; everything after is ignored. It
# names the output and is used to check that the files you picked belong
# to the same section.
#
#   tifs/Region0011_ChannelFITCTRITC_Seq0011_MAX_C2.tif
#   processed_bgsub_cleared/Region0011_ChannelFITCTRITC_Seq0011_MAX_C2_bgsub.tif
#   probabilities/Region0011_ChannelFITCTRITC_Seq0011_MAX_C2_bgsub.tif (ilastik)
#   particle_counts/thresholded/..._bgsub_thresh.tif, particle_rois/..._particles.zip
#   rois/Region0011.zip  ->  pipeline_composites/Region0011_composite.tif
KEY_PATTERN = r"^(Region\d+)"
CASE_INSENSITIVE_KEYS = True

# Files are paired by their RegionXXXX token only. True warns - in the Log
# and in the completion message - when the chosen files do not come from
# the same slide folder (the folder that holds tifs/, rois/,
# probabilities/, ...), e.g. an image from one slide and ROIs from another.
# It never stops the run.
# particle_counts/thresholded/ and particle_counts/particle_rois/ count
# as part of the slide folder that holds particle_counts/.
WARN_ON_DIFFERENT_SLIDE_FOLDERS = True

# Filename filters used by the batch version when it scans folders. Files
# you pick here by hand are NOT filtered; these stay only because the
# shared key helper expects them.
REQUIRE_IN_NAME = ""
EXCLUDE_IN_NAME = ""

TIF_EXTENSIONS = [".tif", ".tiff"]


# ---- BIT DEPTH ----------------------------------------------------------
#
# A stack needs one type throughout, so stages are promoted to a common
# depth. Each channel then gets its own display range, so a 0-255 mask and
# a 16-bit raw image both still look right.
#
#   "auto"  16-bit if any stage is 16-bit or deeper, otherwise 8-bit
#   "8"     everything to 8-bit (smaller; raw dynamic range is compressed)
#   "16"    everything to 16-bit
TARGET_DEPTH = "auto"


# ---- SIZE MISMATCH ------------------------------------------------------
#
# Stages should share dimensions. If one does not:
#   "skip"   leave that stage out of the composite and say so
#   "scale"  resize it to match the first stage (QC only - do not measure
#            anything off a scaled channel)
#   "fail"   treat the composite as failed
ON_SIZE_MISMATCH = "skip"


# ---- OVERLAYS -----------------------------------------------------------
#
# Particle ROIs come from the counting script's particle_rois folder, which
# holds an individual RoiSet (<stem>_particles.zip, keeps each particle's
# region name) and a combined outline (<stem>_particles_combined.roi).
# Pick whichever you want to see; the batch setting
# PREFER_INDIVIDUAL_PARTICLES has no job here.
PARTICLE_OUTLINE_COLOR = (255, 255, 0)      # yellow
ANATOMICAL_OUTLINE_COLOR = (0, 255, 255)    # cyan
OVERLAY_LINE_WIDTH = 1

# True: overlays are attached with position 0, meaning "show on every
# channel". False: they are pinned to channel 1 only (they show while the
# slider is on channel 1). Applies to ROI Manager entries as well.
OVERLAY_ON_ALL_CHANNELS = True

# Each overlay belongs to one stage's pixels: the anatomical ROIs (2a) to
# the raw image (or, without it, the background-subtracted one), the
# particle ROIs (stage 3) to the probability map (or, without it, the
# thresholded mask). The first stage of each list below that is given is
# the overlay's stage. When that stage was left out or scaled for a size
# mismatch (ON_SIZE_MISMATCH), the overlay would not line up, so it is
# left out and the Log says so. ROIs that reach past the edge of the
# composite are reported too.
OVERLAY_STAGES = {
    "anatomical": ["rawFile", "bgsubFile"],
    "particle":   ["probFile", "threshFile"],
}

# ROI Manager loading (dialog: "ROI Manager" or "Both").
#
# The ROI Manager is a single global list. ROIs are prefixed with the
# section key (Region0042: Caudoputamen-L_0001) so they stay
# distinguishable from anything already there.
RESET_ROI_MANAGER = True             # clear it first; False adds to it
ROI_MANAGER_SHOW_ALL = True          # outline every entry on the image
ROI_MANAGER_SHOW_LABELS = False      # names on the image; cluttered with
									 # hundreds of particles

# Whatever the load mode, the saved .tif carries the ROIs as an overlay, so
# the file on disk is self-contained. Set False to save without them in
# "ROI Manager" mode.
SAVE_OVERLAY_IN_FILE = True


# ---- OUTPUT -------------------------------------------------------------
# The composite keeps the whole name of the first stage file given (Raw if
# given, then BgSub_Cleared, ...) and adds this suffix:
#   Region0011_ChannelFITCTRITC_Seq0011_MAX_C2_composite.tif
OUTPUT_SUFFIX = "_composite"

# With "Output location" blank, the output folder goes one level above the
# folder of the first file given (in the order Raw, BgSub_Cleared,
# Probabilities, Thresholded, particle ROIs, anatomical ROIs), i.e. into the
# slide folder. Folders with these names (stage 3's subfolders) are stepped
# out of first, so a file from particle_counts/thresholded/ still gives
# <slide>/pipeline_composites/.
NESTED_INPUT_FOLDERS = ["thresholded", "watershed", "QC", "particle_rois"]

# Save a plain-text record of every setting used (_run_...txt) in the
# output folder, so the composite can be traced back to its parameters.
WRITE_PARAMETER_RECORD = True


# ---- SAFETY CHECKS ------------------------------------------------------
#
# True (default): before anything is built, show a "Check settings"
# window that lists what is about to happen (which files, the output
# folder and file name) and any warnings, with Run and Cancel. False:
# skip the window and start straight away, e.g. for unattended runs. The
# warnings are written to the Log either way.
CONFIRM_BEFORE_RUN = True

# =========================================================================
# ===  END OF USER CONFIGURATION  =========================================
# =========================================================================

SCRIPT_NAME = "4_Build_Pipeline_Composite_(single)"
SCRIPT_VERSION = "2.0"


import os
import re
from collections import OrderedDict

from ij import IJ, ImagePlus, ImageStack, CompositeImage
from java.lang import Exception as JavaException
from ij.gui import Overlay
from ij.plugin.frame import RoiManager
from ij.measure import Measurements, Calibration
from ij.plugin import Duplicator, ChannelSplitter
from ij.process import ImageProcessor
from java.awt import Color

try:
	from loci.plugins import BF
	HAVE_BIOFORMATS = True
except ImportError:
	HAVE_BIOFORMATS = False


LOAD_OVERLAY = roiLoadMode in ("Overlay", "Both")
LOAD_MANAGER = roiLoadMode in ("ROI Manager", "Both")


# ------------------------------------------------ slide-folder check
# A folder whose name holds the word MBF ("hippocampus MBF") is a region
# folder made by Set Up Slide Folders inside a slide folder.
MBF_FOLDER_RE = re.compile(r"(^|[^A-Za-z0-9])MBF([^A-Za-z0-9]|$)", re.IGNORECASE)


def mbf_output_parent(anchor):
	"""Where a blank 'Output location' sends the output, as a File, or None
	for the usual place (one level above anchor).

	In the Set Up Slide Folders layout the region's work lives in a
	"<region> MBF" folder inside the slide folder. When the usual place is a
	slide folder that holds exactly one such folder, the output goes into
	it. With several MBF folders (several regions) it stays in the slide
	folder; fill in 'Output location' to choose.
	"""
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
	# A slide still in the protocol layout (region subfolders directly in
	# it) keeps its output there too.
	if [d for d in names if d.lower() in ("xml", "rois", "probabilities",
	                                      "processed_bgsub_cleared",
	                                      "particle_counts")]:
		return None
	mbfs = layout_regions(parent)
	if len(mbfs) == 1:
		return File(os.path.join(parent, mbfs[0]))
	return None


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


# ------------------------------------------------------- dialog files
def given_path(f):
	"""Absolute path of an optional #@ File parameter, or None if blank."""
	if f is None:
		return None
	try:
		p = f.getPath()
	except (Exception, JavaException):
		return None
	if not p or not p.strip():
		return None
	return f.getAbsolutePath()


def shown(f):
	"""A dialog File value as text for the Log and the parameter record."""
	return given_path(f) or "(blank)"


def key_as_written(filename):
	"""The Region token exactly as it appears in the file name."""
	m = re.search(KEY_PATTERN, os.path.splitext(os.path.basename(filename))[0])
	return m.group(1) if m else None


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
	_KEYS = layout_keys(layout_find(_SLIDE, _REGION, "rois"), ('.zip',))
	_SEC = layout_pick_section(_KEYS, sectionKey)
	if _SEC is None:
		raise SystemExit
	_K = key_from(_SEC)
	_HINTS = layout_files_for(layout_find(_SLIDE, _REGION, "processed_bgsub_cleared"), _K, (".tif", ".tiff"))
	_c_rawFile = layout_files_for(layout_find(_SLIDE, _REGION, "tifs"), _K, ('.tif', '.tiff'))
	_c_bgsubFile = layout_files_for(layout_find(_SLIDE, _REGION, "processed_bgsub_cleared"), _K, ('.tif', '.tiff'))
	_c_probFile = layout_files_for(layout_find(_SLIDE, _REGION, "probabilities"), _K, ('.tif', '.tiff'))
	_c_threshFile = layout_files_for(layout_find(_SLIDE, _REGION, "particle_counts/thresholded"), _K, ('.tif', '.tiff'))
	_c_particleFile = layout_files_for(layout_find(_SLIDE, _REGION, "particle_counts/particle_rois"), _K, ('.zip', '.roi'))
	_c_anatFile = layout_files_for(layout_find(_SLIDE, _REGION, "rois"), _K, ('.zip',))
	_got = layout_confirm(SCRIPT_NAME + " - " + _SEC, _SLIDE, _REGION, [
	    ('Raw .tif image (from tifs/)', "choice", layout_default(_c_rawFile, _HINTS), _c_rawFile, False),
	    ('Background-subtracted image (from processed_bgsub_cleared/)', "choice", layout_default(_c_bgsubFile, _HINTS), _c_bgsubFile, False),
	    ('ilastik probability image (from probabilities/)', "choice", layout_default(_c_probFile, _HINTS), _c_probFile, False),
	    ('Thresholded mask (from particle_counts/thresholded/)', "choice", layout_default(_c_threshFile, _HINTS), _c_threshFile, False),
	    ('Particle ROIs to overlay, .zip or .roi (from particle_counts/particle_rois/)', "choice", (len([c for c in _c_particleFile if c.lower().endswith("_particles.zip")]) == 1 and [c for c in _c_particleFile if c.lower().endswith("_particles.zip")][0]) or layout_default(_c_particleFile, _HINTS), _c_particleFile, False),
	    ('Anatomical ROIs to overlay, .zip (from rois/)', "choice", layout_default(_c_anatFile, _HINTS), _c_anatFile, False),
	])
	if _got is None:
		raise SystemExit
	rawFile = _F(_got[0]) if _got[0] else None
	bgsubFile = _F(_got[1]) if _got[1] else None
	probFile = _F(_got[2]) if _got[2] else None
	threshFile = _F(_got[3]) if _got[3] else None
	particleFile = _F(_got[4]) if _got[4] else None
	anatFile = _F(_got[5]) if _got[5] else None


# The stage list in the configuration block names its dialog parameters;
# they are looked up by name, so a new stage only needs a STAGE_ORDER entry
# and a matching #@ line.
unknown_params = []
for _label, _filevar, _chvar in STAGE_ORDER:
	for _v in (_filevar, _chvar):
		if _v and _v not in globals():
			unknown_params.append(_v)

STAGES = []
bad_files = []
for label, filevar, chvar in STAGE_ORDER:
	p = given_path(globals().get(filevar))
	if p is None:
		continue
	if not os.path.isfile(p):
		bad_files.append("%s: not an existing file:  %s" % (label, p))
		continue
	if os.path.splitext(p)[1].lower() not in TIF_EXTENSIONS:
		bad_files.append("%s: not a %s image:  %s"
		                 % (label, " / ".join(TIF_EXTENSIONS), p))
		continue
	ch = globals().get(chvar) if chvar else None
	STAGES.append({"label": label, "path": p, "filevar": filevar,
	               "dir": os.path.dirname(p), "file": os.path.basename(p),
	               "channel": int(ch) if ch else 0})


def overlay_file(f, label):
	"""Checked path of an optional overlay .zip/.roi parameter, or None."""
	p = given_path(f)
	if p is None:
		return None
	if not os.path.isfile(p):
		bad_files.append("%s: not an existing file:  %s" % (label, p))
		return None
	if os.path.splitext(p)[1].lower() not in (".zip", ".roi"):
		bad_files.append("%s: not an ROI file (.zip or .roi):  %s"
		                 % (label, p))
		return None
	return p

PARTICLE_FILE = overlay_file(particleFile, "Particle ROIs")
ANAT_FILE = overlay_file(anatFile, "Anatomical ROIs")


# ================================================== pre-flight validation
if not HAVE_BIOFORMATS:
	IJ.error("Bio-Formats not available",
	         "This script opens images with Bio-Formats, but the loci.plugins "
	         "classes could not be found.\n\n"
	         "Install it via Help > Update... > Manage update sites and tick "
	         "'Bio-Formats', then restart Fiji.")
	raise SystemExit

if unknown_params:
	IJ.error("STAGE_ORDER problem",
	         "STAGE_ORDER in the configuration block names these dialog "
	         "parameters, but the script has no #@ line for them:\n\n%s\n\n"
	         "Check the spelling in STAGE_ORDER, or add the matching #@ "
	         "line at the top of the script." % "\n".join(unknown_params))
	raise SystemExit

if bad_files:
	IJ.error("File problem",
	         "These fields were filled in, but the file cannot be used:\n\n"
	         "%s\n\nPick the file again, or leave the field blank to leave "
	         "that stage out." % "\n".join(bad_files))
	raise SystemExit

if not STAGES:
	IJ.error("No images given",
	         "At least one of the four stage images has to be filled in.\n\n"
	         "Raw, Background subtracted, Probabilities, Thresholded - any "
	         "combination is fine, but there has to be at least one.")
	raise SystemExit

if len(STAGES) == 1 and not (PARTICLE_FILE or ANAT_FILE):
	IJ.error("Only one stage given",
	         "Only the '%s' image was filled in, and no overlay files "
	         "either, so the result would be a copy of an image you already "
	         "have.\n\nAdd a second stage image, or an ROI file to overlay."
	         % STAGES[0]["label"])
	raise SystemExit

if ON_SIZE_MISMATCH not in ("skip", "scale", "fail"):
	IJ.error("Configuration problem",
	         "ON_SIZE_MISMATCH is '%s'; it must be 'skip', 'scale' or "
	         "'fail'.\n\nFix it in the configuration block at the top of "
	         "the script." % ON_SIZE_MISMATCH)
	raise SystemExit

if TARGET_DEPTH not in ("auto", "8", "16"):
	IJ.error("Configuration problem",
	         "TARGET_DEPTH is '%s'; it must be \"auto\", \"8\" or \"16\" "
	         "(in quotes).\n\nFix it in the configuration block at the top "
	         "of the script." % TARGET_DEPTH)
	raise SystemExit

if not showResult and not saveComposites:
	IJ.error("Nothing would be produced",
	         "Both 'Leave the result open on screen' and 'Save the "
	         "composite to disk' are off, so the composite would be built "
	         "and then thrown away.\n\nTick at least one of them.")
	raise SystemExit


# ------------------------------------------------------------ image prep
def open_stage_image(path, want_channel):
	"""(single-channel image, its spatial calibration) for one stage file.

	The image itself is returned uncalibrated so the stages stack cleanly;
	the calibration is kept for the composite (see spatial_calibration).
	"""
	imp, _n_series = bf_open(path)
	cal = spatial_calibration(imp.getCalibration())
	try:
		if imp.getBitDepth() == 24:
			IJ.run(imp, "8-bit", "")

		nch = imp.getNChannels()
		want = want_channel if want_channel > 0 else 1
		if nch > 1:
			if nch < want:
				raise StepError("channel %d requested but it has only %d "
				                "channel(s)." % (want, nch))
			chans = ChannelSplitter.split(imp)
			picked = chans[want - 1]
			for j, c in enumerate(chans):
				if j != want - 1:
					try:
						c.close()
					except (Exception, JavaException):
						pass
		elif imp.getStackSize() > 1:
			picked = Duplicator().run(imp, 1, 1, want, want, 1, 1)
		else:
			picked = imp
	except (Exception, JavaException):
		imp.changes = False
		imp.close()
		raise
	if picked is not imp:
		imp.changes = False
		imp.close()
	picked.setCalibration(Calibration())
	return picked, cal


def spatial_calibration(src):
	"""A new Calibration holding only the pixel size and unit of src."""
	cal = Calibration()
	cal.pixelWidth = src.pixelWidth
	cal.pixelHeight = src.pixelHeight
	cal.pixelDepth = src.pixelDepth
	cal.setUnit(src.getUnit())
	return cal


def promote(imp, depth):
	"""Convert to the common bit depth without clipping."""
	bd = imp.getBitDepth()
	if bd == depth:
		return imp
	st = imp.getStatistics(Measurements.MIN_MAX)
	lo, hi = st.min, st.max
	if hi <= lo:
		hi = lo + 1
	if depth == 8:
		imp.setDisplayRange(lo, hi)
		IJ.run(imp, "8-bit", "")
	else:
		if bd == 32:
			imp.setDisplayRange(lo, hi)
		IJ.run(imp, "16-bit", "")
	return imp


def set_overlay_position(r):
	"""Every channel (OVERLAY_ON_ALL_CHANNELS) or channel 1 only."""
	if OVERLAY_ON_ALL_CHANNELS:
		r.setPosition(0)
	else:
		r.setPosition(1, 0, 0)


def add_roi_file(ov, path, rgb, width, height):
	"""Add every ROI in a .zip / .roi file to the overlay.

	Returns (count, number of ROIs that reach past a width x height image).
	Raises StepError (from read_roiset) if the file cannot be read.
	"""
	col = Color(rgb[0], rgb[1], rgb[2])
	n, n_out = 0, 0
	for r in read_roiset(path).values():
		r.setStrokeColor(col)
		r.setStrokeWidth(OVERLAY_LINE_WIDTH)
		set_overlay_position(r)
		b = r.getFloatBounds()
		if b.x < 0 or b.y < 0 or b.x + b.width > width \
		        or b.y + b.height > height:
			n_out += 1
		ov.add(r)
		n += 1
	return n, n_out


def overlay_misfit(kind, present, changed):
	"""The stage label that makes a 'kind' overlay unusable, or None.

	The overlay's stage is the first stage of OVERLAY_STAGES[kind] that is
	in present (the stage variables opened for this section).

	changed maps a stage file variable to its label for every stage left
	out or scaled for a size mismatch.
	"""
	for v in OVERLAY_STAGES.get(kind, []):
		if v in present:
			return changed.get(v)
	return None


# ------------------------------------------------------ settings check
# Helpers for the "Check settings" window. They only read file names,
# dates and headers; no image is processed.

# The pipeline's default folder names (spec G5, plus stage 3's subfolders)
# and what each one normally holds.
USUAL_FOLDERS = OrderedDict([
    ("tifs", "raw images (stage 1)"),
    ("processed_bgsub_cleared", "background-subtracted images (stage 2b)"),
    ("probabilities", "ilastik probability maps"),
    ("thresholded", "thresholded masks (stage 3)"),
    ("particle_rois", "particle ROIs (stage 3)"),
    ("particle_counts", "stage 3 output (its masks are in thresholded/, "
                        "its particle ROIs in particle_rois/)"),
    ("rois", "anatomical ROIs (stage 2a)"),
    ("optimization", "stage 0 output"),
    ("pipeline_composites", "composites made by this script"),
])

# dialog file variable -> (short field name, the folder name it expects)
FILE_FIELDS = [
    ("rawFile", "Raw .tif image", "tifs"),
    ("bgsubFile", "Background-subtracted image", "processed_bgsub_cleared"),
    ("probFile", "ilastik probability image", "probabilities"),
    ("threshFile", "Thresholded mask", "thresholded"),
    ("particleFile", "Particle ROIs to overlay", "particle_rois"),
    ("anatFile", "Anatomical ROIs to overlay", "rois"),
]


def output_folder_exists(anchor_dir, requested_name, default_name,
                         parent_override):
	"""True if the folder resolve_output_dir() would use already exists."""
	name = (requested_name or "").strip() or default_name
	name = re.sub(r'[\\/:*?"<>|]', "_", name).strip() or default_name
	parent = given_path(parent_override)
	if parent is None and anchor_dir:
		parent = os.path.dirname(os.path.normpath(anchor_dir))
	if not parent:
		return True
	return os.path.isdir(os.path.join(parent, name))


def channel_tag(fname):
	"""Channel number written in a file name as _C<n> (the last one), or None.

	Stage 1 adds _C1, _C2 ... to one-channel files and stage 2b adds _C<n>
	when it extracts a channel; later stages keep the name.
	"""
	stem = os.path.splitext(os.path.basename(fname))[0]
	hits = re.findall(r"_C(\d+)(?=_|$)", stem)
	return int(hits[-1]) if hits else None


def one_per_channel(seen):
	"""From (channel, description) pairs, the first description per channel."""
	out, done = [], set()
	for t, d in seen:
		if t not in done:
			done.add(t)
			out.append(d)
	return out


def channel_summary(what, path, take):
	"""(window line, warning or None, number of channels) for one image file.

	The number of channels is 0 when it cannot be read.
	"""
	chans = describe_channels(path)
	name = os.path.basename(path)
	if not chans:
		return ("%s: channel information could not be read from %s; "
		        "channel %d is taken if it has several." % (what, name, take),
		        None, 0)
	if len(chans) == 1:
		return ("%s: one channel (%s), used as it is." % (what, name),
		        None, 1)
	if all([c.endswith("(no name stored)") for c in chans]):
		names = "the file stores no channel names"
	else:
		names = "; ".join(chans)
	line = ("%s: %d channels in %s (%s); channel %d is taken."
	        % (what, len(chans), name, names, take))
	warn = None
	if take > len(chans):
		warn = ("!Channel %d is to be taken from the '%s' image, but %s "
		        "has only %d channels, so that stage cannot be opened."
		        % (take, what, name, len(chans)))
	return line, warn, len(chans)


def output_anchor(folders):
	"""The folder the default output sits next to.

	The first folder given, after stepping out of stage 3's subfolders
	(NESTED_INPUT_FOLDERS), so the output lands in the slide folder:
	Slide1/particle_counts/thresholded -> Slide1/particle_counts, whose
	parent Slide1 then receives pipeline_composites/.
	"""
	nested = [n.lower() for n in NESTED_INPUT_FOLDERS]
	found = []
	for d in folders:
		if not d:
			continue
		a = os.path.normpath(d)
		while os.path.basename(a).lower() in nested:
			up = os.path.dirname(a)
			if not up or up == a:
				break
			a = up
		found.append(a)
	# Set Up Slide Folders layout: tifs/ sits in the slide folder and the
	# other stages in "<region> MBF"; prefer a folder inside the MBF folder,
	# so the composites land with that region's results.
	for a in found:
		if MBF_FOLDER_RE.search(os.path.basename(os.path.dirname(a))):
			return a
	return found[0] if found else None


# ================================================================= SETUP
# The composite is named after the first image given (its whole name, as
# every stage keeps the input name; the Log and the ROI Manager use the key).
# The files are then
# arranged exactly like one section of the batch version (one key per
# stage), so the build below is the batch code unchanged.
first = STAGES[0]
SECTION = key_from(first["file"]) or "section"
dk_name = (key_as_written(first["file"])
           or os.path.splitext(first["file"])[0])
display_key = {SECTION: dk_name}
OUT_STEM = os.path.splitext(first["file"])[0]
keys = [SECTION]

for st in STAGES:
	st["index"] = {SECTION: st["file"]}

PARTICLE_DIR, particle_index = None, {}
if PARTICLE_FILE:
	PARTICLE_DIR = os.path.dirname(PARTICLE_FILE)
	particle_index = {SECTION: os.path.basename(PARTICLE_FILE)}
ANAT_DIR, anat_index = None, {}
if ANAT_FILE:
	ANAT_DIR = os.path.dirname(ANAT_FILE)
	anat_index = {SECTION: os.path.basename(ANAT_FILE)}

# Do the picked files belong to the same section? Warn, do not stop: the
# user chose them deliberately.
given = [(st["label"], st["file"]) for st in STAGES]
if PARTICLE_FILE:
	given.append(("Particle ROIs", os.path.basename(PARTICLE_FILE)))
if ANAT_FILE:
	given.append(("Anatomical ROIs", os.path.basename(ANAT_FILE)))
file_keys = [key_from(f) for _l, f in given]
key_warning = None
if len(set(file_keys)) > 1:
	key_warning = ("The files picked do not share one RegionXXXX key:\n%s\n"
	               "The composite was built anyway and named %s%s.tif."
	               % ("\n".join(["  %s: %s" % (l, key_as_written(f) or
	                                           "(no key)")
	                             for l, f in given]),
	                  OUT_STEM, OUTPUT_SUFFIX))

# Do they come from the same slide folder? A file in tifs/, rois/, ... is
# two levels below it; one from particle_counts/thresholded/ or
# particle_counts/particle_rois/ is three. Warning only.
_slide_entries = [("%s file" % st["label"], st["path"],
                   3 if st["filevar"] == "threshFile" else 2) for st in STAGES]
if PARTICLE_FILE:
	_slide_entries.append(("Particle ROI file", PARTICLE_FILE, 3))
if ANAT_FILE:
	_slide_entries.append(("Anatomical ROI file", ANAT_FILE, 2))
SLIDE_WARNING = slide_folder_warning(_slide_entries)

# The output folder is created even when 'Save the composite to disk' is
# off: every run leaves its parameter record there.
_FIRST_DIR = output_anchor([st["dir"] for st in STAGES] + [PARTICLE_DIR, ANAT_DIR])
OUT_PARENT = (outParentDir if outParentDir is not None
              else mbf_output_parent(_FIRST_DIR))
if outParentDir is None and globals().get("_REGION") not in (None, globals().get("_SLIDE")):
	OUT_PARENT = _F(_REGION)       # slide mode: the region chosen
OUT_EXISTED = output_folder_exists(_FIRST_DIR, outFolderName,
                                   "pipeline_composites", OUT_PARENT)
OUT_DIR = resolve_output_dir(_FIRST_DIR, outFolderName,
                             "pipeline_composites", OUT_PARENT)
if OUT_DIR is None:
	raise SystemExit      # resolve_output_dir has already said why

IJ.log("=" * 64)
IJ.log("Pipeline composite builder, single image  (%s, version %s)"
       % (SCRIPT_NAME, SCRIPT_VERSION))
for st in STAGES:
	IJ.log("  C%d  %-16s %s" % (STAGES.index(st) + 1, st["label"], st["path"]))
if PARTICLE_FILE:
	IJ.log("  overlay: particles      %s" % PARTICLE_FILE)
if ANAT_FILE:
	IJ.log("  overlay: anatomical     %s" % ANAT_FILE)
IJ.log("  ROIs loaded as: %s" % roiLoadMode)
IJ.log("  depth: %s   on size mismatch: %s" % (TARGET_DEPTH, ON_SIZE_MISMATCH))
IJ.log("  output: %s%s" % (OUT_DIR, "" if saveComposites
                            else "   (saving off: parameter record only)"))
if key_warning:
	for line in key_warning.split("\n"):
		IJ.log("  ! " + line)
if SLIDE_WARNING:
	log_slide_warning(SLIDE_WARNING)
IJ.log("=" * 64)

show_windows = showResult
if LOAD_MANAGER and not showResult and (PARTICLE_DIR or ANAT_DIR):
	IJ.log("  ! ROIs were set to load into the ROI Manager, but 'Leave the "
	       "result open on screen' is off. The ROI Manager needs an open "
	       "image, so nothing will be loaded there; the saved file still "
	       "carries the ROIs as an overlay.")

# ========================================================= CHECK SETTINGS
# What is about to happen, in plain words, plus warnings ("!" lines) about
# likely mistakes. Nothing has been built yet; Cancel stops here.
check = []
warns = []
check.append("Images (one channel each, in this order):")
for st in STAGES:
	check.append("   C%d %s: %s" % (STAGES.index(st) + 1, st["label"],
	                                st["path"]))
check.append("Particle ROI overlay: %s" % (PARTICLE_FILE or "none"))
check.append("Anatomical ROI overlay: %s" % (ANAT_FILE or "none"))
check.append("Region: %s (from the first image)" % dk_name)

# channels inside each stage image
for st in STAGES:
	line, w, nch = channel_summary(st["label"], st["path"], st["channel"] or 1)
	st["n_channels"] = nch
	check.append(line)
	if w:
		warns.append(w)

if key_warning:
	warns.append("!The files picked do not share one RegionXXXX key (%s). "
	             "The composite is still built and named after the first "
	             "image." % ", ".join(["%s: %s" % (l, key_as_written(f)
	                                               or "no key")
	                                   for l, f in given]))
if SLIDE_WARNING:
	if "region (MBF)" in SLIDE_WARNING[0]:
		warns.append("!The files come from different region (MBF) folders of "
		             "one slide (listed in the Log). Files pair by RegionXXXX "
		             "only, so files from two regions would pair without any error.")
	else:
		warns.append("!The files do not all come from the same slide folder "
		             "(listed in the Log). Files pair by RegionXXXX only, so "
		             "files from two slides would pair without any error.")

# do the stages name the same channel (_C<n> in the name)?
seen = []
for st in STAGES:
	tag = channel_tag(st["file"])
	if tag is not None:
		seen.append((tag, "%s file %s is named _C%d" % (st["label"], st["file"], tag)))
	elif st["filevar"] != "probFile" and st.get("n_channels", 0) > 1:
		# A probability channel is an ilastik class, not a stain, so it is
		# not compared.
		take = st["channel"] or 1
		seen.append((take, "%s shows channel %d of %s"
		             % (st["label"], take, st["file"])))
if len(set([t for t, _d in seen])) > 1:
	warns.append("!The images seem to come from different channels: %s. "
	             "Check 'Channel to take from multi-channel RAW' and the "
	             "files picked." % "; ".join(one_per_channel(seen)))

# a probability map older than the image it should be made from
by_var = dict((st["filevar"], st) for st in STAGES)
if "bgsubFile" in by_var and "probFile" in by_var:
	bg, pr = by_var["bgsubFile"], by_var["probFile"]
	if key_from(bg["file"]) == key_from(pr["file"]):
		try:
			if os.path.getmtime(pr["path"]) + 1.0 < os.path.getmtime(bg["path"]):
				warns.append("!The probability map %s is older than the "
				             "background-subtracted image %s. It may have "
				             "been made from an earlier image; if so, run "
				             "ilastik again on the current one."
				             % (pr["file"], bg["file"]))
		except OSError:
			pass

# files that sit in another stage's folder, or the same file twice
seen_paths = {}
for var, field, expected in FILE_FIELDS:
	pth = given_path(globals().get(var))
	if not pth:
		continue
	base = os.path.basename(os.path.dirname(os.path.normpath(pth))).lower()
	if base in USUAL_FOLDERS and base != expected:
		warns.append("!'%s' is a file in a folder named %s/, which is "
		             "usually the folder for %s. Check that the right file "
		             "was picked." % (field, base, USUAL_FOLDERS[base]))
	kp = os.path.normcase(os.path.normpath(pth))
	if kp in seen_paths:
		warns.append("!'%s' and '%s' are the same file: %s."
		             % (seen_paths[kp], field, pth))
	else:
		seen_paths[kp] = field

out_name = OUT_STEM + OUTPUT_SUFFIX + ".tif"
if saveComposites and os.path.exists(os.path.join(OUT_DIR, out_name)):
	if overwrite:
		check.append("The existing %s will be replaced (overwrite is on)."
		             % out_name)
	else:
		warns.append("!%s already exists in the output folder and will NOT "
		             "be replaced ('Overwrite an existing composite' is off)."
		             % out_name)

check.append("Display mode: %s;  ROIs loaded as: %s" % (displayMode, roiLoadMode))
check.append("Bit depth: %s;  stages of a different size: %s"
             % (TARGET_DEPTH, ON_SIZE_MISMATCH))
check.append("Leave open on screen: %s;  save to disk: %s;  overwrite "
             "existing: %s" % ("yes" if showResult else "no",
                               "yes" if saveComposites else "no",
                               "yes" if overwrite else "no"))
check.append("Output folder: %s%s" % (OUT_DIR, "" if saveComposites
                                      else "  (parameter record only)"))
if saveComposites:
	check.append("Output file: %s" % out_name)

if not confirm_settings(SCRIPT_NAME, experiment_lines(globals().get("_SLIDE") or _FIRST_DIR) + warns + check, CONFIRM_BEFORE_RUN):
	IJ.log("%s: cancelled at the settings check; nothing was processed."
	       % SCRIPT_NAME)
	# Remove the output folder again if this run created it and it is empty.
	if not OUT_EXISTED:
		try:
			if not os.listdir(OUT_DIR):
				os.rmdir(OUT_DIR)
		except OSError:
			pass
	raise SystemExit


# ================================================================= RUN
if LOAD_MANAGER and show_windows and (PARTICLE_DIR or ANAT_DIR):
	try:
		_rm = RoiManager.getRoiManager()
		if RESET_ROI_MANAGER:
			_rm.reset()
	except (Exception, JavaException), e:
		IJ.log("  ! could not open the ROI Manager: %s" % str(e))

built, failed, noted = [], [], []
log_rows = []

try:
	for i, key in enumerate(keys):
		dk = display_key.get(key) or key
		IJ.showProgress(i, len(keys))
		IJ.showStatus("[%d/%d] %s - opening stages" % (i + 1, len(keys), dk))

		opened = []
		notes = []     # problems worth a look: flagged in the summary
		info = []      # routine facts: logged only
		comp = None
		comp_shown = False
		try:
			# ---- load whichever stages exist for this key ---------------
			loaded = []
			for st in STAGES:
				fname = st["index"].get(key)
				if fname is None:
					notes.append("stage '%s' has no file for this section"
					             % st["label"])
					continue
				try:
					im, cal = open_stage_image(os.path.join(st["dir"], fname),
					                           st["channel"])
				except StepError, e:
					notes.append("stage '%s' could not be opened: %s"
					             % (st["label"], str(e)))
					continue
				opened.append(im)
				loaded.append({"label": st["label"], "imp": im, "file": fname,
				               "filevar": st["filevar"], "cal": cal})

			if not loaded:
				raise StepError("no stage produced a usable image for this "
				                "section.")

			# ---- dimensions ----------------------------------------------
			ref_w = loaded[0]["imp"].getWidth()
			ref_h = loaded[0]["imp"].getHeight()
			present = [L["filevar"] for L in loaded]
			keep = []
			changed = {}    # stage file variable -> label, dropped or scaled
			for L in loaded:
				w, h = L["imp"].getWidth(), L["imp"].getHeight()
				if (w, h) == (ref_w, ref_h):
					keep.append(L)
					continue
				msg = ("stage '%s' is %dx%d but '%s' is %dx%d"
				       % (L["label"], w, h, loaded[0]["label"], ref_w, ref_h))
				if ON_SIZE_MISMATCH == "fail":
					raise StepError(
					    msg + ".\n      Stages should share dimensions; "
					    "something cropped or resized this one.")
				changed[L["filevar"]] = L["label"]
				if ON_SIZE_MISMATCH == "scale":
					ip = L["imp"].getProcessor()
					ip.setInterpolationMethod(ImageProcessor.BILINEAR)
					L["imp"].setProcessor(ip.resize(ref_w, ref_h))
					notes.append(msg + "; SCALED to match (do not measure "
					             "off it)")
					keep.append(L)
				else:
					notes.append(msg + "; left out of the composite")
			loaded = keep

			if not loaded:
				raise StepError("every stage was dropped on a size mismatch.")

			# ---- common bit depth ----------------------------------------
			IJ.showStatus("[%d/%d] %s - assembling" % (i + 1, len(keys), dk))
			depths = [L["imp"].getBitDepth() for L in loaded]
			if TARGET_DEPTH == "8":
				target = 8
			elif TARGET_DEPTH == "16":
				target = 16
			else:
				target = 16 if max(depths) > 8 else 8
			if len(set(depths)) > 1:
				info.append("stages were %s-bit; promoted to %d-bit"
				            % ("/".join([str(d) for d in sorted(set(depths))]),
				               target))
			for L in loaded:
				L["imp"] = promote(L["imp"], target)

			# ---- assemble ------------------------------------------------
			stack = ImageStack(ref_w, ref_h)
			ranges = []
			for L in loaded:
				st_ = L["imp"].getStatistics(Measurements.MIN_MAX)
				lo, hi = st_.min, st_.max
				if hi <= lo:
					hi = lo + 1
				ranges.append((lo, hi))
				stack.addSlice(L["label"], L["imp"].getProcessor())

			comp_imp = ImagePlus(OUT_STEM + OUTPUT_SUFFIX, stack)
			comp_imp.setDimensions(len(loaded), 1, 1)

			if displayMode.startswith("Grayscale"):
				mode = CompositeImage.GRAYSCALE
			elif displayMode.startswith("Color"):
				mode = CompositeImage.COLOR
			else:
				mode = CompositeImage.COMPOSITE
			comp = CompositeImage(comp_imp, mode)

			for c, (lo, hi) in enumerate(ranges):
				comp.setPosition(c + 1, 1, 1)
				comp.setDisplayRange(lo, hi)
			comp.setPosition(1, 1, 1)

			# Pixel size and unit of the first stage (Raw when present).
			comp.setCalibration(loaded[0]["cal"])

			# ---- overlays ------------------------------------------------
			IJ.showStatus("[%d/%d] %s - overlays" % (i + 1, len(keys), dk))
			ov = Overlay()
			n_part, n_anat = 0, 0
			used_files = []

			overlay_files = []
			if anat_index.get(key):
				overlay_files.append(("anatomical", ANAT_DIR, anat_index[key],
				                      ANATOMICAL_OUTLINE_COLOR))
			elif ANAT_DIR:
				notes.append("no anatomical ROI file for this section")
			if particle_index.get(key):
				overlay_files.append(("particle", PARTICLE_DIR,
				                      particle_index[key],
				                      PARTICLE_OUTLINE_COLOR))
			elif PARTICLE_DIR:
				notes.append("no particle ROI file for this section")

			for kind, odir, oname, ocol in overlay_files:
				bad = overlay_misfit(kind, present, changed)
				if bad:
					notes.append("%s ROIs (%s) left out: they were drawn on "
					             "the '%s' stage's pixels, and that stage "
					             "was %s for its size, so they would not "
					             "line up" % (kind, oname, bad,
					                          "scaled" if ON_SIZE_MISMATCH == "scale"
					                          else "left out"))
					continue
				try:
					n, n_out = add_roi_file(ov, os.path.join(odir, oname),
					                        ocol, ref_w, ref_h)
				except StepError, e:
					notes.append("%s ROIs could not be read (%s): %s"
					             % (kind, oname, str(e)))
					continue
				if kind == "anatomical":
					n_anat = n
					used_files.append("anatomical=" + oname)
				else:
					n_part = n
					used_files.append("particles=" + oname)
				if n_out:
					notes.append("%d of %d %s ROI(s) in %s reach past the "
					             "edge of the %dx%d composite; they may come "
					             "from an image of another size"
					             % (n_out, n, kind, oname, ref_w, ref_h))

			# ---- save -----------------------------------------------------
			# The file gets the overlay whenever there is one and the settings
			# allow it, independent of how ROIs are shown on screen.
			if ov.size() > 0 and (LOAD_OVERLAY or SAVE_OVERLAY_IN_FILE):
				comp.setOverlay(ov)

			saved = "no"
			if saveComposites:
				IJ.showStatus("[%d/%d] %s - saving" % (i + 1, len(keys), dk))
				opath = os.path.join(OUT_DIR, OUT_STEM + OUTPUT_SUFFIX + ".tif")
				if os.path.exists(opath) and not overwrite:
					notes.append("output already existed; not overwritten "
					             "(tick 'Overwrite an existing composite' to "
					             "replace it)")
				else:
					if IJ.saveAsTiff(comp, opath):
						saved = "yes"
					else:
						notes.append("the composite could not be saved to %s"
						             % opath)

			# ---- show -----------------------------------------------------
			n_manager = 0
			if show_windows:
				if not LOAD_OVERLAY:
					comp.setOverlay(None)
				comp.show()
				comp_shown = True

				if LOAD_MANAGER and ov.size() > 0:
					rm = RoiManager.getRoiManager()
					for j in range(ov.size()):
						r = ov.get(j).clone()
						base = r.getName() or ("roi_%d" % (j + 1))
						r.setName("%s: %s" % (dk, base))
						set_overlay_position(r)
						rm.addRoi(r)
						n_manager += 1
					if ROI_MANAGER_SHOW_ALL:
						rm.runCommand(comp, "Show All with labels"
						              if ROI_MANAGER_SHOW_LABELS
						              else "Show All without labels")

			built.append(key)
			if notes:
				noted.append(key)
			IJ.log("[%d/%d] %s   %d channel(s): %s   %dx%d %d-bit   "
			       "ROIs: %d particle, %d anatomical%s   saved: %s"
			       % (i + 1, len(keys), dk, len(loaded),
			          ", ".join([L["label"] for L in loaded]),
			          ref_w, ref_h, target, n_part, n_anat,
			          ("   (%d in ROI Manager)" % n_manager) if n_manager
			          else "", saved))
			if used_files:
				info.append("overlay files: %s" % ", ".join(used_files))
			for nt in info:
				IJ.log("      - %s" % nt)
			for nt in notes:
				IJ.log("      ! %s" % nt)

			log_rows.append([dk, str(len(loaded)),
			                 "|".join([L["label"] for L in loaded]),
			                 "%dx%d" % (ref_w, ref_h), str(target),
			                 str(n_part), str(n_anat), saved,
			                 "ok" if not notes else " | ".join(notes)])

		except StepError, e:
			failed.append(key)
			IJ.log("[%d/%d] %s  FAILED: %s" % (i + 1, len(keys), dk, str(e)))
			for nt in notes:
				IJ.log("      ! %s" % nt)
			log_rows.append([dk, "", "", "", "", "", "", "no",
			                 "FAILED: " + str(e).replace("\n", " ")])

		except (Exception, JavaException), e:
			failed.append(key)
			msg = "%s: %s" % (type(e).__name__, str(e))
			IJ.log("[%d/%d] %s  UNEXPECTED ERROR: %s"
			       % (i + 1, len(keys), dk, msg))
			for nt in notes:
				IJ.log("      ! %s" % nt)
			log_rows.append([dk, "", "", "", "", "", "", "no",
			                 "UNEXPECTED ERROR: " + msg.replace("\n", " ")])

		finally:
			if comp is not None and not comp_shown:
				try:
					comp.changes = False
					comp.close()
				except (Exception, JavaException):
					pass
			for im in opened:
				try:
					im.changes = False
					im.close()
				except (Exception, JavaException):
					pass
finally:
	IJ.showProgress(1.0)
	IJ.showStatus("")

# ------------------------------------------------------------------- log
log_path = None
if writeLog and OUT_DIR:
	# Named after the section so it never replaces a batch run's log.
	log_path = os.path.join(OUT_DIR, "_composite_log_%s.csv" % dk_name)
	if os.path.exists(log_path) and not overwrite:
		IJ.log("Debug log NOT saved - the file already exists (tick "
		       "'Overwrite an existing composite' to replace it): %s" % log_path)
		log_path = None
	else:
		try:
			fh = open(log_path, "w")
			try:
				fh.write("key,n_channels,channels,dimensions,bit_depth,"
				         "particle_rois,anatomical_rois,saved,status\n")
				for r in log_rows:
					fh.write(",".join(['"%s"' % str(c).replace('"', "'") for c in r]) + "\n")
			finally:
				fh.close()
			IJ.log("Log written: %s" % log_path)
		except IOError, e:
			log_path = None
			IJ.log("WARNING: could not write the log CSV: %s" % str(e))


# ------------------------------------------------------ parameter record
record_path = None
if WRITE_PARAMETER_RECORD and OUT_DIR:
	items = [
	    ("#Dialog", "")] + layout_record() + [
	    ("Raw .tif image (from tifs/)", shown(rawFile)),
	    ("Background-subtracted image (from processed_bgsub_cleared/)", shown(bgsubFile)),
	    ("ilastik probability image (from probabilities/)", shown(probFile)),
	    ("Thresholded mask (from particle_counts/thresholded/)", shown(threshFile)),
	    ("Particle ROIs to overlay, .zip or .roi (from particle_counts/particle_rois/)", shown(particleFile)),
	    ("Anatomical ROIs to overlay, .zip (from rois/)", shown(anatFile)),
	    ("Channel to take from multi-channel RAW", rawChannel),
	    ("Channel to take from multi-channel PROBABILITIES", probChannel),
	    ("Display mode", displayMode),
	    ("Load ROIs as", roiLoadMode),
	    ("Output location (blank = beside the folder that holds the input file)", shown(outParentDir)),
	    ("Name for the new output folder", outFolderName),
	    ("Leave the result open on screen", showResult),
	    ("Save the composite to disk", saveComposites),
	    ("Overwrite an existing composite", overwrite),
	    ("Write a debug log CSV", writeLog),
	    ("#Configuration", ""),
	    ("STAGE_ORDER", STAGE_ORDER),
	    ("KEY_PATTERN", KEY_PATTERN),
	    ("CASE_INSENSITIVE_KEYS", CASE_INSENSITIVE_KEYS),
	    ("TIF_EXTENSIONS", TIF_EXTENSIONS),
	    ("TARGET_DEPTH", TARGET_DEPTH),
	    ("ON_SIZE_MISMATCH", ON_SIZE_MISMATCH),
	    ("PARTICLE_OUTLINE_COLOR", PARTICLE_OUTLINE_COLOR),
	    ("ANATOMICAL_OUTLINE_COLOR", ANATOMICAL_OUTLINE_COLOR),
	    ("OVERLAY_LINE_WIDTH", OVERLAY_LINE_WIDTH),
	    ("OVERLAY_ON_ALL_CHANNELS", OVERLAY_ON_ALL_CHANNELS),
	    ("OVERLAY_STAGES", OVERLAY_STAGES),
	    ("RESET_ROI_MANAGER", RESET_ROI_MANAGER),
	    ("ROI_MANAGER_SHOW_ALL", ROI_MANAGER_SHOW_ALL),
	    ("ROI_MANAGER_SHOW_LABELS", ROI_MANAGER_SHOW_LABELS),
	    ("SAVE_OVERLAY_IN_FILE", SAVE_OVERLAY_IN_FILE),
	    ("OUTPUT_SUFFIX", OUTPUT_SUFFIX),
	    ("NESTED_INPUT_FOLDERS", ", ".join(NESTED_INPUT_FOLDERS)),
	    ("CONFIRM_BEFORE_RUN", CONFIRM_BEFORE_RUN),
	    ("#Inputs", ""),
	]
	for st in STAGES:
		items.append(("stage %s" % st["label"], st["path"]))
	items.append(("particle ROI file", PARTICLE_FILE or "(none)"))
	items.append(("anatomical ROI file", ANAT_FILE or "(none)"))
	items.append(("output folder", OUT_DIR))
	if key_warning:
		items.append(("key warning", "files do not share one RegionXXXX key"))
	record_path = write_run_record(OUT_DIR, SCRIPT_NAME, SCRIPT_VERSION, items)
	if record_path:
		IJ.log("Parameter record: %s" % record_path)


# ---------------------------------------------------- completion notice
IJ.log("-" * 64)
if built:
	summary = ["Composite built  : %s%s   (%s)"
	           % (OUT_STEM, OUTPUT_SUFFIX,
	              ", ".join([st["label"] for st in STAGES]))]
else:
	summary = ["Composite FAILED : %s  (see Log)" % dk_name]
if noted:
	summary.append("With notes       : see Log")
for line in summary:
	IJ.log(line)
IJ.log("-" * 64)
IJ.beep()

body = list(summary)
if key_warning:
	body.append("")
	body.append("WARNING: " + key_warning)
if SLIDE_WARNING:
	body.append("")
	body.append("WARNING: " + SLIDE_WARNING[0])
	body.extend(SLIDE_WARNING[1:])
if show_windows and built:
	body.append("")
	body.append("Scroll the channel slider (the 'c' bar) to move through "
	            "the pipeline stages.")
if OUT_DIR and saveComposites:
	body.append("")
	body.append("Output: " + OUT_DIR)
elif OUT_DIR:
	body.append("")
	body.append("'Save the composite to disk' was off: only the parameter "
	            "record was written, in " + OUT_DIR)
if record_path:
	body.append("Parameter record: " + record_path)
if log_path:
	body.append("")
	body.append("Log: " + log_path)
if failed or noted or key_warning or SLIDE_WARNING:
	body.append("")
	body.append("Check the Log window for details.")
if failed:
	title = "Composite complete - with failures"
elif noted or key_warning or SLIDE_WARNING:
	title = "Composite complete - with problems"
else:
	title = "Composite complete"
IJ.log(title)
IJ.showMessage(title, "\n".join(body))
