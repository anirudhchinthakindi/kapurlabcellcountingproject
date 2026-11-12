# Kapur Lab Cell Counting

Fiji (ImageJ) scripts that count labelled cells in brain sections, region by
region. The sections are registered to the atlas in NeuroInfo, and the scripts
take it from there: they convert the microscope files, turn NeuroInfo's region
outlines into ImageJ ROIs, prepare the images for ilastik, run the trained
ilastik classifier, and count the cells inside each region. The result for
each slide is a CSV table with one row per section and one column per brain
region.

## What is in this folder

| Item | What it is |
| --- | --- |
| `Kapur Lab Cell Counting/` | The scripts. This folder is what you copy into Fiji. |
| `Kapur Lab Cell Counting/Batch/` | One script per stage, each processing every section of one slide. |
| `Kapur Lab Cell Counting/Single Image/` | The same stages for one section, for trying settings. |
| `Kapur Lab Cell Counting/*.py` | Four tools: Set Up Slide Folders, Map Experiment Folders, Tune Counting Parameters and Run Stages for an Animal. |
| `Cell Count Pipeline Protocol.docx` | The lab protocol, step by step, from imaging to counts. |
| `Kapur Lab Cell Counting Script Reference.docx` | Every script in detail: dialog fields, settings, outputs and messages. |

The protocol tells you what to do and in which order. The script reference
is where to look up what a field means or why a message appeared.

## Installing

1. Install Fiji from https://imagej.net/software/fiji/downloads. Unzip it to a
   folder you can write to (on Windows, not inside Program Files; for example
   `C:\Users\<you>\Fiji`). The unzipped folder is called `Fiji` (`Fiji.app`
   in older downloads).
