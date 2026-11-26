from io import BytesIO
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile

from app.delivery_file import MAX_FILE_BYTES, validate_file
from app.storage import LocalStorage


@pytest.mark.parametrize(("name", "data", "status"), [
    ("../output.txt", b"ready", 422),
    ("output.txt", b"", 422),
    ("output.txt", b"\x00", 415),
    ("output.txt", b"x" * (MAX_FILE_BYTES + 1), 413),
    ("output.jpg", b"not a jpeg", 415),
    ("output.pdf", b"%PDF-1.4", 415),
    ("output.svg", b"<svg></svg>", 415),
])
def test_rejects_invalid_delivery_uploads(name, data, status):
    with pytest.raises(HTTPException) as exc:
        validate_file(UploadFile(BytesIO(data), filename=name))
    assert exc.value.status_code == status


def test_local_storage_uses_private_opaque_name(tmp_path):
    name, data, _ = validate_file(UploadFile(BytesIO("מסירה".encode()), filename="תוצר.txt"))
    storage = LocalStorage(tmp_path)
    file_id = uuid4()
    storage.store(file_id, data)
    path = storage.path(file_id)
    assert path != tmp_path / name
    assert path.read_bytes() == data
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        storage.store(file_id, b"new file")
    assert path.read_bytes() == data
