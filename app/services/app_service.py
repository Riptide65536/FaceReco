from __future__ import annotations

from app.repositories import ConfigRepository, DataRepository, SqlRepository
from app.services.recognition_pipeline import RecognitionPipeline
from app.state import AppState


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
            model_path = self.data_repo.model_file_path()
            if model_path.exists():
                try:
                    model_path.unlink()
                except OSError:
                    pass
            ok = True
        else:
            ok = self.pipeline.train_and_save(samples, labels)
        if ok:
            self.data_repo.clear_model_pending()
        self.state.update_user_stats()
        self.persist_training_state()
        return ok

    def reset_face_data(self) -> None:
        self.data_repo.clear_face_data_keep_py()
        self.data_repo.reset_model_dir()
        self.state.user_dic = {}
        self.state.clear_training_cache()
        self.state.total_user = 0
        self.data_repo.clear_model_pending()
        self.persist_training_state()

    def can_train_user(self, username: str) -> tuple[bool, str]:
        name = str(username).strip()
        if not name:
            return False, '你还没有输入姓名'
        if not self.data_repo.user_dir_exists(name):
            return False, '该用户不存在或未进行录入'
        return True, ''

    def ensure_user_registered(self, username: str) -> int:
        name = str(username).strip()
        for label, saved_name in self.state.user_dic.items():
            if saved_name == name:
                return int(label)
        next_id = max([int(i) for i in self.state.user_dic.keys()], default=0) + 1
        self.state.user_dic[next_id] = name
        self.state.total_user = max(self.state.total_user, next_id)
        return next_id

    def delete_user_and_rebuild(self, username: str) -> bool:
        name = str(username).strip()
        if not name:
            return False

        target_label = None
        for label, saved_name in list(self.state.user_dic.items()):
            if saved_name == name:
                target_label = int(label)
                break

        if target_label is not None and target_label in self.state.user_dic:
            self.state.user_dic.pop(target_label)

        self.data_repo.remove_user_dirs(name, target_label)
        return self.rebuild_and_train()

    def delete_user_only(self, username: str) -> bool:
        name = str(username).strip()
        if not name:
            return False

        target_label = None
        for label, saved_name in list(self.state.user_dic.items()):
            if saved_name == name:
                target_label = int(label)
                break

        if target_label is not None and target_label in self.state.user_dic:
            self.state.user_dic.pop(target_label)

        self.data_repo.remove_user_dirs(name, target_label)
        self.state.update_user_stats()
        self.persist_training_state()
        self.mark_model_pending()
        return True

    def mark_model_pending(self) -> None:
        self.data_repo.mark_model_pending()

    def is_model_pending(self) -> bool:
        return self.data_repo.is_model_pending()
