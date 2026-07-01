#!/usr/bin/env python3
"""Generate the FIRE UCSC track hub (hub/) from the lab's live tracking sheet.

The published Google Sheet is the master sample list. This script fetches
it fresh, keeps only rows with a sample name, tissue, and a working
percent-accessible link (see SHEET_ROW_FILTER below), templates the URL for
each of the 4 file types the sheet links (total/hap1/hap2 percent-accessible
bigWig, peaks bigBed) from each row's base URL, checks that each URL is
actually reachable, and writes a single merged hub.txt / genomes.txt /
trackDb.txt that exposes:

  1. a default multiWig overlay of the "Default" samples' percent-accessible
     tracks (on by default), and
  2. an ENCODE-style compositeTrack matrix (dimX=sample, dimY=view,
     dimA=cell type) covering every sample x those 4 file types.

Run: python3 scripts/build_hub.py
"""

from __future__ import annotations

import csv
import io
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HUB_DIR = REPO_ROOT / "hub"

SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vTmfYPsh-QeNk7gwcw1IYQUaHGSChoKlbLVon7imcSzEI3mzVCv78HPzjaPb_TK3HDUhiTFBEijXP6W"
    "/pub?output=csv"
)

HUB_NAME = "FIRE-fiberseq"
CONTACT_EMAIL = "mrvollger@genetics.utah.edu"

# Okabe-Ito colorblind-safe palette, one color per default sample (stable order).
DEFAULT_PALETTE = [
    "230,159,0",    # orange
    "86,180,233",   # sky blue
    "0,158,115",    # bluish green
    "240,228,66",   # yellow
    "0,114,178",    # blue
    "213,94,0",     # vermillion
    "204,121,167",  # reddish purple
]


@dataclass(frozen=True)
class Sample:
    sample: str
    ps_id: str
    tissue: str
    default: bool
    base_url: str

    @property
    def cell_tag(self) -> str:
        return sanitize_tag(self.tissue)

    @property
    def sample_tag(self) -> str:
        return sanitize_tag(self.sample) + "_" + self.ps_id


def sanitize_tag(text: str) -> str:
    """UCSC subGroup tags must be alphanumeric/underscore only."""
    tag = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return tag or "unknown"


def sanitize_title(text: str) -> str:
    """UCSC subGroup mTitle values are underscore-joined words with no other
    punctuation (the browser swaps '_' back to spaces for display) -- sheet
    tissue names like "Lymphoblastoid (B-lymphocyte, EBV-transformed)" have
    parens/commas that silently break the composite's filter-by dropdown if
    left in, so strip everything but alnum/hyphen/underscore."""
    title = re.sub(r"[^A-Za-z0-9\-]+", "_", text).strip("_")
    return title or "unknown"


def trunc(text: str, limit: int) -> str:
    """ASCII-only truncation (UCSC labels should stay plain ASCII)."""
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def fetch_sheet_csv(url: str = SHEET_CSV_URL) -> str:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read().decode("utf-8")


def load_samples(csv_text: str) -> list[Sample]:
    """Parse the published sheet, keeping only rows ready for v1: a sample
    name, a tissue, and a working 'total percent accessible' link. Rows
    missing any of those (mostly samples still being annotated, or HPRC
    samples with no data yet) are silently skipped -- add data/tissue in the
    sheet to bring a sample in on the next build."""
    samples = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        row = {k.strip(): v.strip() for k, v in row.items() if k}
        sample = row.get("Sample", "")
        ps_id = row.get("PS", "")
        tissue = row.get("Tissue/Cell type", "")
        link = row.get("Link to total % accessible", "")
        if not (sample and tissue and link):
            continue
        base_url = link.rsplit("/bw/", 1)[0].rstrip("/")
        samples.append(
            Sample(
                sample=sample,
                ps_id=ps_id,
                tissue=tissue,
                default=row.get("Default % accessible track (limited to 7)", "").upper() == "TRUE",
                base_url=base_url,
            )
        )
    return samples


def check_url(url: str) -> tuple[str, bool]:
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return url, 200 <= resp.status < 300
    except Exception:
        return url, False


def check_urls(urls: list[str]) -> set[str]:
    """Return the subset of urls that are NOT reachable."""
    bad = set()
    with ThreadPoolExecutor(max_workers=16) as pool:
        for url, ok in pool.map(check_url, urls):
            if not ok:
                bad.add(url)
    return bad


# ---------------------------------------------------------------------------
# trackDb generation
# ---------------------------------------------------------------------------

# Simple views: one leaf bigWig/bigBed track per sample, keyed by file suffix.
# Kept to exactly the file types the sheet links -- not the full per-sample
# hub's file set. Percent-accessible (all/hap1/hap2) is handled separately
# below as one combined multiWig view rather than 3 separate rows.
SIMPLE_VIEWS = [
    # tag,      label,     file suffix,          type,             extra settings
    ("PEAKS", "Peaks", "bb/fire-peaks.bb", "bigNarrowPeak", {}),
]

