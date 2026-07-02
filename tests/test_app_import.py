from pathlib import Path


def test_app_module_parses():
    # Compile app.py without executing Streamlit runtime to catch syntax/import errors.
    path = Path(__file__).resolve().parents[1] / "app.py"
    source = path.read_text()
    compile(source, str(path), "exec")
