"""Content-addressed immutable local blobs behind a minimal storage port."""

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Protocol


class BlobStore(Protocol):
    def put(self, data: bytes) -> str: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...


class LocalBlobStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        if not re.fullmatch("[a-f0-9]{64}", key):
            raise ValueError("invalid_blob_key")
        path = (self.root / key[:2] / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("blob_path_escape")
        return path

    def put(self, data: bytes) -> str:
        key = hashlib.sha256(data).hexdigest()
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            self.get(key)
            return key
        fd, temporary = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return key

    def get(self, key: str) -> bytes:
        data = self.path(key).read_bytes()
        if hashlib.sha256(data).hexdigest() != key:
            raise ValueError("blob_integrity_mismatch")
        return data

    def put_stream(self, parts) -> str:
        """Content-address a bounded iterator without duplicating the canonical document in RAM."""
        fd, temporary = tempfile.mkstemp(dir=self.root)
        hasher = hashlib.sha256()
        try:
            with os.fdopen(fd, "wb") as stream:
                for part in parts:
                    hasher.update(part)
                    stream.write(part)
                stream.flush()
                os.fsync(stream.fileno())
            key = hasher.hexdigest()
            destination = self.path(key)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                check = hashlib.sha256()
                with destination.open("rb") as source:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        check.update(block)
                if check.hexdigest() != key:
                    raise ValueError("blob_integrity_mismatch")
            else:
                os.replace(temporary, destination)
            return key
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def delete(self, key: str):
        self.path(key).unlink(missing_ok=True)
