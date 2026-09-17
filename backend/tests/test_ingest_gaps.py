"""What happens when a paper cannot be built.

Every case here was found by sweeping open-access papers across subspecialties, and every
one of them used to fail in a way that misled the reader: an empty explainer that looked
built, or a message telling them to try an open-access paper when theirs already was.
"""

from __future__ import annotations

from ingestion.pubmed import MIN_BODY_WORDS, body_words

FULL = """<article><body><sec><title>Methods</title>
<p>{}</p></sec></body></article>""".format(" ".join(["word"] * 400))

METADATA_ONLY = """<article>
  <front><article-meta><title-group><article-title>An editorial</article-title></title-group>
  <abstract><p>A short abstract that is not a paper.</p></abstract></article-meta></front>
</article>"""

NO_BODY_BUT_LONG_FRONT = """<article><front><article-meta><abstract><p>{}</p></abstract>
</article-meta></front></article>""".format(" ".join(["word"] * 900))


def test_a_real_body_is_counted():
    assert body_words(FULL) >= 400


def test_metadata_only_records_count_as_empty():
    """`<article>` is not evidence of a paper. PMC serves plenty of records without one."""
    assert body_words(METADATA_ONLY) == 0


def test_a_long_abstract_is_not_a_body():
    """Otherwise an abstract-only deposit passes the check and builds an explainer of it."""
    assert body_words(NO_BODY_BUT_LONG_FRONT) == 0


def test_unparseable_xml_is_empty_rather_than_an_exception():
    assert body_words("<article><body><p>unclosed") >= 0
    assert body_words("") == 0
    assert body_words("not xml at all") == 0


def test_the_threshold_rejects_a_stub_and_accepts_a_paper():
    assert body_words(METADATA_ONLY) < MIN_BODY_WORDS
    assert body_words(FULL) >= MIN_BODY_WORDS
