from __future__ import annotations

from pathlib import Path

from app.services.app_service import AppService
from app.repositories import SqlRepository
from data.sql_helper import SqlF


def test_app_service_initialize_and_persist_roundtrip(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    model_dir = tmp_path / "model"

    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    (config_dir / "totalUser.txt").write_text("1", encoding="utf-8")
    (config_dir / "idlists.txt").write_text("1\n", encoding="utf-8")
    (config_dir / "userdic.txt").write_text("{1: 'linhao'}", encoding="utf-8")

    service = AppService()
    service.config_repo.config_dir = Path(config_dir)
    service.data_repo.data_dir = Path(data_dir)
    service.data_repo.model_dir = Path(model_dir)

    service.initialize_state()
    assert service.state.total_user == 1
    assert service.state.user_dic == {1: "linhao"}

    service.state.user_dic[2] = "alice"
    service.state.update_user_stats()
    service.state.id_lists = [1, 2]
    service.persist_training_state()

    assert (config_dir / "totalUser.txt").read_text(encoding="utf-8") == "2"
    assert (config_dir / "idlists.txt").read_text(encoding="utf-8") == "1\n2\n"
    assert "alice" in (config_dir / "userdic.txt").read_text(encoding="utf-8")


def test_sql_repository_account_roundtrip(tmp_path):
    db_path = tmp_path / "sql_repo.db"
    sql_repo = SqlRepository(db=SqlF(backend="sqlite", sqlite_path=str(db_path)))
    try:
        assert sql_repo.register("u1", "p1")
        assert sql_repo.verify_login("u1", "p1")
        accounts = [row[0] for row in sql_repo.get_all_accounts()]
        assert "u1" in accounts
    finally:
        sql_repo.close()
