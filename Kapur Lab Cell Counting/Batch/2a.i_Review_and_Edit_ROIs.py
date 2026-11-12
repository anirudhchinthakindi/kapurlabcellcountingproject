# 2a.i_Review_and_Edit_ROIs.py
#
# Fiji / ImageJ Jython script - Kapur Lab Cell Counting suite, step 2a
# (review). Shows each section's image with its ROI set so you can check
# the NeuroInfo outlines against the tissue and correct them by hand, then
# saves the corrected ROI set back to its .zip.
#
# Menu  : Plugins > Kapur Lab Cell Counting > Batch > 2a.i Review and Edit ROIs
# Reads : a folder of images (tifs/) and a folder of RoiSet .zip files
#         (rois/), paired by the leading RegionXXXX token, one section at a
#         time, in RegionXXXX order.
# Writes: the edited RoiSet .zip in place of the old one (only when you save
#         a section whose ROIs changed). The first time a .zip is replaced,
#         the original is kept as <rois folder>/_before_review/<name>.zip
#         (never overwritten later), so the NeuroInfo outlines can always be
#         restored. Every save adds rows to <rois folder>/_roi_review_log.csv
#         (one per ROI added, removed, renamed or reshaped, with its area in
#         pixels before and after), and every run writes a parameter record
#         _run_2a.i_Review_and_Edit_ROIs_<time>.txt in the rois folder.
#
# How to edit, while the review window is open (it does not block Fiji):
#   - Choose the ROI under "ROI to edit" in the review window, then press
#     "Reshape with the brush" (drag its edge out from inside or in from
#     outside; brush width BRUSH_SIZE), "Reshape by moving points" (the
#     outline becomes points POINT_SPACING pixels apart that you drag; Alt-
#     click removes one, Shift-click on the line adds one) or "Redraw it by
#     hand" (polygon tool), and then "Keep this shape". "Undo changes to this
#     ROI" restores the outline it had when the section opened. Editing in
#     the ROI Manager ("Update") still works; an outline changed on the image
#     but not kept is caught when you press OK.
#   - "Add [t]" adds the current selection as a new ROI; "Rename..." renames;
#     "Delete" removes. Stage 3 makes one CSV column per ROI name, so keep
#     the names consistent across sections.
#   - Then choose what to do in the review window and press OK.
#
# Every channel is shown overlaid in colour (SHOW_ALL_CHANNELS): the
# section's tifs/ files merged (one per channel), or its raw .nd2/.ims (z
# maximum projection) when tifs/ holds fewer channels, so the anatomy is
# visible. 'Channels on/off' turns channels on and off.
# The image is shown with automatic contrast for viewing only; the image
# file is never changed. ROIs keep the image's pixel coordinates, so the
# saved set lines up with every later stage (2b, 3, 4).
#
# After you change ROIs: run 2b again for the changed sections when you
# moved the outer edge of the tissue (2b clears everything outside the
# ROIs), then ilastik on any changed 2b output, then stage 3 (the counts
# depend on the ROI outlines). The completion message lists the sections
# you changed.
#
# Before it starts, the script shows a Check settings window listing the
# sections it found. Press Run to go ahead or Cancel to stop.
#
# Usage: Plugins > Kapur Lab Cell Counting > Batch > 2a.i Review and Edit
# ROIs, or open this file in the Script Editor (File > New >
# Script..., or Plugins > Scripting > Script Editor) with Language = Python
# (Jython) and press Run.

#@ File    (label="Slide folder (the scripts find its subfolders)", style="directory") slideDir
#@ String  (label="Region (its MBF folder; blank = choose from a list)", value="", required=false) regionName
#@ File    (label="Raw data top folder (the tree with the .nd2/.ims files that mirrors the slide folders; blank = in the slide folder)", style="directory", required=false) rawRoot
#@ String  (label="Only use images whose name contains (blank = all; e.g. _C2)", value="", required=false) nameFilter
#@ String  (label="Start at section (blank = first; e.g. Region0005)", value="", required=false) startAt

