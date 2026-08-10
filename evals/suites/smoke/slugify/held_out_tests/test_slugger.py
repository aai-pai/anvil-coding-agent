"""Held-out acceptance tests for slugify. The agent never sees these."""


def test_basic_slugs():
    from slugger import slugify

    assert slugify("Hello, World!") == "hello-world"
    assert slugify("The Quick Brown Fox") == "the-quick-brown-fox"
    assert slugify("Python 3.12 Release Notes") == "python-3-12-release-notes"


def test_collapses_and_strips_hyphens():
    from slugger import slugify

    assert slugify("  --Already--Slugged--  ") == "already-slugged"
    assert slugify("a___b") == "a-b"


def test_empty_results():
    from slugger import slugify

    assert slugify("") == ""
    assert slugify("!!! ???") == ""


def test_max_length_truncation():
    from slugger import slugify

    assert slugify("Hello, World!", max_length=6) == "hello"
    assert slugify("Hello, World!", max_length=11) == "hello-world"
    result = slugify("one two three four", max_length=8)
    assert len(result) <= 8
    assert not result.endswith("-")
