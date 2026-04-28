"""Global test configuration -- deterministic local tests, no live services."""
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TEST_TMP_ROOT = _PROJECT_ROOT / "tmp_pytest_runtime"


class WorkspaceTemporaryDirectory:
    """TemporaryDirectory replacement that is writable in this Windows sandbox.

    Python's stdlib TemporaryDirectory can create directories with ACLs that this
    workspace sandbox cannot re-enter. Tests only need ordinary workspace dirs,
    so create them with normal inherited permissions and clean up best-effort.
    """

    def __init__(
        self,
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | None = None,
        ignore_cleanup_errors: bool = True,
    ):
        root = Path(dir) if dir else _TEST_TMP_ROOT
        root.mkdir(parents=True, exist_ok=True)
        name = f"{prefix or 'tmp'}{uuid.uuid4().hex}{suffix or ''}"
        self.name = str(root / name)
        Path(self.name).mkdir(parents=True, exist_ok=False)
        self._ignore_cleanup_errors = ignore_cleanup_errors

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        shutil.rmtree(self.name, ignore_errors=self._ignore_cleanup_errors)

    def __del__(self) -> None:
        try:
            self.cleanup()
        except Exception:
            pass


def workspace_mkdtemp(suffix: str | None = None, prefix: str | None = None, dir: str | None = None) -> str:
    """mkdtemp replacement with normal inherited workspace permissions."""
    root = Path(dir) if dir else _TEST_TMP_ROOT
    root.mkdir(parents=True, exist_ok=True)
    name = f"{prefix or 'tmp'}{uuid.uuid4().hex}{suffix or ''}"
    path = root / name
    path.mkdir(parents=True, exist_ok=False)
    return str(path)


def pytest_configure(config):
    """Run before test collection/imports: disable network-backed agent paths.

    This prevents real OpenRouter/OpenAI API calls from turning a short test run
    into a slow network exercise. It also keeps live broker tests opt-in even
    when a developer has credentials in `.env`.
    """
    _TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    os.environ["TEMP"] = str(_TEST_TMP_ROOT)
    os.environ["TMP"] = str(_TEST_TMP_ROOT)
    os.environ["TMPDIR"] = str(_TEST_TMP_ROOT)
    tempfile.tempdir = str(_TEST_TMP_ROOT)
    tempfile.TemporaryDirectory = WorkspaceTemporaryDirectory
    tempfile.mkdtemp = workspace_mkdtemp

    os.environ["OPENROUTER_API_KEY"] = ""
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["ANTHROPIC_API_KEY"] = ""
    os.environ.setdefault("RUN_LIVE_ALPACA_TESTS", "0")


@pytest.fixture
def tmp_path():
    """Workspace-local replacement for pytest's tmp_path fixture."""
    path = Path(workspace_mkdtemp(prefix="tmp_path_"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