# =========================================================================
# ===  USER CONFIGURATION  ================================================
# =========================================================================
# Nothing below the END OF USER CONFIGURATION banner needs editing for
# routine use.

# ---- PAIRING ----
# Images and ROI sets pair by the leading RegionXXXX token of the name.
KEY_PATTERN = r"^(Region\d+)"
CASE_INSENSITIVE_KEYS = True
REQUIRE_IN_NAME = ""        # extra filters on image names (dialog filter too)
EXCLUDE_IN_NAME = ""
IMAGE_EXTENSIONS = [".tif", ".tiff"]

# ---- DISPLAY ----
AUTO_CONTRAST = True        # stretch the display (viewing only)
SHOW_LABELS = True          # ROI names on the image
BRUSH_SIZE = 30             # pixels; width of the reshaping brush
POINT_SPACING = 15          # pixels between points in "Reshape by moving points"
# Show every channel overlaid in colour, to see the anatomy: the section's
# tifs/ files merged (one file per channel), or its raw .nd2/.ims from nd2/,
# ims/ or the slide folder (z maximum projection) when that has more
# channels. False shows only the tif (as chosen).
SHOW_ALL_CHANNELS = True
# Colours for channels the file gives none (1st, 2nd, ...): ImageJ LUT names.
CHANNEL_COLORS = ["Green", "Red", "Blue", "Grays", "Cyan", "Magenta", "Yellow"]

# ---- SAVING ----
BACKUP_FOLDER_NAME = "_before_review"     # inside the rois folder
REVIEW_LOG_NAME = "_roi_review_log.csv"   # inside the rois folder
# The ROI Manager is cleared when the script starts and between sections.
# Set False to stop instead when it holds ROIs at the start.
CLEAR_ROI_MANAGER = True

# ---- SAFETY CHECKS ----
CONFIRM_BEFORE_RUN = True
WRITE_PARAMETER_RECORD = True

# =========================================================================
# ===  END OF USER CONFIGURATION  =========================================
# =========================================================================

SCRIPT_NAME = "2a.i_Review_and_Edit_ROIs"
SCRIPT_VERSION = "2.0"

import os
import re
import sys
import time
from ij import IJ, WindowManager
from ij.gui import NonBlockingGenericDialog, GenericDialog
from ij.plugin.frame import RoiManager
from java.awt.event import ActionListener, ItemListener
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


# ---------------------------------------------------------------- helpers
ACT_SAVE_NEXT = "Save changes, then go to the next section"
ACT_NEXT = "Go to the next section without saving"
ACT_BACK = "Go back to the previous section (unsaved changes are lost)"
ACT_SAVE_STOP = "Save changes, then stop"
ACT_STOP = "Stop without saving"


def geometry(roi):
	"""Comparable outline of an ROI: type plus its polygon coordinates."""
	try:
		fp = roi.getFloatPolygon()
		pts = tuple([(round(fp.xpoints[i], 3), round(fp.ypoints[i], 3))
		             for i in range(fp.npoints)])
	except (Exception, JavaException):
		b = roi.getBounds()
		pts = ((b.x, b.y, b.width, b.height),)
	return (roi.getType(), pts)


def manager():
	rm = RoiManager.getInstance()
	if rm is None:
		rm = RoiManager()
	return rm


def current_set(rm):
	"""[(name, Roi copy)] from the ROI Manager, in its order."""
	out = []
	for r in rm.getRoisAsArray():
		c = r.clone()
		c.setPosition(0)          # ROIs apply to every channel, as from 2a
		out.append((c.getName() or "roi", c))
	return out


def sync_image_selection(imp, rm):
	"""Offer to store an outline edited on the image but not 'Update'd."""
	roi = imp.getRoi() if imp is not None else None
	idx = rm.getSelectedIndex()
	if roi is None or idx < 0:
		return
	stored = rm.getRoi(idx)
	if stored is None or geometry(roi) == geometry(stored):
		return
	gd = GenericDialog("Unsaved outline")
	gd.addMessage("The outline on the image differs from the ROI Manager's "
	              "copy of '%s'.\nYou probably edited it without pressing "
	              "'Update'." % stored.getName())
	gd.enableYesNoCancel("Update it", "Keep the ROI Manager copy")
	gd.hideCancelButton()
	gd.showDialog()
	if gd.wasOKed():
		rm.select(imp, idx)
		imp.setRoi(roi)
		rm.runCommand(imp, "Update")