# Percent-accessible view: one matrix cell per sample, each a multiWig
# overlay of all/hap1/hap2 in the hub's standard haplotype colors (hap1 =
# blue, hap2 = red, all = black), matching the default track's own style.
ACCESSIBILITY_SUBTRACKS = [
    ("all", "bw/all.percent.accessible.bw", "0,0,0"),
    ("hap1", "bw/hap1.percent.accessible.bw", "0,0,255"),
    ("hap2", "bw/hap2.percent.accessible.bw", "255,0,0"),
]


def stanza(**kwargs) -> str:
    lines = []
    for key, val in kwargs.items():
        if val is None:
            continue
        lines.append(f"{key} {val}")
    return "\n".join(lines)


def default_composite(samples: list[Sample], bad: frozenset[str] = frozenset()) -> tuple[str, list[str]]:
    defaults = [s for s in samples if s.default]
    urls = [f"{s.base_url}/bw/all.percent.accessible.bw" for s in defaults]
    defaults = [s for s in defaults if f"{s.base_url}/bw/all.percent.accessible.bw" not in bad]

    parent = stanza(
        track="fireDefaultAccessibility",
        container="multiWig",
        aggregate="transparentOverlay",
        showSubtrackColorOnUi="on",
        type="bigWig 0 100",
        viewLimits="0:100",
        alwaysZero="on",
        graphTypeDefault="points",
        visibility="full",
        maxHeightPixels="100:50:8",
        windowingFunction="mean",
        group="regulation",
        priority="1",
        shortLabel="Fiber-seq Accessibility",
        longLabel="Fiber-seq Accessibility",
        html="fire-accessibility-description.html",
    )

    children = []
    for sample, color in zip(defaults, DEFAULT_PALETTE):
        child = stanza(
            track=f"fireDefault_{sample.sample_tag}",
            parent="fireDefaultAccessibility",
            bigDataUrl=f"{sample.base_url}/bw/all.percent.accessible.bw",
            type="bigWig",
            color=color,
            shortLabel=trunc(sample.sample, 17),
            longLabel=trunc(
                f"{sample.sample} ({sample.tissue}) Fiber-seq percent accessible chromatin, {sample.ps_id}", 80
            ),
        )
        children.append(child)

    text = "# Default track: overlapping Fiber-seq percent-accessible chromatin, one color per sample\n"
    text += parent + "\n\n"
    text += "\n\n".join("    " + line.replace("\n", "\n    ") for line in children)
    return text + "\n", urls


def accessibility_supertrack(samples: list[Sample], bad: frozenset[str] = frozenset()) -> tuple[str, list[str]]:
    """One selector per sample for percent-accessible chromatin: each is a
    multiWig overlaying all/hap1/hap2 in the hub's standard haplotype colors
    (hap1 blue, hap2 red, all black), same style as the default track.
    A composite `view` can't have a multiWig container as a child (hubCheck
    rejects it), so this lives as its own superTrack alongside the Peaks
    matrix rather than as a row inside it."""
    urls: list[str] = []
    parent = stanza(
        track="fireAccessibilityBySample",
        superTrack="on",
        shortLabel="Percent Accessible by Sample",
        longLabel="Fiber-seq percent accessible chromatin, one multiWig per sample",
        group="regulation",
        priority="1.5",
        html="fire-compendium-description.html",
    )

    children = []
    for s in sorted(samples, key=lambda s: (s.tissue, s.sample)):
        sub_children = []
        for suffix_name, suffix, color in ACCESSIBILITY_SUBTRACKS:
            url = f"{s.base_url}/{suffix}"
            urls.append(url)
            if url in bad:
                continue
            sub_children.append(
                stanza(
                    track=f"fireAccBySample_{s.sample_tag}_{suffix_name}",
                    parent=f"fireAccBySample_{s.sample_tag}",
                    bigDataUrl=url,
                    type="bigWig",
                    color=color,
                )
            )
        if not sub_children:
            continue
        parent_leaf = stanza(
            track=f"fireAccBySample_{s.sample_tag}",
            parent="fireAccessibilityBySample",
            container="multiWig",
            aggregate="transparentOverlay",
            showSubtrackColorOnUi="on",
            type="bigWig 0 100",
            viewLimits="0:100",
            autoScale="off",
            alwaysZero="on",
            graphTypeDefault="points",
            visibility="hide",
            maxHeightPixels="100:50:8",
            shortLabel=trunc(f"{s.sample} Accessible", 17),
            longLabel=trunc(f"{s.sample} ({s.tissue}) Fiber-seq percent accessible chromatin, {s.ps_id}", 80),
        )
        children.append(parent_leaf)
        children.extend(sub_children)

    text = parent + "\n\n"
    text += "\n\n".join("    " + block.replace("\n", "\n    ") for block in children)
    return text + "\n", urls


