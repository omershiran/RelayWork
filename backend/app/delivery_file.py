import hashlib
import unicodedata
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

MAX_FILE_BYTES = 5 * 1024 * 1024
IMAGE_SIGNATURES = {".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}


class DeliveryFile(Base):
    __tablename__ = "delivery_files"
    __table_args__ = (CheckConstraint("size_bytes BETWEEN 1 AND 5242880", name="delivery_file_size"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    delivery_id: Mapped[UUID] = mapped_column(ForeignKey("deliveries.id", name="delivery_files_delivery_id_fkey"),
                                             unique=True)
    name: Mapped[str]
    digest: Mapped[str]
    size_bytes: Mapped[int]


def validate_file(upload: UploadFile):
    name = unicodedata.normalize("NFC", upload.filename or "")
    if (
        not name or name != name.strip() or len(name.encode()) > 240
        or any(character in "/\\" or unicodedata.category(character).startswith("C") for character in name)
    ):
        raise HTTPException(422, "invalid_file_name")
    content = upload.file.read(MAX_FILE_BYTES + 1)
    if not content:
        raise HTTPException(422, "empty_delivery_file")
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "delivery_file_too_large")
    suffix = PurePosixPath(name).suffix.lower()
    if suffix in IMAGE_SIGNATURES:
        valid = content.startswith(IMAGE_SIGNATURES[suffix])
    elif suffix == ".pdf":
        valid = content.startswith(b"%PDF-") and content.rstrip().endswith(b"%%EOF")
    elif suffix == ".txt":
        try:
            text = content.decode("utf-8")
            valid = all(character in "\n\r\t" or character.isprintable() for character in text)
        except UnicodeDecodeError:
            valid = False
    else:
        valid = False
    if not valid:
        raise HTTPException(415, "invalid_delivery_file_type")
    return name, content, hashlib.sha256(content).hexdigest()