def compare(old, new):
	"""Rows describing what changed: (kind, name, area_before, area_after)."""
	rows = []
	oldd = dict(old)
	newd = dict(new)
	for n, r in old:
		if n not in newd:
			rows.append(("removed", n, roi_area_px(r), ""))
		elif geometry(r) != geometry(newd[n]):
			rows.append(("reshaped", n, roi_area_px(r), roi_area_px(newd[n])))
	for n, r in new:
		if n not in oldd:
			rows.append(("added", n, "", roi_area_px(r)))
	if not rows and [n for n, _r in old] != [n for n, _r in new]:
		rows.append(("reordered", "", "", ""))
	return rows


def duplicate_names(pairs):
	seen, dup = set(), []
	for n, _r in pairs:
		if n in seen and n not in dup:
			dup.append(n)
		seen.add(n)
	return dup


def save_set(zip_path, old, new, rows):
	"""Back up the original once, write the new set via a temp file."""
	folder = os.path.dirname(zip_path)
	bdir = os.path.join(folder, BACKUP_FOLDER_NAME)
	backup = os.path.join(bdir, os.path.basename(zip_path))
	if not os.path.exists(backup):
		if not os.path.isdir(bdir):
			os.makedirs(bdir)
		import shutil
		shutil.copy2(zip_path, backup)
	tmp = zip_path + ".saving"
	write_roiset(new, tmp)
	check = read_roiset(tmp)
	if len(check) != len(new):
		raise StepError("the saved file holds %d ROIs instead of %d; the "
		                "original was kept" % (len(check), len(new)))
	if os.path.exists(zip_path):
		os.remove(zip_path)
	os.rename(tmp, zip_path)
	log = os.path.join(folder, REVIEW_LOG_NAME)
	new_file = not os.path.exists(log)
	fh = open(log, "a")
	try:
		if new_file:
			fh.write("time,roi_file,change,roi_name,area_px_before,area_px_after\n")
		stamp = time.strftime("%Y-%m-%d %H:%M:%S")
		for kind, name, a, b in rows:
			fh.write('%s,"%s",%s,"%s",%s,%s\n'
			         % (stamp, os.path.basename(zip_path), kind,
			            name.replace('"', '""'), a, b))
	finally:
		fh.close()
	return backup


RAW_DIRS = []               # nd2/, ims/ and the slide folder (slide-folder runs)


def chan_no(path):
	m = re.search(r"_C(\d+)\.tiff?$", path, re.I)
	return int(m.group(1)) if m else 0


def same_key_files(folder, k, exts):
	"""Files in folder with RegionXXXX key k and one of the extensions."""
	if not folder or not os.path.isdir(folder):
		return []
	return [os.path.join(folder, f) for f in sorted(os.listdir(folder))
	        if not f.startswith(".") and os.path.splitext(f)[1].lower() in exts
	        and key_from(f) == k]


def colour(imp, every=False):
	"""Several channels: shown overlaid, each in its colour (CHANNEL_COLORS
	for channels with no colour in the file, or for all when every)."""
	from ij import CompositeImage
	if imp.getNChannels() < 2:
		return imp
	if not imp.isComposite():
		imp = CompositeImage(imp, CompositeImage.COMPOSITE)
	imp.setMode(CompositeImage.COMPOSITE)
	for c in range(1, imp.getNChannels() + 1):
		lut = imp.getChannelLut(c)
		if every or lut.getRed(255) == lut.getGreen(255) == lut.getBlue(255):
			imp.setC(c)
			IJ.run(imp, CHANNEL_COLORS[(c - 1) % len(CHANNEL_COLORS)], "")
	imp.setC(1)
	return imp


