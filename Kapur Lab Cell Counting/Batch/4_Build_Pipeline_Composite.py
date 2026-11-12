# 4_Build_Pipeline_Composite.py
#
# Stacks each section's pipeline stages into one multi-channel QC image,
# with anatomical ROIs and counted particles laid over it.
#
# Menu: Plugins > Kapur Lab Cell Counting > Batch > 4 Build Pipeline Composite
#
# Fiji / ImageJ Jython script. Scroll the channel slider to follow the same
# field through the workflow (C1 Raw, C2 Background subtracted and cleared,
# C3 ilastik probabilities, C4 Thresholded mask); the counted particles and
# anatomical regions show as an overlay on every channel. Every folder is
# OPTIONAL: missing stages are absent and the channels close up. Sections
# pair by the leading RegionXXXX token; one is built if ANY folder has it.
#
# Reads (every folder is optional; at least one image folder is needed):
#   tifs/                            raw images (stage 1)
#   processed_bgsub_cleared/         background subtracted + cleared (2b)
#   probabilities/                   ilastik probability maps
#   particle_counts/thresholded/     thresholded masks, <stem>_thresh.tif (3)
#   particle_counts/particle_rois/   counted particles, overlay (3):
#                                    <stem>_particles.zip and/or
#                                    <stem>_particles_combined.roi
#   rois/                            anatomical ROI .zip files, overlay (2a)
# Writes (into a new folder, default pipeline_composites/; inputs untouched):
#   RegionXXXX_composite.tif         one multi-channel image per section
#   _run_4_Build_Pipeline_Composite_<date-time>.txt   parameter record
#   _composite_log.csv               only if the debug log CSV is ticked
#
# A Check settings window comes first (CONFIRM_BEFORE_RUN = False skips it).
#
# Usage: Plugins > Kapur Lab Cell Counting > Batch > 4 Build Pipeline
#        Composite, or open this file in the Script Editor (File > New >
#        Script..., or Plugins > Scripting > Script Editor) with Language =
#        Python (Jython) and press Run.

#@ File    (label="Slide folder (the scripts find its subfolders)", style="directory") slideDir
#@ String  (label="Region (its MBF folder; blank = choose from a list)", value="", required=false) regionName
#@ String  (label="Only use raw images whose name contains (blank = all; e.g. _C2)", value="", required=false) rawNameFilter
#@ Integer (label="Channel to take from multi-channel RAW", value=1, min=0) rawChannel
#@ Integer (label="Channel to take from multi-channel PROBABILITIES", value=1, min=0) probChannel
#@ String  (label="Display mode", choices={"Grayscale - scroll one stage at a time", "Color - one LUT per stage", "Composite - all stages merged"}, style="listBox") displayMode
#@ String  (label="Load ROIs as", choices={"Overlay", "ROI Manager", "Both"}, style="radioButtonHorizontal") roiLoadMode
#@ File    (label="Output location (blank = one level above the input)", style="directory", required=false) outParentDir
#@ String  (label="Name for the new output folder", value="pipeline_composites") outFolderName
#@ Boolean (label="Open the composites on screen", value=true) showComposites
#@ Boolean (label="Save the composites to disk", value=true) saveComposites
#@ Boolean (label="Overwrite existing composites", value=false) overwrite
#@ Boolean (label="Write a debug log CSV", value=false) writeLog


# =========================================================================
# ===  USER CONFIGURATION  ================================================
# =========================================================================
# Everything you may want to change; nothing below the END banner needs
# editing for routine use.

# ---- STAGES -------------------------------------------------------------
# (label, folder variable name, channel variable) in channel order. Labels
# are the channel labels; to add a stage, add an entry and a folder
# parameter. BgSub takes the raw channel (2b keeps the raw channel order);
# a single-channel image is used as it is.
STAGE_ORDER = [
    ("Raw",            "rawDir",    "rawChannel"),
    ("BgSub_Cleared",  "bgsubDir",  "rawChannel"),
    ("Probabilities",  "probDir",   "probChannel"),
    ("Thresholded",    "threshDir", None),
]


# ---- FILENAME STANDARD --------------------------------------------------
# Pairing key: the leading RegionXXXX token (the rest of the name is ignored).
KEY_PATTERN = r"^(Region\d+)"
CASE_INSENSITIVE_KEYS = True

# True warns (Log and completion message; never stops) when the input
# folders are not in one slide folder: two slides' folders would pair
# without any error.
WARN_ON_DIFFERENT_SLIDE_FOLDERS = True

# Applied to every folder before pairing (e.g. REQUIRE_IN_NAME = "_C2").
REQUIRE_IN_NAME = ""
EXCLUDE_IN_NAME = ""

TIF_EXTENSIONS = [".tif", ".tiff"]


# ---- BIT DEPTH ----------------------------------------------------------
# Stages are promoted to one depth (each channel keeps its display range):
#   "auto"  16-bit if any stage is 16-bit or deeper, otherwise 8-bit
#   "8"     everything to 8-bit (smaller; raw dynamic range is compressed)
#   "16"    everything to 16-bit
TARGET_DEPTH = "auto"


# ---- SIZE MISMATCH ------------------------------------------------------
# When a stage's dimensions differ:
#   "skip"   leave that stage out of this section's composite and say so
#   "scale"  resize it to match the first stage (QC only - do not measure
#            anything off a scaled channel)
#   "fail"   treat the section as failed
ON_SIZE_MISMATCH = "skip"


# ---- OVERLAYS -----------------------------------------------------------
# True prefers the individual particle set (<stem>_particles.zip, region
# names kept), False the combined outline (<stem>_particles_combined.roi,
# lighter); the other is used when the preferred one is missing.
PREFER_INDIVIDUAL_PARTICLES = True