2. Quit Fiji. Copy the whole `Kapur Lab Cell Counting` folder into Fiji's
   `scripts/Plugins/` folder (`Fiji\scripts\Plugins\` on Windows). Make sure
   it did not end up inside a second folder of the same name.
3. Start Fiji. The scripts are under Plugins > Kapur Lab Cell Counting:
   the four tools, then the submenus Batch and Single Image.
4. For stage 2c and for training, install ilastik from https://www.ilastik.org.
   Use one ilastik version for a whole experiment.

To update, quit Fiji, delete the old `Kapur Lab Cell Counting` folder in
`scripts/Plugins/`, and copy in the new one. Copying over the old
folder leaves renamed scripts behind, and the menu then shows both versions.

The scripts are tested outside the Fiji app, with a stand-in for ilastik: on
Linux with ImageJ 1.54f and Bio-Formats 7.3.0, and with the jars of the
current Fiji download (ImageJ 1.54p, Bio-Formats 8.5.0, Jython 2.7.4); and
under Wine, which behaves like Windows, with that download's own Windows
Java. They have not been run on a Windows PC.

## On Windows

- 2c finds ilastik by itself when it is installed in
  `C:\Program Files\ilastik-<version>\` (also on D:, in your user's
  `AppData\Local\Programs`, or as `C:\ilastik-<version>`). Elsewhere, fill
  in "ilastik program" with the path of `ilastik.exe`.
- Windows locks a file that is open in Excel. Close a results table or
  `experiment_layout.csv` there before a script writes it; a script that
  finds one locked says so.
- Keep the experiment folder near the top of a drive (for example
  `D:\Data\<experiment>`). ilastik cannot open paths of 260 characters or
  more unless long paths are turned on in Windows, and 2c warns when a path
  is that long.
- The scripts were not tested with network paths of the form
  `\\server\share\...`. If the data is on a server, map the share to a
  drive letter and choose the folders through that letter.
- If you get the scripts with Git, the repository's `.gitattributes` keeps
  their Unix line ends. Scripts with Windows line ends (CR LF) work too.

## The stages

| Stage | Script | What it does |
| --- | --- | --- |
| (NeuroInfo) | outside Fiji | Registers each section to the atlas and exports the region outlines as XML. |
| 1 | Convert to Tif | `.ims` or `.nd2` files to TIFF, with a z-projection and the channels you choose. |
| 2a | NeuroInfo XML to ROI | The XML outlines to ImageJ ROI sets. "Separate brain regions" gives one ROI per region and side, so each region is counted on its own. |
| 2a.i | Review and Edit ROIs | Optional. Correct outlines by hand, with every channel shown in colour. |
| 2b | BG Subtract and Clear | Background subtraction, then everything outside the tissue set to black. These are the images ilastik sees. |
| (ilastik) | outside Fiji | Train the pixel classifier on a few images and save the project. |
| 2c | Run ilastik Headless | Runs the trained classifier on every image from Fiji. Optional: ilastik's own batch window does the same. |
| 3 | Count Particles per ROI | Thresholds the probability maps and counts the cells in each region. |
| 4 | Build Pipeline Composite | Optional. Stacks each section's stages with the ROIs and counted cells, for checking. |
| 0 | Optimize Parameters | Optional. Tries a range of values for one setting, side by side. |

Tune Counting Parameters is another way to choose the counting settings: you
count cells by hand on a few sections without seeing the script's result, and
it picks the settings that agree best with your counts.

## How the folders are laid out

The scripts find their inputs from the slide folder, so the folder names
matter. Set Up Slide Folders makes this layout for you:

```
Experiment/
  experiment_layout.csv              table of every slide (Map Experiment Folders)
  day 1/
    vehicle/
      A2F/                           one animal
        A2F_project.ilp              optional: one ilastik project for the animal
        slide1/                      one slide
          tifs/                      converted images (stage 1)
          jpx/                       NeuroInfo files
          hippocampus MBF/           one region folder per analysed region
            xml/                     NeuroInfo exports
            rois/                    ROI sets (2a)
            processed_bgsub_cleared/ images for ilastik (2b)
            probabilities/           ilastik maps (2c or ilastik)
            particle_counts/         counts (stage 3)
```

A region folder is recognised by the word MBF in its name. One region folder
can hold several regions: name it for example `somatosensory hippocampus
striatum MBF`, export all their outlines from NeuroInfo into its `xml/`, and
use 2a's "Separate brain regions" to count each region separately. A section
that lacks one of the regions gets `NA` for it.

The raw `.ims` / `.nd2` files can sit in the slide folders or in a separate
folder tree that repeats the same names, with the raw files directly in each
slide folder there:

```
Raw data/
  Experiment/day 1/vehicle/A2F/slide1/*.ims
```

Give that tree's top folder as "Raw data top folder" in Set Up Slide Folders,
1 Convert to Tif, 2a.i Review and Run Stages for an Animal. The slide folders
then hold only analysis files. A slide's raw folder is found by its path, and
the animal folder above it must match, so another animal's slide of the same
name is never used.

## Running one slide

Each Batch script asks for the slide folder and the region (for example
`hippocampus`). It finds its input folders, shows them for checking, and
lists everything it will do in a Check settings window before anything
changes. Click Run to start.

## Running every slide of an animal

Run Stages for an Animal runs the Batch stages you tick (1, 2a, 2b, 2c, 3
and 4) on every slide of one animal, one slide after another, with one set of
settings for all of them. Each slide is processed as if you had run the stage
on it yourself: its files go into its own folders and its counts stay its own.
Slides of different animals are never run together.

- Each stage asks for its settings once. For 2c you choose the animal's
  ilastik project (an `.ilp` in the animal folder) or each slide's own.
- The Check settings window lists every slide and what will run on it. A slide
  that lacks a stage's input is skipped for that stage, with the reason.
- The run breaks where a step needs you, after every slide has reached it:
  before 2b to review the ROIs (it can open 2a.i on each slide in turn),
  before 2c to train ilastik, and before 3 for Tune if stage 3 should use
  tuned values and none exist yet. The window stays open while you work.
  Press Continue when the step is done, or Stop here to finish another day:
  the next run on that animal and region offers to continue with the same
  settings and the same ilastik project, and slides that finished a stage do
  not repeat it.
- If a stage fails on a slide, the later stages skip that slide and the other
  slides carry on. Esc stops the run once the stage that is running has
  finished.
- Each slide's region folder gets a record saying it was run as part of the
  whole animal. After stage 3, the animal folder also gets
  `particle_counts_all_slides_<region>.csv`, which lists the slides' tables
  one after the other (in a continued run, also those of the slides counted
  before the pause).

A first pass on a new animal goes:

1. Set Up Slide Folders on the experiment (with the raw data top folder, if
   the raw files are kept elsewhere).
2. NeuroInfo on each slide, exporting the XML into each slide's
   `<region> MBF/xml/`.
3. Run Stages for an Animal with every stage ticked. At the ilastik break,
   train one project on images from several of the animal's slides and save
   it in the animal folder.

Tune draws sections from the whole experiment, and stage 3 uses its values
for every animal. If only this animal has probability maps when the run
reaches the Tune break, stop there, make the other animals' maps, run Tune,
and then continue each animal's run.

## The results

- `particle_counts.csv` (in `particle_counts/`): one row per section, one
  column per region ROI. `NA` means that region is not in that section.
- `particle_counts_by_region.csv`: one row per region ROI of each section
  (a region counted per side has a row for each side), with the count, the
  region's area and the cells per mm2.
- Every run writes a parameter record, `_run_<script>_<time>.txt`, next to its
  outputs, with every setting it used.
- Tune Counting Parameters saves its results in `counting_tuning/` in the
  experiment folder. Stage 3 looks for the tuned values there.

## For maintainers

Each script is a single file, so nothing else needs installing. Helper code
that several scripts use is pasted into each of them and must stay identical
in every copy. Fiji cannot open a script of 100,000 characters or more, so
each script is kept under 95,000, which leaves room for Windows line ends.
The scripts are Jython 2.7 (Python 2 syntax) and pure ASCII. A file a script
reads is closed at once (with `with`, or read and closed in a helper): Jython
closes files only when it collects them, and on Windows an open file cannot
be renamed or removed. `tests/run_all.sh` runs the test suites; Appendix A
of the script reference has the details.