def open_review_image(img_path):
	"""The section's image with every channel, in colour: the tif, merged
	with the section's other tifs/ files (one per channel), or the raw
	.nd2/.ims (z maximum projection) when that has more channels and the
	same size. Returns (imp, what is shown). The ROIs line up either way."""
	from ij import ImagePlus
	from ij.plugin import RGBStackMerge, ZProjector
	from java.lang import Throwable
	from jarray import array
	imp = bf_open(img_path)[0]
	shown = os.path.basename(img_path)
	k, merged = key_from(shown), False
	if not SHOW_ALL_CHANNELS or k is None:
		return imp, shown
	paths = same_key_files(os.path.dirname(img_path), k, IMAGE_EXTENSIONS)
	if len(paths) > 1 and imp.getNChannels() == 1:
		paths = sorted(paths, key=chan_no)
		imps = [imp if p == img_path else bf_open(p)[0] for p in paths]
		if all([(q.getWidth(), q.getHeight(), q.getBitDepth(), q.getStackSize())
		        == (imp.getWidth(), imp.getHeight(), imp.getBitDepth(), 1) for q in imps]):
			imp = RGBStackMerge.mergeChannels(array(imps, ImagePlus), False)
			shown = "%s (%d tifs/ files, one per channel)" % (shown, len(imps))
			merged = True
		else:
			for q in imps:
				if q is not imp:
					q.close()
	raw = None
	for d in RAW_DIRS:
		got = same_key_files(d, k, (".nd2", ".ims"))
		if got:
			raw = got[0]
			break
	if raw:
		try:
			r = bf_open(raw)[0]
			if r.getNChannels() > imp.getNChannels() and \
			        (r.getWidth(), r.getHeight()) == (imp.getWidth(), imp.getHeight()):
				if r.getNSlices() > 1:
					r2 = ZProjector.run(r, "max")
					r.close()
					r = r2
				imp.close()
				imp, merged = r, False
				shown = "%s (every channel, z maximum)" % os.path.basename(raw)
			else:
				if r.getNChannels() > imp.getNChannels():
					IJ.log("    %s is not the size of the tif; the tif is shown"
					       % os.path.basename(raw))
				r.close()
		except (Exception, JavaException, Throwable), e:
			IJ.log("    raw file %s not shown (%s); the tif is shown"
			       % (os.path.basename(raw), e))
	return colour(imp, merged), shown


def remove_old_review():
	"""Offer to delete the 2a Review scripts this one replaced (left behind
	when the new folder was copied over the old one)."""
	import glob
	base = os.path.join(IJ.getDirectory("imagej") or "", "scripts", "Plugins", "*")
	old = sorted(glob.glob(os.path.join(base, "Batch", "2a_Review_and_Edit_ROIs.py")) +
	             glob.glob(os.path.join(base, "Single*", "2a_Review_and_Edit_ROIs_(single).py")))
	if not old:
		return
	gd = GenericDialog(SCRIPT_NAME + " - old version")
	gd.addMessage("The old version of this script (2a Review and Edit ROIs) is still "
	              "installed:\n%s\n\nDelete it? It appears in the menu until Fiji "
	              "restarts." % "\n".join(old))
	gd.setOKLabel("Delete")
	gd.setCancelLabel("Keep")
	gd.showDialog()
	if gd.wasOKed():
		for p in old:
			try:
				os.remove(p)
				IJ.log("  deleted the old %s" % p)
			except OSError, e:
				IJ.log("  could not delete %s: %s" % (p, e))


def show_section(i, n, key, img_path, zip_path):
	"""Open the image and its ROIs. Returns (imp, original pairs)."""
	imp, shown = open_review_image(img_path)
	imp.setTitle("[%d/%d] %s" % (i + 1, n, os.path.basename(img_path)))
	IJ.log("  %s: showing %s" % (key, shown))
	if AUTO_CONTRAST:
		for c in range(1, imp.getNChannels() + 1):
			imp.setC(c)
			IJ.run(imp, "Enhance Contrast", "saturated=0.35")
		imp.setC(1)
	imp.show()
	rois = read_roiset(zip_path)
	rm = manager()
	rm.reset()
	original = []
	for name, roi in rois.items():
		roi.setPosition(0)
		rm.addRoi(roi.clone())
		original.append((name, roi))
	rm.runCommand("UseNames", "true")
	rm.runCommand(imp, "Show All with labels" if SHOW_LABELS else "Show All")
	return imp, original


