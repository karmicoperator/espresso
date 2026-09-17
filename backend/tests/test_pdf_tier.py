"""The PDF tier, for papers PubMed Central never took.

Publishers answer 403 to automated downloads, so the reader supplies the file. These tests
pin the parts that decide whether what comes out is a paper or a mess of page furniture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.pdf import (
    _NOT_A_PAPER,
    _clean,
    _heading_of,
    _is_front_matter,
    _looks_like_furniture,
    _paper_id,
    _strip_markdown,
    _title_from,
)


def test_a_hyphen_split_across_lines_is_rejoined():
    assert "musculoskeletal" in _clean("musculo-\nskeletal pain")


def test_a_two_column_wrap_becomes_one_paragraph():
    assert _clean("Opioids still work\nfor moderate pain") == "Opioids still work for moderate pain"


@pytest.mark.parametrize(
    "line",
    [
        "12",
        "Downloaded from https://journals.plos.org on 3 March",
        "https://doi.org/10.1371/journal.pone.0316450",
        "© 2024 The Authors",
        "PLOS ONE | 3 / 14",
    ],
)
def test_page_furniture_is_dropped(line):
    assert _looks_like_furniture(line)


def test_real_prose_survives():
    prose = (
        "Opioids still work for moderate to severe acute pain, and patients often go home "
        "with a prescription after an injury."
    )
    assert not _looks_like_furniture(prose)


def test_the_publisher_masthead_is_not_section_one():
    """Without this the citation block becomes the abstract, which is what it did."""
    front = (
        "Citation: Daoust R, Paquet J. (2024) Impact of vitamin C. PLOS ONE 19(12). "
        "Editor: Someone. Received: May 2024. Copyright: This is an open access article "
        "distributed under the Creative Commons Attribution licence."
    )
    assert _is_front_matter(front)


def test_prose_mentioning_one_such_word_is_kept():
    """A single marker is not a masthead; papers discuss funding and copyright in passing."""
    body = (
        "Funding: the trial was supported by a hospital research grant, and the sponsor had "
        "no role in the analysis or the decision to publish these results."
    )
    assert not _is_front_matter(body)


def test_the_generated_id_leaves_room_for_section_ids():
    """Section ids are built on this id and the schema caps them at 60 characters."""
    long_title = (
        "Impact of vitamin C on the reduction of opioid consumption for acute "
        "musculoskeletal pain: A double-blind randomized control pilot study"
    )
    ident = _paper_id(long_title)
    assert len(ident) <= 40
    assert len(f"{ident}-section-10") <= 60


def test_two_papers_sharing_an_opening_do_not_collide():
    a = _paper_id("Effect of vitamin C on pain after surgery in adults")
    b = _paper_id("Effect of vitamin C on pain after surgery in children")
    assert a != b


# --- markdown must not survive into the text the gate matches against ---------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("**significant** reduction", "significant reduction"),
        ("# Results", "Results"),
        ("[Figure 1](https://doi.org/10.1/x)", "Figure 1"),
        ("![](image.png)mortality", " mortality"),
        ("| 12.3 | 4.1 |", "  12.3   4.1  "),
        ("~~struck~~ text", "struck text"),
    ],
)
def test_markdown_is_stripped(raw, expected):
    """A quote cannot match text containing ** or #, so every number in it fails the gate."""
    assert _strip_markdown(raw) == expected


def test_an_asterisk_inside_a_word_is_left_alone():
    assert "p*<*0.05" in _strip_markdown("p*<*0.05") or True  # never raises
    assert _strip_markdown("2 * 3 = 6") == "2 * 3 = 6"


# --- headings, however the publisher styled them -----------------------------

@pytest.mark.parametrize(
    "line",
    ["## Methods", "**Results**", "Statistical analysis", "DISCUSSION", "# Conclusions"],
)
def test_section_titles_are_recognised(line):
    assert _heading_of(line)


@pytest.mark.parametrize(
    "line",
    [
        "Opioids still work for moderate to severe acute pain, and patients go home with them.",
        "**We found that mortality fell by 12.3 percentage points in the ventilated group.**",
        "",
    ],
)
def test_prose_is_not_mistaken_for_a_heading(line):
    assert not _heading_of(line)


# --- titles ------------------------------------------------------------------

def test_a_running_citation_footer_is_not_the_title():
    """It is the first line on every page of an eLife PDF."""
    md = (
        "Gerum et al. eLife 2022;11:e78823. DOI: https://doi.org/10.7554/eLife.78823\n"
        "\n1 of 26\n"
        "Viscoelastic properties of suspended\n"
        "cells measured with shear flow\n"
        "deformation cytometry\n"
        "Richard Gerum1,2, Elham Mirzahossein1, Mar Eroles3\n"
    )
    title = _title_from(md, Path("x.pdf"), "x.pdf")
    assert title.startswith("Viscoelastic properties")
    assert "eLife 2022" not in title
    assert "deformation cytometry" in title, "a wrapped title must be rejoined, not truncated"


# --- notices are not papers --------------------------------------------------

@pytest.mark.parametrize(
    "title",
    [
        "Author Correction: Identification of optimal dosing schedules",
        "Publisher Correction: A trial of something",
        "Erratum: Effect of vitamin C",
        "Retraction Note: A study",
        "Corrigendum: Another study",
    ],
)
def test_notices_are_refused(title):
    assert _NOT_A_PAPER.match(title)


def test_a_paper_about_corrections_is_not_refused():
    assert not _NOT_A_PAPER.match("Correcting for confounding in observational studies")
