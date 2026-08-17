"""The engine-submodule guard must detect the package, not the directory.

Regression cover for a real deploy failure: `engine/` is a git submodule, a
plain clone leaves it as an empty directory, `os.path.isdir()` returned True
anyway, and the resulting image built cleanly and then died at container start
with `ModuleNotFoundError: No module named 'gateway'` — surfacing as a Cloud
Run health-check timeout rather than anything that named the actual problem.

These tests pin the three properties that would have caught it:
  1. an empty engine/ reads as unavailable
  2. failure is loud, immediate, and names the fix
  3. the diagnostic distinguishes the ways it can be broken
"""

from __future__ import annotations

import pytest

from circle import engine_path


@pytest.fixture
def fake_engine(tmp_path, monkeypatch):
    """Point the module at a scratch engine/ we control."""
    def _configure(state: str):
        eng = tmp_path / "engine"
        if state != "missing":
            eng.mkdir()
        if state == "populated":
            (eng / "gateway").mkdir()
            (eng / "gateway" / "__init__.py").write_text("")
        if state == "wrong_commit":
            (eng / "README.md").write_text("content, but no gateway package")
        monkeypatch.setattr(engine_path, "ENGINE_PATH", eng)
        monkeypatch.setattr(engine_path, "GATEWAY_PATH", eng / "gateway")
        return eng
    return _configure


class TestAvailability:
    def test_empty_submodule_is_unavailable(self, fake_engine):
        """THE BUG: an empty engine/ is still a directory. isdir() said yes."""
        eng = fake_engine("empty")
        assert eng.is_dir()                      # the old guard's check passed
        assert engine_path.engine_available() is False   # the new one does not

    def test_missing_engine_is_unavailable(self, fake_engine):
        fake_engine("missing")
        assert engine_path.engine_available() is False

    def test_content_without_gateway_is_unavailable(self, fake_engine):
        fake_engine("wrong_commit")
        assert engine_path.engine_available() is False

    def test_populated_submodule_is_available(self, fake_engine):
        fake_engine("populated")
        assert engine_path.engine_available() is True


class TestFailsLoudly:
    def test_required_raises_on_empty(self, fake_engine):
        fake_engine("empty")
        with pytest.raises(ModuleNotFoundError) as exc:
            engine_path.ensure_on_path()
        assert "git submodule update --init" in str(exc.value)

    def test_error_names_gateway_and_the_fix(self, fake_engine):
        """The message must be actionable without reading the source."""
        fake_engine("empty")
        with pytest.raises(ModuleNotFoundError) as exc:
            engine_path.ensure_on_path()
        msg = str(exc.value)
        assert "gateway" in msg
        assert "submodule" in msg

    def test_optional_callers_can_degrade(self, fake_engine):
        fake_engine("empty")
        assert engine_path.ensure_on_path(required=False) is False


class TestPathInsertion:
    def test_populated_engine_goes_on_syspath(self, fake_engine, monkeypatch):
        eng = fake_engine("populated")
        monkeypatch.setattr(engine_path.sys, "path", ["/unrelated"])
        assert engine_path.ensure_on_path() is True
        assert str(eng) in engine_path.sys.path

    def test_insertion_is_idempotent(self, fake_engine, monkeypatch):
        eng = fake_engine("populated")
        monkeypatch.setattr(engine_path.sys, "path", ["/unrelated"])
        engine_path.ensure_on_path()
        engine_path.ensure_on_path()
        assert engine_path.sys.path.count(str(eng)) == 1

    def test_unavailable_engine_never_pollutes_syspath(self, fake_engine, monkeypatch):
        eng = fake_engine("empty")
        monkeypatch.setattr(engine_path.sys, "path", ["/unrelated"])
        with pytest.raises(ModuleNotFoundError):
            engine_path.ensure_on_path()
        assert str(eng) not in engine_path.sys.path


class TestDiagnose:
    """Each failure mode gets a distinguishable explanation."""

    @pytest.mark.parametrize("state,expected", [
        ("missing", "missing entirely"),
        ("empty", "EMPTY"),
        ("wrong_commit", "unexpected commit"),
        ("populated", "present"),
    ])
    def test_diagnostic_distinguishes_states(self, fake_engine, state, expected):
        fake_engine(state)
        assert expected in engine_path.diagnose()


class TestRealCheckout:
    """Against the actual repo, not a fixture."""

    def test_engine_is_checked_out_here(self):
        """If this fails, the tree cannot produce a working deploy."""
        assert engine_path.engine_available(), engine_path.diagnose()

    def test_gateway_actually_imports(self):
        """The end state the guard exists to protect."""
        engine_path.ensure_on_path()
        from gateway.canonical import canonicalize
        assert callable(canonicalize)
