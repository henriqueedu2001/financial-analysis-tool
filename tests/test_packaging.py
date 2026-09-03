from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_docker_build_context_never_reincludes_personal_data():
    patterns = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert patterns[0] == "**"
    assert not any(pattern.startswith("!data") for pattern in patterns)


def test_dockerfile_uses_explicit_copy_instead_of_whole_repository():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY . " not in dockerfile
    assert "COPY finance ./finance" in dockerfile


def test_compose_persists_only_local_data_directory():
    compose = yaml.safe_load((PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    service = compose["services"]["finance"]
    assert service["volumes"] == ["./data:/app/data"]
    assert service["environment"]["FINANCE_DATABASE_URL"].endswith("/app/data/finance.sqlite")
