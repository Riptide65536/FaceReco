from data.config_manager import CameraSlotConfig, ConfigManager


def test_config_manager_migrates_legacy_files_to_json(tmp_path):
    legacy = tmp_path / "config"
    legacy.mkdir()
    (legacy / "configwin1.txt").write_text("front\n2\n0\n", encoding="utf-8")

    manager = ConfigManager(json_path=str(tmp_path / "config.json"), legacy_dir=str(legacy))

    slots = manager.load()

    assert slots[0] == CameraSlotConfig(name_location="front", displaymode=2, url="0")
    assert (tmp_path / "config.json").exists()


def test_config_manager_saves_json_and_legacy_files(tmp_path):
    legacy = tmp_path / "config"
    manager = ConfigManager(json_path=str(tmp_path / "config.json"), legacy_dir=str(legacy))

    manager.save([CameraSlotConfig(name_location="gate", displaymode=1, url="rtsp://demo")])

    assert "rtsp://demo" in (tmp_path / "config.json").read_text(encoding="utf-8")
    assert (legacy / "configwin1.txt").read_text(encoding="utf-8").splitlines() == [
        "gate",
        "1",
        "rtsp://demo",
    ]