PARTICLE_OUTLINE_COLOR = (255, 255, 0)      # yellow
ANATOMICAL_OUTLINE_COLOR = (0, 255, 255)    # cyan
OVERLAY_LINE_WIDTH = 1

# True: overlays (and ROI Manager entries) show on every channel; False:
# on channel 1 only.
OVERLAY_ON_ALL_CHANNELS = True

# The stage whose pixels each overlay belongs to: the first of its list
# present for a section. When that stage was left out or scaled
# (ON_SIZE_MISMATCH) the overlay is left out, and the Log says so.
OVERLAY_STAGES = {
    "anatomical": ["rawDir", "bgsubDir"],
    "particle":   ["probDir", "threshDir"],
}

# ROI Manager loading (dialog: "ROI Manager" or "Both"): one global list;
# entries are prefixed with the section key (Region0042: Caudoputamen-L_0001).
RESET_ROI_MANAGER = True             # clear it once, at the start of the run
ROI_MANAGER_SHOW_ALL = True          # outline every entry on the image
ROI_MANAGER_SHOW_LABELS = False      # names on the image (cluttered)

# The saved .tif carries the ROIs as an overlay; False saves without them
# in "ROI Manager" mode.
SAVE_OVERLAY_IN_FILE = True


# ---- OUTPUT -------------------------------------------------------------
# Added to the name of the first stage's file for the section, e.g.
#   Region0011_ChannelFITCTRITC_Seq0011_MAX_C2_composite.tif
OUTPUT_SUFFIX = "_composite"

# With "Output location" blank, the output goes one level above the first
# folder given (stages in order, then particle and anatomical ROIs), after
# stepping out of these stage 3 subfolders.
NESTED_INPUT_FOLDERS = ["thresholded", "watershed", "QC", "particle_rois"]

# Above this many sections the composites are saved but not shown.
MAX_WINDOWS = 8

# Save a record of every setting used (_run_...txt) in the output folder.
WRITE_PARAMETER_RECORD = True


# ---- SAFETY CHECKS ------------------------------------------------------
# True shows the "Check settings" window first; False skips it (warnings
# are logged either way).
CONFIRM_BEFORE_RUN = True

# =========================================================================
# ===  END OF USER CONFIGURATION  =========================================
# =========================================================================

SCRIPT_NAME = "4_Build_Pipeline_Composite"
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
# A region folder (Set Up Slide Folders) has the word MBF in its name.
MBF_FOLDER_RE = re.compile(r"(^|[^A-Za-z0-9])MBF([^A-Za-z0-9]|$)", re.IGNORECASE)


def mbf_output_parent(anchor):
	"""Where a blank 'Output location' sends the output (a File), or None for
	one level above anchor: into the slide's only "<region> MBF" folder when
	the slide has one MBF folder and no protocol-layout subfolders."""
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
	if [d for d in names if d.lower() in ("xml", "rois", "probabilities",
	                                      "processed_bgsub_cleared",
	                                      "particle_counts")]:
		return None
	mbfs = layout_regions(parent)
	if len(mbfs) == 1:
		return File(os.path.join(parent, mbfs[0]))
	return None


def slide_folder_warning(entries):
	"""Warning lines when the inputs are not from one slide folder, else
	None. entries: [(label, path, levels up to the slide folder), ...]."""
	if not WARN_ON_DIFFERENT_SLIDE_FOLDERS or len(entries) < 2:
		return None
	slides = []
	regions = set()
	for _label, path, levels in entries:
		p = os.path.normpath(os.path.abspath(path))
		for _k in range(levels):
			p = os.path.dirname(p)
		# A "<region> MBF" folder is part of its slide folder: step out.
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


# ------------------------------------------------------ dialog folders
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
	    ('Folder of raw .tif images (tifs/)', "dir", (lambda p: p if os.path.isdir(p) else "")(layout_find(_SLIDE, _REGION, "tifs")), None, False),
	    ('Folder of background-subtracted images (processed_bgsub_cleared/)', "dir", (lambda p: p if os.path.isdir(p) else "")(layout_find(_SLIDE, _REGION, "processed_bgsub_cleared")), None, False),
	    ('Folder of ilastik probabilities (probabilities/)', "dir", (lambda p: p if os.path.isdir(p) else "")(layout_find(_SLIDE, _REGION, "probabilities")), None, False),
	    ('Folder of thresholded masks (particle_counts/thresholded/)', "dir", (lambda p: p if os.path.isdir(p) else "")(layout_find(_SLIDE, _REGION, "particle_counts/thresholded")), None, False),
	    ('Folder of particle ROIs to overlay (particle_counts/particle_rois/)', "dir", (lambda p: p if os.path.isdir(p) else "")(layout_find(_SLIDE, _REGION, "particle_counts/particle_rois")), None, False),
	    ('Folder of anatomical ROIs to overlay (rois/)', "dir", (lambda p: p if os.path.isdir(p) else "")(layout_find(_SLIDE, _REGION, "rois")), None, False),
	])
	if _got is None:
		raise SystemExit
	rawDir = _F(_got[0]) if _got[0] else None
	bgsubDir = _F(_got[1]) if _got[1] else None
	probDir = _F(_got[2]) if _got[2] else None
	threshDir = _F(_got[3]) if _got[3] else None
	particleDir = _F(_got[4]) if _got[4] else None
	anatDir = _F(_got[5]) if _got[5] else None


# STAGE_ORDER names its dialog parameters; they are looked up by name.
unknown_params = []
for _label, _dirvar, _chvar in STAGE_ORDER:
	for _v in (_dirvar, _chvar):
		if _v and _v not in globals():
			unknown_params.append(_v)

