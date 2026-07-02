from src.config import load_config, Config


def test_get_reads_nested_dotted_path(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("transcribe:\n  provider: groq\n  local:\n    model: small\n")
    cfg = load_config(str(p))
    assert cfg.get("transcribe.provider") == "groq"
    assert cfg.get("transcribe.local.model") == "small"


def test_get_returns_default_for_missing_path(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("summarize:\n  provider: ollama\n")
    cfg = load_config(str(p))
    assert cfg.get("transcribe.provider", "local") == "local"


def test_missing_file_yields_empty_config():
    cfg = load_config("does-not-exist.yaml")
    assert isinstance(cfg, Config)
    assert cfg.get("anything", "fallback") == "fallback"