def compendium_composite(samples: list[Sample], bad: frozenset[str] = frozenset()) -> tuple[str, list[str]]:
    urls: list[str] = []

    # subGroups
    cell_tags = {}
    for s in samples:
        cell_tags.setdefault(s.cell_tag, sanitize_title(s.tissue))
    sample_tags = {s.sample_tag: sanitize_title(f"{s.sample}_{s.ps_id}") for s in samples}

    view_tags = {tag: label for tag, label, *_ in SIMPLE_VIEWS}

    def subgroup_line(n: int, tag: str, title: str, mapping: dict[str, str]) -> str:
        parts = " ".join(f"{k}={v}" for k, v in mapping.items())
        return f"subGroup{n} {tag} {title} {parts}"

    header = "\n".join(
        [
            "track fireCompendium",
            "compositeTrack on",
            "shortLabel Fiber-seq Compendium",
            "longLabel Fiber-seq Compendium",
            subgroup_line(1, "view", "Track_Type", view_tags),
            subgroup_line(2, "cellType", "Cell_Type", cell_tags),
            subgroup_line(3, "sample", "Sample", sample_tags),
            "dimensions dimX=sample dimY=view dimA=cellType",
            "filterComposite dimA",
            "sortOrder cellType=+ sample=+ view=+",
            "dragAndDrop subTracks",
            "visibility hide",
            "type bigWig",
            "html fire-compendium-description.html",
            "group regulation",
            "priority 2",
        ]
    )

    blocks = [header]

    # -- simple views --
    for tag, label, suffix, ttype, extra in SIMPLE_VIEWS:
        view_header = stanza(
            track=f"fireCompendiumView{tag}",
            shortLabel=label.replace("_", " "),
            view=tag,
            visibility="hide",
            parent="fireCompendium",
            type=ttype,
            **extra,
        )
        leaves = []
        for s in samples:
            url = f"{s.base_url}/{suffix}"
            urls.append(url)
            if url in bad:
                continue
            leaf = stanza(
                track=f"fireComp_{tag}_{s.sample_tag}",
                parent=f"fireCompendiumView{tag}",
                bigDataUrl=url,
                type=ttype,
                subGroups=f"view={tag} cellType={s.cell_tag} sample={s.sample_tag}",
                shortLabel=trunc(f"{s.sample} {label.split('_')[0]}", 17),
                longLabel=trunc(f"{s.sample} ({s.tissue}) Fiber-seq {label.replace('_', ' ')}, {s.ps_id}", 80),
            )
            leaves.append("    " + leaf.replace("\n", "\n    "))
        if leaves:
            blocks.append("\n" + view_header)
            blocks.extend(leaves)

    return "\n\n".join(blocks) + "\n", urls


def build() -> None:
    print(f"fetching sample sheet from {SHEET_CSV_URL} ...", file=sys.stderr)
    samples = load_samples(fetch_sheet_csv())
    if not samples:
        sys.exit("no samples with a name, tissue, and working link found in the sheet")

    # Pass 1: harvest every URL the hub would reference.
    _, default_urls = default_composite(samples)
    _, accessibility_urls = accessibility_supertrack(samples)
    _, compendium_urls = compendium_composite(samples)
    all_urls = sorted(set(default_urls) | set(accessibility_urls) | set(compendium_urls))

    print(f"checking {len(all_urls)} data file URLs ...", file=sys.stderr)
    bad = frozenset(check_urls(all_urls))
    if bad:
        print(f"WARNING: {len(bad)} unreachable URLs — dropping the corresponding tracks:", file=sys.stderr)
        for url in sorted(bad):
            print(f"  {url}", file=sys.stderr)
    else:
        print("all data file URLs reachable.", file=sys.stderr)

    # Pass 2: regenerate, omitting any track whose data file is unreachable.
    default_text, _ = default_composite(samples, bad)
    accessibility_text, _ = accessibility_supertrack(samples, bad)
    compendium_text, _ = compendium_composite(samples, bad)

    (HUB_DIR / "hg38").mkdir(parents=True, exist_ok=True)

    (HUB_DIR / "hub.txt").write_text(
        "\n".join(
            [
                f"hub {HUB_NAME}",
                "shortLabel Fiber-seq",
                "longLabel Fiber-seq chromatin accessibility and regulatory elements",
                "genomesFile genomes.txt",
                f"email {CONTACT_EMAIL}",
                "descriptionUrl hg38/fire-compendium-description.html",
                "",
            ]
        )
    )

    (HUB_DIR / "genomes.txt").write_text(
        "\n".join(["genome hg38", "trackDb hg38/trackDb.txt", ""])
    )

    trackdb = (
        default_text
        + "\n"
        + accessibility_text
        + "\n"
        + compendium_text
    )
    (HUB_DIR / "hg38" / "trackDb.txt").write_text(trackdb)

    n_default = sum(1 for s in samples if s.default)
    print(
        f"wrote hub/ for {len(samples)} samples ({n_default} default) -> "
        f"{HUB_DIR / 'hg38' / 'trackDb.txt'}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    build()