RAW_NAME_FILTER = (rawNameFilter or "").strip()

STAGES = []
bad_folders = []
for label, dirvar, chvar in STAGE_ORDER:
	d = given_path(globals().get(dirvar))
	if d is None:
		continue
	if not os.path.isdir(d):
		bad_folders.append((label, d))
		continue
	ch = globals().get(chvar) if chvar else None
	STAGES.append({"label": label, "dir": d, "dirvar": dirvar,
	               "channel": int(ch) if ch else 0})

# A missing particle folder is not an error (stage 3 writes particle_rois/
# only when asked): the composites are built without that overlay.
PARTICLE_DIR = given_path(particleDir)
PARTICLE_MISSING = None
if PARTICLE_DIR and not os.path.isdir(PARTICLE_DIR):
	PARTICLE_MISSING = PARTICLE_DIR
	PARTICLE_DIR = None
ANAT_DIR = given_path(anatDir)
if ANAT_DIR and not os.path.isdir(ANAT_DIR):
	bad_folders.append(("Anatomical ROIs", ANAT_DIR))
	ANAT_DIR = None


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

if bad_folders:
	IJ.error("Folder not found",
	         "These fields were filled in, but the path is not an existing "
	         "folder:\n\n%s\n\nPick the folder again, or leave the field "
	         "blank to leave that stage out."
	         % "\n".join(["%s:  %s" % (l, p) for l, p in bad_folders]))
	raise SystemExit

if not STAGES:
	IJ.error("No image folders given",
	         "At least one of the four stage folders has to be filled in.\n\n"
	         "Raw, Background subtracted, Probabilities, Thresholded - any "
	         "combination is fine, but there has to be at least one.")
	raise SystemExit

