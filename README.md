# UCSC-Fiber-seq-hub

A [UCSC Track Hub](https://genome.ucsc.edu/goldenPath/help/hgTrackHubHelp.html)
for hg38 exposing [FIRE](https://github.com/fiberseq/FIRE) (Fiber-seq
Inferred Regulatory Elements) chromatin accessibility and regulatory element
calls across a compendium of cell lines and tissues.

Hub URL (once deployed): `https://fiberseq.github.io/UCSC-Fiber-seq-hub/hub.txt`

Load it in the UCSC Genome Browser via **My Data → Track Hubs → My Hubs**,
or append `&hubUrl=https://fiberseq.github.io/UCSC-Fiber-seq-hub/hub.txt`
to any `hgTracks` URL.

## What's in the hub

- **FIRE Accessibility** (on by default): percent-accessible chromatin for a
  panel of commonly used cell lines, overlaid as semi-transparent lines in
  different colors.
- **FIRE Compendium**: every sample × the 4 file types the sheet links
  (percent accessible all/hap1/hap2, and FIRE peaks), organized as an
  ENCODE-style composite matrix. Use the *Cell Type* filter to narrow the
  sample list, then check boxes in the sample × track-type grid.

Each sample's raw bigWig/bigBed files live on Kopah S3
(`s3.kopah.uw.edu/.../hashed.PacBio-Fiber-seq/<PS-ID>/...`) as their own
independent per-sample track hubs — this repo only builds a merged
`hub.txt`/`genomes.txt`/`trackDb.txt` that points at them. No sequencing data
lives in this repo.

## Repo layout

- The [lab's tracking sheet](https://docs.google.com/spreadsheets/d/e/2PACX-1vTmfYPsh-QeNk7gwcw1IYQUaHGSChoKlbLVon7imcSzEI3mzVCv78HPzjaPb_TK3HDUhiTFBEijXP6W/pub?output=csv)
  is the master sample list — `scripts/build_hub.py` fetches it live on
  every run. A row is included once it has a sample name, a tissue, and a
  working "total percent accessible" link; incomplete rows (still being
  annotated) are silently skipped until they're filled in.
- `scripts/build_hub.py` — fetches the sheet and (re)writes `hub/`.
  Stdlib-only Python.
- `hub/` — the generated hub, committed to git (small text files only).
  This directory is exactly what gets deployed to GitHub Pages.
- `pixi.toml` — provides `hubCheck` (from bioconda) and the standard tasks
  below. Run `pixi install` once to set up.

## Regenerating the hub

```bash
pixi run build
```

This fetches the sheet, templates every included sample's file URLs,
HEAD-checks each one, and drops any track whose data file isn't reachable
(with a warning) rather than shipping a broken link. Commit the resulting
changes under `hub/`.

## Adding a sample

Fill in its name, tissue, and file links in the tracking sheet, then re-run
`pixi run validate` and commit the changes under `hub/`.

## Validating before merging

```bash
pixi run validate          # primary: rebuild + hubCheck -noTracks (structure only)
pixi run validate-full     # also re-fetches every bigWig/bigBed via hubCheck
```

`validate-full` is secondary — data-file reachability is already covered by
`build_hub.py`'s own URL check. CI (`.github/workflows/validate.yml`) runs
the full check on every PR and push to `main` as the authoritative gate;
`.github/workflows/deploy.yml` re-validates and then deploys `hub/` to
GitHub Pages. Both use the same `pixi.toml` environment as local dev.

## Submitting to UCSC

Once `hub/` passes `hubCheck` cleanly and has been spot-checked in the
browser, email `genome@soe.ucsc.edu` with the hub.txt URL, a short
description, and the citation below, per UCSC's
[Public Hub Guidelines](https://genome.ucsc.edu/goldenPath/help/publicHubGuidelines.html).
Whether it's loaded by default for hg38 is UCSC's call.

## Citation

Vollger, M. R.\*†, Swanson, E. G.\*, Neph, S. J., et al., Stergachis, A. B.†
(2026). Somatic epimutations cap genetic determinism in the human diploid
chromatin epigenome. *Cell*, in press.
[Preprint](https://doi.org/10.1101/2024.06.14.599122)

## Contact

- Mitchell R. Vollger, Vollger Lab, Department of Human Genetics, University
  of Utah — mrvollger@genetics.utah.edu
- Andrew B. Stergachis, Department of Genome Sciences, University of
  Washington — absterga@uw.edu
