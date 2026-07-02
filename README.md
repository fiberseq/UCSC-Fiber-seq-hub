# UCSC-Fiber-seq-hub

A [UCSC Track Hub](https://genome.ucsc.edu/goldenPath/help/hgTrackHubHelp.html)
for hg38 exposing [FIRE](https://github.com/fiberseq/FIRE) (Fiber-seq Inferred
Regulatory Elements) chromatin accessibility and peak calls across a
compendium of cell lines and tissues.

Hub URL: `https://fiberseq.github.io/UCSC-Fiber-seq-hub/hub.txt`

Load it via **My Data → Track Hubs → My Hubs**, or append
`&hubUrl=<hub URL>` to any `hgTracks` URL (add `&udcTimeout=1` while iterating).

## Tracks

Both are grouped under "Regulation" (next to ENCODE cCREs/H3K27Ac) and each
has its own description page.

- **Fiber-seq Accessibility** (on by default): percent-accessible chromatin
  for the 7 default cell lines, overlaid as semi-transparent bars in a
  colorblind-safe palette.
- **Fiber-seq Compendium**: every sample × 4 file types (percent accessible
  all/hap1/hap2, peaks) as an ENCODE-style composite matrix. Hidden overall
  by default; an enabled subtrack renders `dense`. Filter by *Cell Type*, then
  click the *Sample* or *Track Type* column header to group either way.

Raw bigWig/bigBed files live on Kopah S3 as per-sample hubs; this repo only
builds the merged `hub.txt`/`genomes.txt`/`trackDb.txt` pointing at them. No
sequencing data is stored here.

## Build

The [tracking sheet](https://docs.google.com/spreadsheets/d/e/2PACX-1vTmfYPsh-QeNk7gwcw1IYQUaHGSChoKlbLVon7imcSzEI3mzVCv78HPzjaPb_TK3HDUhiTFBEijXP6W/pub?output=csv)
is the master sample list. `scripts/build_hub.py` (stdlib-only) fetches it
live, templates each sample's file URLs, HEAD-checks them, and drops any
unreachable file rather than shipping a broken link. A row is included once it
has a name, tissue, and working "total % accessible" link. Only the sheet's
first published tab is read, so rows parked in an `unused` tab are ignored.

```bash
pixi install            # one-time
pixi run build          # regenerate hub/ from the sheet
pixi run validate       # rebuild + hubCheck -noTracks (run before pushing)
pixi run validate-full  # also re-fetches every bigWig/bigBed
```

Everything under `hub/` is committed and is exactly what deploys to GitHub
Pages: `hub.txt`, `genomes.txt`, `hg38/trackDb.txt`, the two description
pages, and `samples.tsv` — a machine-parseable manifest of what shipped (one
row per sample; columns for name, PS ID, tissue, default flag, and each track
type's data-file URL), served at `.../samples.tsv`. `genomes.txt` stamps the
trackDb URL with a content hash (`trackDb.txt?v=<hash>`) so UCSC can't get
stuck on a stale cached copy.

To add a sample: fill in its name, tissue, and links in the sheet, then
`pixi run validate` and commit the `hub/` changes.

CI runs the fast `-noTracks` check on every push and before deploy. **Before
submitting to UCSC**, switch `deploy.yml` to the full `-udcDir` check (see the
TODO there) so a broken data link can't go live.

## Submitting to UCSC

Once `hub/` passes `hubCheck` and is spot-checked in the browser, email
`genome@soe.ucsc.edu` with the hub.txt URL, a short description, and the
citation, per the
[Public Hub Guidelines](https://genome.ucsc.edu/goldenPath/help/publicHubGuidelines.html).

## Citation

Vollger, M. R.\*†, Swanson, E. G.\*, Neph, S. J., et al., Stergachis, A. B.†
(2026). Somatic epimutations cap genetic determinism in the human diploid
chromatin epigenome. *Cell*, in press.
[Preprint](https://doi.org/10.1101/2024.06.14.599122)

Fiber-seq method: Stergachis, A. B., et al. (2020). Single-molecule regulatory
architectures captured by chromatin fiber sequencing. *Science*
368(6498):1449–1454. https://doi.org/10.1126/science.aaz1646

## Contact

Vollger Lab, University of Utah (mrvollger@genetics.utah.edu) ·
Stergachis Lab, University of Washington (absterga@uw.edu)