if len(STAGES) == 1 and not (PARTICLE_DIR or ANAT_DIR):
	IJ.error("Only one stage given",
	         "Only the '%s' folder was filled in, and no overlay folders "
	         "either, so the result would be a copy of an image you already "
	         "have.\n\nAdd a second stage folder, or an ROI folder to overlay."
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

if not showComposites and not saveComposites:
	IJ.error("Nothing would be produced",
	         "Both 'Open the composites on screen' and 'Save the composites "
	         "to disk' are off, so the composites would be built and then "
	         "thrown away.\n\nTick at least one of them.")
	raise SystemExit


# ---------------------------------------------------------------- keys
def key_as_written(filename):
	"""The Region token exactly as it appears in the file name."""
	m = re.search(KEY_PATTERN, os.path.splitext(os.path.basename(filename))[0])
	return m.group(1) if m else None


def output_anchor(folders):
	"""The folder the default output sits next to: the first folder given,
	after stepping out of NESTED_INPUT_FOLDERS."""
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
	# Prefer a folder inside a "<region> MBF" folder (that region's results).
	for a in found:
		if MBF_FOLDER_RE.search(os.path.basename(os.path.dirname(a))):
			return a
	return found[0] if found else None


def index_folder(d, exts, allow_filter=True, also_require=""):
	"""(key -> filename, key -> duplicate files, files with no key).
	also_require: extra text a name must contain (raw name filter)."""
	out, dupes, nokey = {}, {}, []
	for f in sorted(os.listdir(d)):
		if (not os.path.isfile(os.path.join(d, f)) or f.startswith("_")
		        or os.path.splitext(f)[1].lower() not in exts
		        or (allow_filter and not name_allowed(f))
		        or (also_require and also_require not in f)):
			continue
		k = key_from(f)
		if k is None:
			nokey.append(f)
		elif k in out:
			dupes.setdefault(k, [out[k]]).append(f)
		else:
			out[k] = f
	return out, dupes, nokey


def index_roi_folder(d, what, ext_order, one_per_type):
	"""(key -> the .zip/.roi file to use, number of duplicate keys).
	ext_order: file types by preference. one_per_type: only a second file
	of the SAME type is a duplicate (particle folder). Duplicates are logged
	and the first file is used."""
	groups = OrderedDict()
	for f in sorted(os.listdir(d)):
		k = key_from(f)
		if (f.startswith("_") or not os.path.isfile(os.path.join(d, f))
		        or os.path.splitext(f)[1].lower() not in ext_order or k is None):
			continue
		groups.setdefault(k, []).append(f)

	out, n_dupes = {}, 0
	for k, files in groups.items():
		chosen = None
		for ext in ext_order:
			cands = [f for f in files if os.path.splitext(f)[1].lower() == ext]
			if cands:
				chosen = cands[0]
				break
		out[k] = chosen
		if one_per_type:
			ext = os.path.splitext(chosen)[1].lower()
			clash = [f for f in files if os.path.splitext(f)[1].lower() == ext]
		else:
			clash = files
		if len(clash) > 1:
			n_dupes += 1
			IJ.log("  ! %s: key '%s' matches several files: %s - using %s, "
			       "ignoring the rest" % (what, key_as_written(chosen),
			                              ", ".join(clash), chosen))
	return out, n_dupes


# ------------------------------------------------------------ image prep
def open_stage_image(path, want_channel):
	"""(uncalibrated single-channel image, its spatial calibration)."""
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

	changed maps a stage folder variable to its label for every stage left
	out or scaled for a size mismatch in this section.
	"""
	for v in OVERLAY_STAGES.get(kind, []):
		if v in present:
			return changed.get(v)
	return None


# ------------------------------------------------------ settings check
# The pipeline's default folder names and what each normally holds.
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

# dialog folder variable -> (short field name, the folder name it expects)
FOLDER_FIELDS = [
    ("rawDir", "Folder of raw .tif images", "tifs"),
    ("bgsubDir", "Folder of background-subtracted images",
     "processed_bgsub_cleared"),
    ("probDir", "Folder of ilastik probabilities", "probabilities"),
    ("threshDir", "Folder of thresholded masks", "thresholded"),
    ("particleDir", "Folder of particle ROIs to overlay", "particle_rois"),
    ("anatDir", "Folder of anatomical ROIs to overlay", "rois"),
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
	hits = re.findall(r"_C(\d+)(?=_|$)", stem_of(fname))
	return int(hits[-1]) if hits else None


def few(names, n=4):
	"""'a, b, c, d and 3 more' for a window line."""
	names = list(names)
	text = ", ".join(names[:n])
	if len(names) > n:
		text += " and %d more" % (len(names) - n)
	return text


def folder_name_warnings(fields):
	"""Warnings for fields that point at another stage's usual folder.

	fields: list of (field name, path, expected folder name). The folder
	name is compared case-insensitively with USUAL_FOLDERS.
	"""
	out = []
	for field, path, expected in fields:
		if not path:
			continue
		base = os.path.basename(os.path.normpath(path)).lower()
		if base in USUAL_FOLDERS and base != expected:
			out.append("!'%s' points at a folder named %s/, which is usually "
			           "the folder for %s. Check that the right folder was "
			           "picked." % (field, base, USUAL_FOLDERS[base]))
	return out


def same_path_warnings(fields):
	"""Warnings when one folder (or file) is given in two fields."""
	out, seen = [], {}
	for field, path, _expected in fields:
		if not path:
			continue
		k = os.path.normcase(os.path.normpath(path))
		if k in seen:
			out.append("!'%s' and '%s' are the same: %s. Each stage "
			           "normally has its own folder." % (seen[k], field, path))
		else:
			seen[k] = field
	return out


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
		return ("%s: one channel per image (%s), used as it is."
		        % (what, name), None, 1)
	if all([c.endswith("(no name stored)") for c in chans]):
		names = "the file stores no channel names"
	else:
		names = "; ".join(chans)
	line = ("%s: %d channels in %s (%s); channel %d is taken."
	        % (what, len(chans), name, names, take))
	warn = None
	if take > len(chans):
		warn = ("!Channel %d is to be taken from the '%s' images, but %s "
		        "has only %d channels, so that stage cannot be opened."
		        % (take, what, name, len(chans)))
	return line, warn, len(chans)


# ================================================================= SETUP
n_setup_warnings = 0
problems = []
for st in STAGES:
	is_raw = (st["dirvar"] == "rawDir")
	idx, dupes, nokey = index_folder(st["dir"], TIF_EXTENSIONS, True,
	                                 RAW_NAME_FILTER if is_raw else "")
	st["index"] = idx
	st["dupes"] = dupes
	st["channel_for"] = {}
	for f in nokey:
		IJ.log("  ! stage '%s': no key in '%s' - ignored" % (st["label"], f))
		n_setup_warnings += 1
	if not idx:
		problems.append("stage '%s': no usable images found in %s"
		                % (st["label"], st["dir"]))


def stem_of(fname):
	return os.path.splitext(fname)[0]


def is_name_prefix(short, longer):
	"""True when 'longer' is 'short' with more added after a '_' (or equal)."""
	return longer == short or (longer.startswith(short)
	                           and longer[len(short)] == "_")


# Several files for one section in a stage folder: chosen latest stage
# first, (a) the file whose name starts a later stage's chosen name, (b) Raw
# only: the one ending in _C<n> for raw channel n > 0, (c) else the run stops
# with "Duplicate keys".
LATER_ORDER = ["bgsubDir", "probDir", "threshDir"]
auto_choices = []
auto_why = {}         # (stage folder variable, key) -> reason
dup_problems = []
raw_dupes = False
for si in range(len(STAGES) - 1, -1, -1):
	st = STAGES[si]
	is_raw = (st["dirvar"] == "rawDir")
	for k, fs in sorted(st["dupes"].items()):
		chosen, why = None, None
		later = dict((x["dirvar"], x) for x in STAGES[si + 1:])
		for dv in LATER_ORDER:
			other = later.get(dv)
			if other is None or k not in other["index"] or k in other["dupes"]:
				continue
			target = stem_of(other["index"][k])
			hits = [f for f in fs if is_name_prefix(stem_of(f), target)]
			if hits:
				hits.sort(key=lambda f: len(stem_of(f)), reverse=True)
				chosen = hits[0]
				why = "its name starts the %s file %s" % (other["label"],
				                                          other["index"][k])
				break
		if chosen is None and is_raw and st["channel"] > 0:
			suffix = "_C%d" % st["channel"]
			hits = [f for f in fs if stem_of(f).endswith(suffix)]
			if len(hits) == 1:
				chosen = hits[0]
				st["channel_for"][k] = 1
				why = ("it ends in %s ('Channel to take from multi-channel "
				       "RAW' = %d); its only channel is used"
				       % (suffix, st["channel"]))
		if chosen is not None:
			st["index"][k] = chosen
			del st["dupes"][k]
			auto_why[(st["dirvar"], k)] = why
			auto_choices.append("stage '%s', %s: used %s (of %s) because %s"
			                    % (st["label"], k, chosen, ", ".join(fs), why))
		else:
			if is_raw:
				raw_dupes = True
			dup_problems.append("stage '%s': key '%s' matches several files: "
			                    "%s" % (st["label"], k, ", ".join(fs)))
for line in auto_choices:
	IJ.log("  . several files for one section: " + line)

if problems:
	for p in problems:
		IJ.log("  ! " + p)
	n_setup_warnings += len(problems)

if dup_problems:
	for p in dup_problems:
		IJ.log("  ! " + p)
	advice = ("For other folders, set REQUIRE_IN_NAME in the configuration "
	          "block to the text identifying the variant you want (for "
	          "example \"_C2\"), or split them into separate folders.")
	if raw_dupes:
		advice = ("For the Raw folder, type the text that identifies the "
		          "variant you want (for example _C2) into the dialog field "
		          "\"Only use raw images whose name contains (blank = "
		          "all; e.g. _C2)\". " + advice)
	IJ.error("Duplicate keys",
	         "More than one file shares the same RegionXXXX key, and no "
	         "later stage or channel number says which one to use:\n\n%s"
	         "\n\n%s" % ("\n".join(dup_problems[:10]), advice))
	raise SystemExit

STAGES = [st for st in STAGES if st["index"]]
if not STAGES:
	IJ.error("No images found",
	         "None of the folders given contained usable images.\n\n"
	         "Check the folders, the extensions (%s) and REQUIRE_IN_NAME."
	         % ", ".join(TIF_EXTENSIONS))
	raise SystemExit

particle_index, anat_index = {}, {}
if PARTICLE_DIR:
	order = [".zip", ".roi"] if PREFER_INDIVIDUAL_PARTICLES else [".roi", ".zip"]
	particle_index, nd = index_roi_folder(PARTICLE_DIR, "particle ROI folder",
	                                      order, True)
	n_setup_warnings += nd
	if not particle_index:
		n_setup_warnings += 1
		hint = ""
		if os.path.isdir(os.path.join(PARTICLE_DIR, "particle_rois")):
			hint = (" - it has a 'particle_rois' subfolder; pick that "
			        "folder instead")
		IJ.log("  ! no .zip/.roi files found in the particle ROI folder%s"
		       % hint)
if ANAT_DIR:
	anat_index, nd = index_roi_folder(ANAT_DIR, "anatomical ROI folder",
	                                  [".zip", ".roi"], False)
	n_setup_warnings += nd
	if not anat_index:
		n_setup_warnings += 1
		IJ.log("  ! no .zip/.roi files found in the anatomical ROI folder")

# A section is built if ANY stage has it; named after its first stage's file.
all_keys = set()
display_key = {}
out_stem = {}
for st in STAGES:
	for k, f in st["index"].items():
		all_keys.add(k)
		if k not in display_key:
			display_key[k] = key_as_written(f)
			out_stem[k] = stem_of(f)
keys = sorted(all_keys)

if showComposites and len(keys) > MAX_WINDOWS and not saveComposites:
	IJ.error("Nothing would be produced",
	         "There are %d sections, which is more than MAX_WINDOWS (%d), "
	         "so they will not be opened - and saving is off, so nothing "
	         "would be written either.\n\n"
	         "Tick 'Save the composites to disk', or raise MAX_WINDOWS."
	         % (len(keys), MAX_WINDOWS))
	raise SystemExit

# Created even with saving off (parameter record).
first_dir = output_anchor([st["dir"] for st in STAGES]
                          + [PARTICLE_DIR, ANAT_DIR])
OUT_PARENT = (outParentDir if outParentDir is not None
              else mbf_output_parent(first_dir))
if outParentDir is None and globals().get("_REGION") not in (None, globals().get("_SLIDE")):
	OUT_PARENT = _F(_REGION)       # slide mode: the region chosen
OUT_EXISTED = output_folder_exists(first_dir, outFolderName,
                                   "pipeline_composites", OUT_PARENT)
OUT_DIR = resolve_output_dir(first_dir, outFolderName,
                             "pipeline_composites", OUT_PARENT)
if OUT_DIR is None:
	raise SystemExit

IJ.log("=" * 64)
IJ.log("Pipeline composite builder  (%s, version %s)"
       % (SCRIPT_NAME, SCRIPT_VERSION))
if RAW_NAME_FILTER:
	IJ.log("Raw name filter (dialog): only Raw images whose name contains "
	       "%r" % RAW_NAME_FILTER)
elif REQUIRE_IN_NAME:
	IJ.log("Name filter: REQUIRE_IN_NAME = %r (all folders)" % REQUIRE_IN_NAME)
for st in STAGES:
	IJ.log("  C%d  %-16s %d file(s)   %s"
	       % (STAGES.index(st) + 1, st["label"], len(st["index"]), st["dir"]))
if PARTICLE_DIR:
	IJ.log("  overlay: particles      %d file(s)   %s   (prefer %s)"
	       % (len(particle_index), PARTICLE_DIR,
	          "individual .zip" if PREFER_INDIVIDUAL_PARTICLES
	          else "combined .roi"))
if PARTICLE_MISSING:
	IJ.log("  overlay: particles      folder not found, left out: %s"
	       % PARTICLE_MISSING)
	IJ.log("           (stage 3 writes particle_rois/ only when 'Export "
	       "particle ROIs' is not 'Nothing')")
if ANAT_DIR:
	IJ.log("  overlay: anatomical     %d file(s)   %s"
	       % (len(anat_index), ANAT_DIR))
IJ.log("  ROIs loaded as: %s" % roiLoadMode)
IJ.log("  sections: %d   depth: %s   on size mismatch: %s"
       % (len(keys), TARGET_DEPTH, ON_SIZE_MISMATCH))
IJ.log("  output: %s%s" % (OUT_DIR, "" if saveComposites
                            else "   (saving off: parameter record only)"))

# Stage 3's folders sit one level deeper inside the slide folder.
_slide_entries = [("%s folder" % st["label"], st["dir"],
                   2 if st["dirvar"] == "threshDir" else 1) for st in STAGES]
if PARTICLE_DIR:
	_slide_entries.append(("Particle ROI folder", PARTICLE_DIR, 2))
if ANAT_DIR:
	_slide_entries.append(("Anatomical ROI folder", ANAT_DIR, 1))
SLIDE_WARNING = slide_folder_warning(_slide_entries)
if SLIDE_WARNING:
	log_slide_warning(SLIDE_WARNING)
IJ.log("=" * 64)

show_windows = showComposites
if LOAD_MANAGER and not showComposites and (PARTICLE_DIR or ANAT_DIR):
	IJ.log("  ! ROIs were set to load into the ROI Manager, but 'Open the "
	       "composites on screen' is off. The ROI Manager needs an open image, "
	       "so nothing will be loaded there; the saved files still carry the "
	       "ROIs as an overlay.")
if show_windows and len(keys) > MAX_WINDOWS:
	show_windows = False
	IJ.log("  ! %d sections is more than MAX_WINDOWS (%d); composites will be "
	       "saved but not opened." % (len(keys), MAX_WINDOWS))


# ========================================================= CHECK SETTINGS
check = []
warns = []
check.append("Stage folders (one channel each, in this order):")
for st in STAGES:
	extra = ""
	if st["dirvar"] == "rawDir" and RAW_NAME_FILTER:
		extra = ", only names containing '%s'" % RAW_NAME_FILTER
	check.append("   C%d %s: %s  (%d file(s)%s)"
	             % (STAGES.index(st) + 1, st["label"], st["dir"],
	                len(st["index"]), extra))
if PARTICLE_DIR:
	check.append("Particle ROI overlay: %s  (%d file(s), prefer the %s)"
	             % (PARTICLE_DIR, len(particle_index),
	                "individual .zip" if PREFER_INDIVIDUAL_PARTICLES
	                else "combined .roi"))
elif PARTICLE_MISSING:
	check.append("Particle ROI overlay: folder not found, left out: %s"
	             % PARTICLE_MISSING)
else:
	check.append("Particle ROI overlay: none")
if ANAT_DIR:
	check.append("Anatomical ROI overlay: %s  (%d file(s))"
	             % (ANAT_DIR, len(anat_index)))
else:
	check.append("Anatomical ROI overlay: none")
for p in problems:
	warns.append("!%s, so that stage is left out. Check the folder and the "
	             "name filters." % (p[0].upper() + p[1:]))

shown_keys = [display_key.get(k) or k for k in keys]
check.append("Composites to build: %d region(s): %s"
             % (len(keys), few(shown_keys, 5)))

# the files the first region will use
k0 = keys[0]
check.append("Files for %s (the first region):" % (display_key.get(k0) or k0))
for st in STAGES:
	fname = st["index"].get(k0)
	if fname is None:
		check.append("   %s: no file, this channel will be missing"
		             % st["label"])
		continue
	why = auto_why.get((st["dirvar"], k0))
	check.append("   %s: %s%s" % (st["label"], fname,
	                              ("  (picked automatically: %s)" % why)
	                              if why else ""))
if PARTICLE_DIR:
	check.append("   particle ROIs: %s" % (particle_index.get(k0) or "no file"))
if ANAT_DIR:
	check.append("   anatomical ROIs: %s" % (anat_index.get(k0) or "no file"))
check.append("   output: %s%s.tif" % (out_stem.get(k0, k0), OUTPUT_SUFFIX))

# regions that some folder does not cover
gaps = []
for st in STAGES:
	gaps.append((st["label"] + " folder",
	             [display_key.get(k) or k for k in keys if k not in st["index"]],
	             "that channel"))
if PARTICLE_DIR and particle_index:
	gaps.append(("particle ROI folder",
	             [display_key.get(k) or k for k in keys if k not in particle_index],
	             "the particle overlay"))
if ANAT_DIR and anat_index:
	gaps.append(("anatomical ROI folder",
	             [display_key.get(k) or k for k in keys if k not in anat_index],
	             "the anatomical overlay"))
n_gaps = 0
for what, missing, lacks in gaps:
	if missing:
		n_gaps += 1
		warns.append("!The %s has no file for %d of the %d region(s) (%s); "
		             "those composites will lack %s. The folders may not "
		             "cover the same regions." % (what, len(missing), len(keys),
		                                         few(missing), lacks))
if not n_gaps:
	check.append("Regions missing a stage or overlay: none")

# channels inside multi-channel stage images (first file of each stage)
STAGE_NCH = {}
for st in STAGES:
	kf = k0 if k0 in st["index"] else sorted(st["index"].keys())[0]
	path = os.path.join(st["dir"], st["index"][kf])
	take = st["channel_for"].get(kf, st["channel"]) or 1
	line, w, nch = channel_summary(st["label"], path, take)
	STAGE_NCH[st["dirvar"]] = nch
	check.append(line)
	if w:
		warns.append(w)

# do the stages of one region name the same channel (_C<n> in the name)?
odd = []
for k in keys:
	seen = []
	for st in STAGES:
		fname = st["index"].get(k)
		if fname is None:
			continue
		tag = channel_tag(fname)
		if tag is not None:
			seen.append((tag, "%s file %s is named _C%d" % (st["label"], fname, tag)))
		elif st["dirvar"] != "probDir" and STAGE_NCH.get(st["dirvar"], 0) > 1:
			# A probability channel is an ilastik class: not compared.
			take = st["channel_for"].get(k, st["channel"]) or 1
			seen.append((take, "%s shows channel %d of %s"
			             % (st["label"], take, fname)))
	if len(set([t for t, _d in seen])) > 1:
		odd.append((k, seen))
if odd:
	warns.append("!In %d region(s) the stages seem to come from different "
	             "channels, e.g. %s: %s. Check 'Channel to take from "
	             "multi-channel RAW' and the raw name filter."
	             % (len(odd), display_key.get(odd[0][0]) or odd[0][0],
	                "; ".join(one_per_channel(odd[0][1]))))

# probability maps older than the images they should be made from
by_var = dict((st["dirvar"], st) for st in STAGES)
if "bgsubDir" in by_var and "probDir" in by_var:
	bg, pr = by_var["bgsubDir"], by_var["probDir"]
	older = []
	for k in keys:
		if k in bg["index"] and k in pr["index"]:
			try:
				tb = os.path.getmtime(os.path.join(bg["dir"], bg["index"][k]))
				tp = os.path.getmtime(os.path.join(pr["dir"], pr["index"][k]))
			except OSError:
				continue
			if tp + 1.0 < tb:
				older.append(display_key.get(k) or k)
	if older:
		warns.append("!%d probability map(s) are older than the matching "
		             "background-subtracted image (%s). They may have been "
		             "made from earlier images; if so, run ilastik again on "
		             "the current images." % (len(older), few(older)))

# folder fields that point at another stage's folder, or repeat a folder
fields = []
for var, field, expected in FOLDER_FIELDS:
	fields.append((field, given_path(globals().get(var)), expected))
warns.extend(folder_name_warnings(fields))
warns.extend(same_path_warnings(fields))

if SLIDE_WARNING:
	if "region (MBF)" in SLIDE_WARNING[0]:
		warns.append("!The input folders come from different region (MBF) "
		             "folders of one slide (listed in the Log). Files pair by "
		             "RegionXXXX only, so folders from two regions would pair "
		             "without any error.")
	else:
		warns.append("!The input folders do not all come from the same slide "
		             "folder (listed in the Log). Files pair by RegionXXXX only, "
		             "so folders from two slides would pair without any error.")

# composites already in the output folder
if saveComposites:
	existing = [k for k in keys
	            if os.path.exists(os.path.join(OUT_DIR, out_stem.get(k, k)
	                                           + OUTPUT_SUFFIX + ".tif"))]
	if existing and not overwrite:
		warns.append("!%d of the %d composite(s) already exist in the output "
		             "folder and will NOT be replaced ('Overwrite existing "
		             "composites' is off)." % (len(existing), len(keys)))
	elif existing:
		check.append("%d existing composite(s) will be replaced (overwrite "
		             "is on)." % len(existing))

check.append("Display mode: %s;  ROIs loaded as: %s" % (displayMode, roiLoadMode))
check.append("Bit depth: %s;  stages of a different size: %s"
             % (TARGET_DEPTH, ON_SIZE_MISMATCH))
if show_windows:
	opened_text = "yes"
elif showComposites:
	opened_text = "no (more than MAX_WINDOWS = %d regions)" % MAX_WINDOWS
else:
	opened_text = "no"
check.append("Open on screen: %s;  save to disk: %s;  overwrite existing: %s"
             % (opened_text, "yes" if saveComposites else "no",
                "yes" if overwrite else "no"))
check.append("Output folder: %s%s" % (OUT_DIR, "" if saveComposites
                                      else "  (parameter record only)"))

if not confirm_settings(SCRIPT_NAME, experiment_lines(globals().get("_SLIDE") or first_dir) + warns + check, CONFIRM_BEFORE_RUN):
	IJ.log("%s: cancelled at the settings check; nothing was processed."
	       % SCRIPT_NAME)
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
		notes, info = [], []     # flagged in the summary / logged only
		comp = None
		comp_shown = False
		try:
			loaded = []
			for st in STAGES:
				fname = st["index"].get(key)
				if fname is None:
					notes.append("stage '%s' has no file for this section"
					             % st["label"])
					continue
				try:
					im, cal = open_stage_image(os.path.join(st["dir"], fname),
					                           st["channel_for"].get(
					                               key, st["channel"]))
				except StepError, e:
					notes.append("stage '%s' could not be opened: %s"
					             % (st["label"], str(e)))
					continue
				opened.append(im)
				loaded.append({"label": st["label"], "imp": im, "file": fname,
				               "dirvar": st["dirvar"], "cal": cal})

			if not loaded:
				raise StepError("no stage produced a usable image for this "
				                "section.")

			ref_w = loaded[0]["imp"].getWidth()
			ref_h = loaded[0]["imp"].getHeight()
			present = [L["dirvar"] for L in loaded]
			keep = []
			changed = {}    # dirvar -> label, dropped or scaled
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
				changed[L["dirvar"]] = L["label"]
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

			stack = ImageStack(ref_w, ref_h)
			ranges = []
			for L in loaded:
				st_ = L["imp"].getStatistics(Measurements.MIN_MAX)
				lo, hi = st_.min, st_.max
				if hi <= lo:
					hi = lo + 1
				ranges.append((lo, hi))
				stack.addSlice(L["label"], L["imp"].getProcessor())

			comp_imp = ImagePlus(out_stem.get(key, dk) + OUTPUT_SUFFIX, stack)
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

			comp.setCalibration(loaded[0]["cal"])

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

			if ov.size() > 0 and (LOAD_OVERLAY or SAVE_OVERLAY_IN_FILE):
				comp.setOverlay(ov)

			saved = "no"
			if saveComposites:
				IJ.showStatus("[%d/%d] %s - saving" % (i + 1, len(keys), dk))
				opath = os.path.join(OUT_DIR, out_stem.get(key, dk)
				                     + OUTPUT_SUFFIX + ".tif")
				if os.path.exists(opath) and not overwrite:
					notes.append("output already existed; not overwritten "
					             "(tick 'Overwrite existing composites' to "
					             "replace it)")
				else:
					if IJ.saveAsTiff(comp, opath):
						saved = "yes"
					else:
						notes.append("the composite could not be saved to %s"
						             % opath)

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
			else:
				if LOAD_MANAGER and ov.size() > 0 and showComposites:
					notes.append("composite not opened (MAX_WINDOWS), so its "
					             "ROIs were not loaded into the ROI Manager")

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
	log_path = os.path.join(OUT_DIR, "_composite_log.csv")
	if os.path.exists(log_path) and not overwrite:
		IJ.log("Debug log NOT saved - the file already exists (tick "
		       "'Overwrite existing composites' to replace it): %s" % log_path)
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
	    ("Folder of raw .tif images (tifs/)", shown(rawDir)),
	    ("Only use raw images whose name contains (blank = all; e.g. _C2)",
	     RAW_NAME_FILTER),
	    ("Folder of background-subtracted images (processed_bgsub_cleared/)", shown(bgsubDir)),
	    ("Folder of ilastik probabilities (probabilities/)", shown(probDir)),
	    ("Folder of thresholded masks (particle_counts/thresholded/)", shown(threshDir)),
	    ("Folder of particle ROIs to overlay (particle_counts/particle_rois/)", shown(particleDir)),
	    ("Folder of anatomical ROIs to overlay (rois/)", shown(anatDir)),
	    ("Channel to take from multi-channel RAW", rawChannel),
	    ("Channel to take from multi-channel PROBABILITIES", probChannel),
	    ("Display mode", displayMode),
	    ("Load ROIs as", roiLoadMode),
	    ("Output location (blank = one level above the input)", shown(outParentDir)),
	    ("Name for the new output folder", outFolderName),
	    ("Open the composites on screen", showComposites),
	    ("Save the composites to disk", saveComposites),
	    ("Overwrite existing composites", overwrite),
	    ("Write a debug log CSV", writeLog),
	    ("#Configuration", ""),
	    ("STAGE_ORDER", STAGE_ORDER),
	    ("KEY_PATTERN", KEY_PATTERN),
	    ("CASE_INSENSITIVE_KEYS", CASE_INSENSITIVE_KEYS),
	    ("REQUIRE_IN_NAME", repr(REQUIRE_IN_NAME)),
	    ("EXCLUDE_IN_NAME", repr(EXCLUDE_IN_NAME)),
	    ("TIF_EXTENSIONS", TIF_EXTENSIONS),
	    ("TARGET_DEPTH", TARGET_DEPTH),
	    ("ON_SIZE_MISMATCH", ON_SIZE_MISMATCH),
	    ("PREFER_INDIVIDUAL_PARTICLES", PREFER_INDIVIDUAL_PARTICLES),
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
	    ("MAX_WINDOWS", MAX_WINDOWS),
	    ("CONFIRM_BEFORE_RUN", CONFIRM_BEFORE_RUN),
	    ("#Inputs", ""),
	]
	for k, line in enumerate(auto_choices):
		items.append(("automatic choice %d" % (k + 1), line))
	for st in STAGES:
		items.append(("stage %s" % st["label"], st["dir"]))
	items.append(("particle ROI folder", PARTICLE_DIR or
	              ("(not found, left out: %s)" % PARTICLE_MISSING
	               if PARTICLE_MISSING else "(none)")))
	items.append(("anatomical ROI folder", ANAT_DIR or "(none)"))
	items.append(("output folder", OUT_DIR))
	record_path = write_run_record(OUT_DIR, SCRIPT_NAME, SCRIPT_VERSION, items)
	if record_path:
		IJ.log("Parameter record: %s" % record_path)


# ---------------------------------------------------- completion notice
IJ.log("-" * 64)
summary = ["Composites built : %d" % len(built)]
if noted:
	summary.append("With notes       : %d  (see Log)" % len(noted))
if failed:
	summary.append("Failed           : %d  (see Log)" % len(failed))
if n_setup_warnings:
	summary.append("Setup warnings   : %d  (see Log)" % n_setup_warnings)
summary.append("Channels          : %s"
               % ", ".join([st["label"] for st in STAGES]))
for line in summary:
	IJ.log(line)
IJ.log("-" * 64)
IJ.beep()

body = ["Finished %d section(s)." % len(keys), ""]
body.extend(summary)
if show_windows and built:
	body.append("")
	body.append("Scroll the channel slider (the 'c' bar) to move through "
	            "the pipeline stages.")
elif built and not show_windows:
	body.append("")
	body.append("Composites were saved rather than opened.")
if PARTICLE_MISSING:
	body.append("")
	body.append("No particle overlay: the particle ROI folder does not exist "
	            "(stage 3 writes particle_rois/ only when 'Export particle "
	            "ROIs' is not 'Nothing'):")
	body.append("   " + PARTICLE_MISSING)
if OUT_DIR and saveComposites:
	body.append("")
	body.append("Output: " + OUT_DIR)
elif OUT_DIR:
	body.append("")
	body.append("'Save the composites to disk' was off: only the parameter "
	            "record was written, in " + OUT_DIR)
if record_path:
	body.append("Parameter record: " + record_path)
if log_path:
	body.append("")
	body.append("Log: " + log_path)
if SLIDE_WARNING:
	body.append("")
	body.append("WARNING: " + SLIDE_WARNING[0])
	body.extend(SLIDE_WARNING[1:])
if failed or noted or n_setup_warnings or SLIDE_WARNING:
	body.append("")
	body.append("Check the Log window for details.")
if failed:
	title = "Composites complete - with failures"
elif noted or n_setup_warnings or SLIDE_WARNING:
	title = "Composites complete - with problems"
else:
	title = "Composites complete"
IJ.log(title)
IJ.showMessage(title, "\n".join(body))
