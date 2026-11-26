import os
import shutil
from pathlib import Path
from typing import Protocol
from uuid import UUID


class StorageFull(Exception):
    pass


class StorageProvider(Protocol):
    def store(self, file_id: UUID, content: bytes) -> None: ...
    def path(self, file_id: UUID) -> Path: ...
    def discard(self, file_id: UUID) -> None: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root

    def path(self, file_id: UUID) -> Path:
        return self.root / file_id.hex

    def store(self, file_id: UUID, content: bytes) -> None:
        if shutil.disk_usage(self.root).free - len(content) < 250 * 1024 * 1024:
            raise StorageFull
        fd = os.open(self.path(file_id), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            directory_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            self.discard(file_id)
            raise

    def discard(self, file_id: UUID) -> None:
        self.path(file_id).unlink(missing_ok=True)


def delivery_storage() -> StorageProvider:
    return LocalStorage(Path(os.getenv("STORAGE_PATH", "/var/lib/agentrelai-demo/deliveries")))
