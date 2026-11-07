import stat

import pytest

from lecture_notes import cli, config, credentials


@pytest.fixture(autouse=True)
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return tmp_path / "cfg"


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_saved_key_is_private_and_read_back(config_dir):
    path = credentials.set_api_key("anthropic", "  sk-ant-abc\n")
    assert path == config_dir / "anthropic-api-key"
    assert _mode(path) == 0o600
    assert path.read_text() == "sk-ant-abc\n"
    assert credentials.get_api_key("anthropic") == "sk-ant-abc"
    assert not [p for p in config_dir.iterdir() if p.name.startswith(".tmp")]  # no leftovers


def test_replacing_key_keeps_permissions(config_dir):
    credentials.set_api_key("anthropic", "sk-ant-old")
    path = credentials.set_api_key("anthropic", "sk-ant-new")
    assert credentials.get_api_key("anthropic") == "sk-ant-new" and _mode(path) == 0o600


def test_hand_made_key_file_is_made_private(config_dir):
    config_dir.mkdir()
    path = config_dir / "anthropic-api-key"
    path.write_text("sk-ant-manual\n")
    path.chmod(0o644)
    assert credentials.get_api_key("anthropic") == "sk-ant-manual"
    assert _mode(path) == 0o600


def test_env_var_is_only_a_fallback(config_dir, monkeypatch):
    assert credentials.get_api_key("anthropic") is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
    assert credentials.get_api_key("anthropic") == "sk-ant-env"
    credentials.set_api_key("anthropic", "sk-ant-file")
    assert credentials.get_api_key("anthropic") == "sk-ant-file"
    (config_dir / "anthropic-api-key").write_text("\n")  # empty file -> fallback again
    assert credentials.get_api_key("anthropic") == "sk-ant-env"


def test_setup_saves_key_to_file(config_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "CONFIG_PATH", config_dir / "config.toml")
    monkeypatch.setattr(cli, "write_default_config", lambda: False)
    monkeypatch.setenv("LECTURE_NOTES_CONFIG", str(tmp_path / "none.toml"))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "sk-ant-from-setup")
    monkeypatch.setattr(cli, "_verify_key", lambda cfg: True)
    monkeypatch.setattr(credentials, "old_keychain_entry_exists", lambda provider: False)
    cli.run_setup()
    assert credentials.get_api_key("anthropic") == "sk-ant-from-setup"
    assert _mode(config_dir / "anthropic-api-key") == 0o600


def test_setup_offers_to_delete_old_keychain_entry(config_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "CONFIG_PATH", config_dir / "config.toml")
    monkeypatch.setattr(cli, "write_default_config", lambda: False)
    monkeypatch.setenv("LECTURE_NOTES_CONFIG", str(tmp_path / "none.toml"))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "sk-ant-x")
    monkeypatch.setattr(cli, "_verify_key", lambda cfg: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "")  # default answer: yes
    deleted = []
    monkeypatch.setattr(credentials, "old_keychain_entry_exists", lambda provider: True)
    monkeypatch.setattr(credentials, "delete_old_keychain_entry", lambda provider: deleted.append(provider) or True)
    cli.run_setup()
    assert deleted == ["anthropic"]