def close_image(imp):
	if imp is not None:
		imp.changes = False
		imp.close()


class _Do(ActionListener, ItemListener):
	"""Runs fn for a button press or a list choice; errors go to the Log."""
	def __init__(self, fn):
		self.fn = fn

	def actionPerformed(self, e):
		self.run()

	def itemStateChanged(self, e):
		self.run()

	def run(self):
		try:
			self.fn()
		except (Exception, JavaException), ex:
			IJ.log("  ! ROI editing: %s" % ex)


def set_tool(name):
	try:
		IJ.setTool(name)
	except (Exception, JavaException):
		pass        # no ImageJ toolbar (headless)


def add_edit_tools(gd, imp, rm, original):
	"""The 'ROI to edit' list and the editing buttons of the review window.
	Returns the button actions by name (used by the automated tests)."""
	from ij.gui import Toolbar, PolygonRoi, Roi
	names = [r.getName() or "roi" for r in rm.getRoisAsArray()]
	if not names:
		return {}
	gd.addChoice("ROI to edit", names, names[0])
	choice = gd.getChoices()[-1]
	orig = dict(original)

	def idx():
		n = choice.getSelectedItem()
		now = [r.getName() for r in rm.getRoisAsArray()]
		return now.index(n) if n in now else -1

	def pick():
		i = idx()
		if i >= 0:
			rm.select(imp, i)
			IJ.showStatus("Editing '%s'" % choice.getSelectedItem())

	def brush():
		pick()
		Toolbar.setBrushSize(BRUSH_SIZE)
		set_tool("brush")
		IJ.showStatus("Brush: start inside the outline and drag to push it out; start "
		              "outside to cut it back. Then press 'Keep this shape'.")

	def points():
		pick()
		r = imp.getRoi()
		if r is None:
			return
		if r.getType() == Roi.COMPOSITE:
			IJ.showMessage("Reshape by moving points",
			               "'%s' is made of separate pieces, so it cannot become one "
			               "line of points. Use the brush instead." % choice.getSelectedItem())
			return
		fp = r.getInterpolatedPolygon(POINT_SPACING, True)
		if r.getFloatPolygon().npoints <= fp.npoints:
			fp = r.getFloatPolygon()            # already few points: keep them
		p = PolygonRoi(fp, Roi.POLYGON)
		imp.setRoi(p)
		set_tool("polygon")
		IJ.showStatus("Drag the points (zoom in with + to see them). Alt-click a point "
		              "to remove it; Shift-click on the line to add one. Then 'Keep this shape'.")

	def redraw():
		pick()
		imp.deleteRoi()
		set_tool("polygon")
		IJ.showStatus("Click around the new outline and double-click to close it. "
		              "Then press 'Keep this shape'.")

	def keep():
		i = idx()
		r = imp.getRoi()
		if i < 0 or r is None or not r.isArea():
			IJ.showMessage("Keep this shape", "Choose the ROI under 'ROI to edit' and "
			               "reshape or draw its outline on the image first.")
			return
		c = r.clone()
		c.setName(choice.getSelectedItem())
		c.setPosition(0)
		rm.setRoi(c, i)
		rm.runCommand(imp, "Show All with labels" if SHOW_LABELS else "Show All")
		rm.select(imp, i)
		IJ.log("    %s: new outline kept (written when you choose 'Save changes')"
		       % c.getName())

	def undo():
		i, name = idx(), choice.getSelectedItem()
		if i < 0 or name not in orig:
			return
		c = orig[name].clone()
		c.setPosition(0)
		rm.setRoi(c, i)
		rm.select(imp, i)
		IJ.log("    %s: original outline restored" % name)

	acts = [("Channels on/off", lambda: IJ.run("Channels Tool...")),
	        ("Reshape with the brush", brush), ("Reshape by moving points", points),
	        ("Redraw it by hand", redraw), ("Keep this shape", keep),
	        ("Undo changes to this ROI", undo)]
	choice.addItemListener(_Do(pick))
	for label, fn in acts:
		gd.addButton(label, _Do(fn))
	pick()
	out = dict(acts)
	out["choice"] = choice
	return out


