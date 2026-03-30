import json
import pytest
from pathlib import Path

import scripts.platform as platform_module
from scripts.platform import PlatformConfig, load_platform, list_platforms


@pytest.fixture
def mock_base_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(platform_module, "BASE_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def valid_platform(mock_base_dir: Path) -> Path:
    platforms_dir = mock_base_dir / "config" / "platforms"
    platforms_dir.mkdir(parents=True)
    config = {"display_name": "Campus Virtual", "login_url": "https://campus.example/login"}
    (platforms_dir / "myplatform.json").write_text(json.dumps(config), encoding="utf-8")
    return mock_base_dir


class TestLoadPlatform:
    def test_carga_plataforma_valida(self, valid_platform: Path):
        config = load_platform("myplatform")
        assert config.name == "myplatform"
        assert config.display_name == "Campus Virtual"
        assert config.login_url == "https://campus.example/login"

    def test_rutas_derivadas_correctas(self, valid_platform: Path):
        config = load_platform("myplatform")
        assert config.course_links_path == valid_platform / "config" / "myplatform" / "course_links.json"
        assert config.tree_dir == valid_platform / "data" / "myplatform" / "trees"
        assert config.course_dir == valid_platform / "data" / "myplatform" / "course"

    def test_display_name_fallback(self, mock_base_dir: Path):
        platforms_dir = mock_base_dir / "config" / "platforms"
        platforms_dir.mkdir(parents=True)
        # sin display_name, debe usar el nombre de la plataforma
        (platforms_dir / "naked.json").write_text(
            json.dumps({"login_url": "https://example.com/login"}), encoding="utf-8"
        )
        config = load_platform("naked")
        assert config.display_name == "naked"

    def test_plataforma_inexistente_lanza_error(self, mock_base_dir: Path):
        platforms_dir = mock_base_dir / "config" / "platforms"
        platforms_dir.mkdir(parents=True)
        with pytest.raises(FileNotFoundError):
            load_platform("nonexistent")

    def test_falta_login_url_lanza_value_error(self, mock_base_dir: Path):
        platforms_dir = mock_base_dir / "config" / "platforms"
        platforms_dir.mkdir(parents=True)
        (platforms_dir / "bad.json").write_text(
            json.dumps({"display_name": "Sin URL"}), encoding="utf-8"
        )
        with pytest.raises(ValueError):
            load_platform("bad")

    def test_retorna_dataclass(self, valid_platform: Path):
        config = load_platform("myplatform")
        assert isinstance(config, PlatformConfig)


class TestListPlatforms:
    def test_lista_multiples_plataformas(self, mock_base_dir: Path):
        platforms_dir = mock_base_dir / "config" / "platforms"
        platforms_dir.mkdir(parents=True)
        (platforms_dir / "alpha.json").write_text("{}", encoding="utf-8")
        (platforms_dir / "beta.json").write_text("{}", encoding="utf-8")
        result = list_platforms()
        assert set(result) == {"alpha", "beta"}

    def test_lista_vacia_si_no_hay_json(self, mock_base_dir: Path):
        platforms_dir = mock_base_dir / "config" / "platforms"
        platforms_dir.mkdir(parents=True)
        result = list_platforms()
        assert result == []

    def test_directorio_inexistente_devuelve_lista_vacia(self, mock_base_dir: Path):
        # no crear el directorio de platforms
        result = list_platforms()
        assert result == []

    def test_ignora_archivos_no_json(self, mock_base_dir: Path):
        platforms_dir = mock_base_dir / "config" / "platforms"
        platforms_dir.mkdir(parents=True)
        (platforms_dir / "real.json").write_text("{}", encoding="utf-8")
        (platforms_dir / "readme.txt").write_text("ignorame", encoding="utf-8")
        result = list_platforms()
        assert result == ["real"]
