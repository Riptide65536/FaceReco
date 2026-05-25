from __future__ import annotations

from app.repositories import ConfigRepository, DataRepository, SqlRepository
from app.services.recognition_pipeline import RecognitionPipeline
from app.state import AppState
from pathlib import Path


class AppService:
    """Application-level service coordinating state + repositories + pipeline."""

    def __init__(self) -> None:
        self.state = AppState()
        self.config_repo = ConfigRepository()
        self.data_repo = DataRepository()
        self.sql_repo = SqlRepository()
        self.pipeline = RecognitionPipeline(self.state)

    def initialize_state(self) -> None:
        self.config_repo.ensure_dirs()
        self.data_repo.ensure()

        self.state.total_user = self.config_repo.load_total_user()
        self.state.id_lists = self.config_repo.load_id_lists()
        self.state.user_dic = self.config_repo.load_user_dic()
        self.state.update_user_stats()

        samples, labels = self.pipeline.rebuild_training_data(self.data_repo)
        self.state.face_samples = samples
        self.state.id_lists = labels
        self.state.update_user_stats()

    def persist_training_state(self) -> None:
        self.config_repo.save_total_user(self.state.total_user)
        self.config_repo.save_id_lists(self.state.id_lists)
        self.config_repo.save_user_dic(self.state.user_dic)

    def rebuild_and_train(self) -> bool:
        samples, labels = self.pipeline.rebuild_training_data(self.data_repo)
        self.state.face_samples = samples
        self.state.id_lists = labels
        if self.pipeline.cv2 is None:
            self.state.update_user_stats()
            self.persist_training_state()
            return len(samples) >= 0
        if len(samples) == 0:
            model_path = Path("model") / "model.yml"
            if model_path.exists():
                try:
                    model_path.unlink()
                except OSError:
                    pass
            ok = True
        else:
            ok = self.pipeline.train_and_save(samples, labels)
        self.state.update_user_stats()
        self.persist_training_state()
        return ok

    def reset_face_data(self) -> None:
        self.data_repo.clear_face_data_keep_py()
        self.data_repo.reset_model_dir()
        self.state.user_dic = {}
        self.state.clear_training_cache()
        self.state.total_user = 0
        self.persist_training_state()
