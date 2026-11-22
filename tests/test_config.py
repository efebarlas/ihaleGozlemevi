"""Missing-data guard (SSD unplugged must fail loudly, never start from an empty store)."""
import pytest

from ihale import config


@pytest.fixture
def strict(monkeypatch, tmp_path):
    monkeypatch.delenv("IHALE_ALLOW_NEW_DATA_DIR", raising=False)
    monkeypatch.delenv("IHALE_DATA_DIR", raising=False)
    monkeypatch.setattr(config, "POINTER_FILE", tmp_path / "pointer")
    return tmp_path


def test_env_dir_missing_raises(strict, monkeypatch):
    monkeypatch.setenv("IHALE_DATA_DIR", str(strict / "unplugged" / "live-data"))
    with pytest.raises(config.DataDirMissing, match="does not exist"):
        config.data_dir()
    assert not (strict / "unplugged").exists()          # nothing was created


def test_dir_without_db_raises(strict, monkeypatch):
    d = strict / "empty"
    d.mkdir()
    monkeypatch.setenv("IHALE_DATA_DIR", str(d))
    with pytest.raises(config.DataDirMissing, match="no ihale.db"):
        config.data_dir()


def test_env_dir_with_db_ok(strict, monkeypatch):
    d = strict / "live"
    d.mkdir()
    (d / "ihale.db").write_bytes(b"")
    monkeypatch.setenv("IHALE_DATA_DIR", str(d))
    assert config.data_dir() == d.resolve()
    assert config.db_path() == d.resolve() / "ihale.db"


def test_pointer_file_used_when_no_env(strict):
    d = strict / "ssd" / "live-data"
    d.mkdir(parents=True)
    (d / "ihale.db").write_bytes(b"")
    config.POINTER_FILE.write_text(str(d) + "\n", encoding="utf-8")
    assert config.data_dir() == d.resolve()


def test_pointer_to_missing_drive_raises(strict):
    config.POINTER_FILE.write_text(str(strict / "gone"), encoding="utf-8")
    with pytest.raises(config.DataDirMissing):
        config.data_dir()


def test_allow_new_permits_fresh_install(strict, monkeypatch):
    monkeypatch.setenv("IHALE_DATA_DIR", str(strict / "fresh"))
    monkeypatch.setenv("IHALE_ALLOW_NEW_DATA_DIR", "1")
    assert config.data_dir() == (strict / "fresh").resolve()