def review(sections):
	"""Step through sections. Returns (saved keys, visited count, stopped)."""
	saved, problems = [], []
	i, visited = 0, 0
	n = len(sections)
	while 0 <= i < n:
		key, img_path, zip_path = sections[i]
		m = re.search(KEY_PATTERN, os.path.basename(img_path))
		key = m.group(1) if m else key          # as written in the file name
		IJ.showStatus("[%d/%d] %s - review" % (i + 1, n, key))
		imp = None
		try:
			try:
				imp, original = show_section(i, n, key, img_path, zip_path)
			except (StepError, Exception, JavaException), e:
				problems.append("%s: could not be opened (%s)" % (key, e))
				IJ.log("  %s: FAILED to open: %s" % (key, e))
				i += 1
				continue
			visited += 1
			rm = manager()
			while True:
				gd = NonBlockingGenericDialog("Review ROIs - [%d/%d] %s" % (i + 1, n, key))
				gd.addMessage("Image: %s\nROIs:  %s  (%d ROIs)\n\n"
				              "To change an outline: choose it under 'ROI to edit', then\n"
				              "  'Reshape with the brush' (drag its edge out or in),\n"
				              "  'Reshape by moving points' (drag points along the outline), or\n"
				              "  'Redraw it by hand' (click around the new outline),\n"
				              "and press 'Keep this shape'. 'Undo changes to this ROI' brings "
				              "back the outline it had\nwhen this section opened. Then choose "
				              "below and press OK. This window does not block Fiji."
				              % (os.path.basename(img_path), os.path.basename(zip_path),
				                 len(original)))
				tools = add_edit_tools(gd, imp, rm, original)
				acts = [ACT_SAVE_NEXT, ACT_NEXT, ACT_BACK, ACT_SAVE_STOP, ACT_STOP]
				if i == n - 1:
					acts = [ACT_SAVE_STOP, ACT_STOP, ACT_BACK]
				if i == 0:
					acts = [a for a in acts if a != ACT_BACK]
				gd.addRadioButtonGroup("Then:", acts, len(acts), 1, acts[0])
				gd.hideCancelButton()
				if "REVIEW_TEST_HOOK" in globals():     # automated tests only
					REVIEW_TEST_HOOK(imp, rm, tools)
				gd.showDialog()
				act = gd.getNextRadioButton()
				if act in (ACT_SAVE_NEXT, ACT_SAVE_STOP):
					sync_image_selection(imp, rm)
					new = current_set(rm)
					dup = duplicate_names(new)
					if dup:
						IJ.showMessage("Duplicate ROI names",
						               "Two ROIs share the name: %s\nStage 3 keys its "
						               "columns by name. Rename one, then press OK again."
						               % ", ".join(dup))
						continue
					if not new:
						IJ.showMessage("No ROIs", "The ROI Manager is empty, so there "
						               "is nothing to save. Undo the deletions or "
						               "choose to go on without saving.")
						continue
					rows = compare(original, new)
					if rows:
						try:
							save_set(zip_path, original, new, rows)
						except (StepError, Exception, JavaException), e:
							IJ.showMessage("Not saved", "%s could not be saved:\n%s\n"
							               "The original file is unchanged."
							               % (os.path.basename(zip_path), e))
							problems.append("%s: save failed (%s)" % (key, e))
							continue
						saved.append(key)
						kinds = {}
						for r in rows:
							kinds[r[0]] = kinds.get(r[0], 0) + 1
						IJ.log("  %s: saved (%s)" % (key, ", ".join(
						    ["%d %s" % (v, k) for k, v in sorted(kinds.items())])))
					else:
						IJ.log("  %s: no change, file left as it was" % key)
				else:
					IJ.log("  %s: %s" % (key, "left without saving" if act != ACT_BACK
					                     else "went back"))
				break
			if act in (ACT_SAVE_STOP, ACT_STOP):
				return saved, visited, problems, True
			i = i - 1 if act == ACT_BACK else i + 1
		finally:
			close_image(imp)
			try:
				manager().reset()
			except (Exception, JavaException):
				pass
	return saved, visited, problems, False


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
	RAW_DIRS = [layout_find(_SLIDE, _REGION, "nd2"), layout_find(_SLIDE, _REGION, "ims"), _SLIDE]
	_RAWT = globals().get("rawRoot") and layout_raw(_SLIDE, rawRoot.getAbsolutePath())
	if _RAWT:      # the raw files in their own tree
		RAW_DIRS = [os.path.join(_RAWT, "nd2"), os.path.join(_RAWT, "ims"), _RAWT] + RAW_DIRS
	_got = layout_confirm(SCRIPT_NAME + " - folders", _SLIDE, _REGION, [
	    ('Folder of raw .tif images (tifs/)', "dir", layout_find(_SLIDE, _REGION, "tifs"), None, True),
	    ('Folder of ROI .zip files (rois/)', "dir", layout_find(_SLIDE, _REGION, "rois"), None, True),
	])
	if _got is None:
		raise SystemExit
	tifDir = _F(_got[0]) if _got[0] else None
	roiDir = _F(_got[1]) if _got[1] else None


