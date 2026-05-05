import pytest

from jobpipe.authoring.adapter import AuthorAdapter
from jobpipe.authoring.author_factory import build_author
from jobpipe.authoring.simple_agent_author import SimpleAgentAuthor


def test_factory_returns_simple_by_default():
    assert isinstance(build_author(), SimpleAgentAuthor)


def test_factory_simple_explicit():
    assert isinstance(build_author("simple"), SimpleAgentAuthor)


def test_factory_satisfies_protocol():
    assert isinstance(build_author("simple"), AuthorAdapter)


def test_factory_unknown_raises():
    with pytest.raises(ValueError, match="Unknown author"):
        build_author("nonsense")


def test_factory_no_static_crewai_import():
    from pathlib import Path

    src = (
        Path(__file__).resolve().parent.parent
        / "jobpipe"
        / "authoring"
        / "author_factory.py"
    ).read_text(encoding="utf-8")
    assert "import crewai" not in src
    assert "from crewai" not in src


def test_factory_simple_branch_has_no_author_cli_sys_modules_lookup():
    from pathlib import Path

    src = (
        Path(__file__).resolve().parent.parent
        / "jobpipe"
        / "authoring"
        / "author_factory.py"
    ).read_text(encoding="utf-8")
    assert "sys.modules" not in src
    assert "jobpipe.authoring.author_cli" not in src