# ------------------------------------------------------------------ main
def main():
	remove_old_review()
	tif_dir = tifDir.getAbsolutePath()
	roi_folder = roiDir.getAbsolutePath()
	filt = (nameFilter or "").strip()
	start = (startAt or "").strip()
	for d, what in ((tif_dir, "image"), (roi_folder, "ROI")):
		if not os.path.isdir(d):
			IJ.error(SCRIPT_NAME, "The %s folder does not exist:\n%s" % (what, d))
			return
	imgs = {}
	for f in sorted(os.listdir(tif_dir)):
		if f.startswith(".") or os.path.splitext(f)[1].lower() not in IMAGE_EXTENSIONS:
			continue
		if (filt and filt not in f) or not name_allowed(f):
			continue
		k = key_from(f)
		if k is None:
			continue
		imgs.setdefault(k, f)     # several (one per channel): shown merged
	zips = {}
	for f in sorted(os.listdir(roi_folder)):
		if f.lower().endswith(".zip") and not f.startswith("."):
			k = key_from(f)
			if k is not None:
				zips[k] = f
	keys = sorted([k for k in imgs if k in zips])
	if start:
		sk = key_from(start) or (start.lower() if CASE_INSENSITIVE_KEYS else start)
		if sk not in keys:
			IJ.error(SCRIPT_NAME, "'%s' is not among the sections found: %s"
			         % (start, ", ".join(keys[:20])))
			return
		keys = keys[keys.index(sk):]
	if not keys:
		IJ.error(SCRIPT_NAME, "No image has a matching ROI set (pairing by "
		         "RegionXXXX).\nImages: %s\nROI folder: %s" % (tif_dir, roi_folder))
		return
	sections = [(k, os.path.join(tif_dir, imgs[k]), os.path.join(roi_folder, zips[k]))
	            for k in keys]
	no_roi = sorted([imgs[k] for k in imgs if k not in zips])
	no_img = sorted([zips[k] for k in zips if k not in imgs])
	lines = ["Images: %s" % tif_dir,
	         "ROI sets: %s" % roi_folder,
	         "Name filter: %s" % (filt or "none"),
	         "Sections to review: %d (%s ... %s)" % (len(sections), imgs[keys[0]], imgs[keys[-1]]),
	         "Edited sets are saved in place; originals go to %s/ once." % BACKUP_FOLDER_NAME,
	         "Shown: %s" % (("every channel in colour (tifs/ files merged, or the raw file "
	                         "from %s when it has more channels)" % (", ".join(
	                             [os.path.basename(d) + "/" for d in RAW_DIRS[:2]]) or "nd2/"))
	                        if SHOW_ALL_CHANNELS else "the tif only")]
	if no_roi:
		lines.append("Images without an ROI set (skipped): %d, e.g. %s"
		             % (len(no_roi), ", ".join(no_roi[:3])))
	if no_img:
		lines.append("! ROI sets without an image (skipped): %s"
		             % ", ".join(no_img[:5]))
	rm0 = RoiManager.getInstance()
	if rm0 is not None and rm0.getCount() > 0 and CLEAR_ROI_MANAGER:
		lines.append("! The ROI Manager holds %d ROI(s); they will be cleared."
		             % rm0.getCount())
	record_items = [("#Dialog", "")] + layout_record() + [
	                ("Folder of raw .tif images (tifs/)", tif_dir),
	                ("Folder of ROI .zip files (rois/)", roi_folder),
	                ("Only use images whose name contains (blank = all; e.g. _C2)", filt),
	                ("Start at section (blank = first; e.g. Region0005)", start),
	                ("Raw data top folder (the tree with the .nd2/.ims files that mirrors the slide folders; blank = in the slide folder)", globals().get("rawRoot") and rawRoot.getAbsolutePath() or "(blank)")]
	if not confirm_settings(SCRIPT_NAME, experiment_lines(globals().get("_SLIDE") or tif_dir) + lines, CONFIRM_BEFORE_RUN):
		IJ.log("%s: cancelled at the settings check; nothing was processed." % SCRIPT_NAME)
		return
	rm = RoiManager.getInstance()
	if rm is not None and rm.getCount() > 0 and not CLEAR_ROI_MANAGER:
		IJ.error(SCRIPT_NAME, "The ROI Manager holds ROIs. Save them, then "
		         "clear it (or set CLEAR_ROI_MANAGER = True).")
		return
	IJ.log("=" * 64)
	IJ.log("%s v%s" % (SCRIPT_NAME, SCRIPT_VERSION))
	for ln in lines:
		IJ.log("  " + ln)
	saved, visited, problems, stopped = review(sections)
	rec = None
	if WRITE_PARAMETER_RECORD:
		items = record_items + [
		    ("#Configuration", ""),
		    ("KEY_PATTERN", KEY_PATTERN), ("CASE_INSENSITIVE_KEYS", CASE_INSENSITIVE_KEYS),
		    ("REQUIRE_IN_NAME", REQUIRE_IN_NAME), ("EXCLUDE_IN_NAME", EXCLUDE_IN_NAME),
		    ("AUTO_CONTRAST", AUTO_CONTRAST), ("SHOW_ALL_CHANNELS", SHOW_ALL_CHANNELS),
		    ("CHANNEL_COLORS", ", ".join(CHANNEL_COLORS)), ("BACKUP_FOLDER_NAME", BACKUP_FOLDER_NAME),
		    ("REVIEW_LOG_NAME", REVIEW_LOG_NAME), ("CLEAR_ROI_MANAGER", CLEAR_ROI_MANAGER),
		    ("CONFIRM_BEFORE_RUN", CONFIRM_BEFORE_RUN),
		    ("#Result", ""),
		    ("sections reviewed", visited), ("sections saved", ", ".join(saved) or "none")]
		if problems:
			items += [("#Problems", "")] + [("%d" % (k + 1), p) for k, p in enumerate(problems)]
		rec = write_run_record(roi_folder, SCRIPT_NAME, SCRIPT_VERSION, items)
	body = "Sections reviewed: %d of %d\nSaved with changes: %s\n" % (
	    visited, len(sections), ", ".join(saved) or "none")
	if saved:
		body += ("\nOriginals kept in %s/ and every change listed in %s.\n"
		         "Run stage 3 again for these sections; run 2b (and ilastik) "
		         "again first if you moved the outer edge of the tissue.\n"
		         % (BACKUP_FOLDER_NAME, REVIEW_LOG_NAME))
	if problems:
		body += "\n%d problem(s); check the Log window.\n" % len(problems)
	if rec:
		body += "\nParameter record:\n%s" % rec
	IJ.beep()
	IJ.showMessage(SCRIPT_NAME + (" - with problems" if problems else ""), body)


main()
