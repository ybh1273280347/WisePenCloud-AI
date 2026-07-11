from __future__ import annotations

import asyncio
import hashlib
import re
import shutil
import tempfile
import time
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

from .core.errors import (
    FileReferenceWriteError,
    InvalidFileReferenceError,
    ReferencedFileNotFoundError,
    ReferencedFileUnreadableError,
)
from .core.models import (
    FileReferenceCleanupResult,
    FileReferenceRecord,
    ResolvedFileReference,
)
from .core.protocols import FileReferenceRepository

DEFAULT_FILE_REFERENCE_ROOT = Path(tempfile.gettempdir()) / "wisepen-file-references"
DEFAULT_FILE_REFERENCE_TTL_SECONDS = 21_600
DEFAULT_FILE_REFERENCE_CLEANUP_GRACE_SECONDS = 600
DEFAULT_FILE_REFERENCE_MAX_BYTES = 52_428_800

_REF_ID_PREFIX = "file_"
_SAFE_COMPONENT_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+")
_MAX_FILENAME_LENGTH = 180
_DANGEROUS_INNER_SUFFIXES = frozenset({
    ".bat", ".cmd", ".com", ".dll", ".exe",
    ".jar", ".js", ".msi", ".ps1", ".scr", ".sh", ".vbs",
})
_HASH_CHUNK_BYTES = 1024 * 1024


class FileReferenceStore:
    """在本地或共享文件系统中发布、解析和清理短期 file_* 引用。"""

    __slots__ = (
        "_cleanup_grace_seconds",
        "_max_file_size_bytes",
        "_ref_ttl_seconds",
        "_repository",
        "_root_dir",
    )

    def __init__(
        self,
        *,
        repository: FileReferenceRepository,
        root_dir: str | Path = DEFAULT_FILE_REFERENCE_ROOT,
        ref_ttl_seconds: int = DEFAULT_FILE_REFERENCE_TTL_SECONDS,
        cleanup_grace_seconds: int = DEFAULT_FILE_REFERENCE_CLEANUP_GRACE_SECONDS,
        max_file_size_bytes: int | None = DEFAULT_FILE_REFERENCE_MAX_BYTES,
    ) -> None:
        self._repository = repository
        self._root_dir = Path(root_dir)
        self._ref_ttl_seconds = int(ref_ttl_seconds)
        self._cleanup_grace_seconds = int(cleanup_grace_seconds)
        self._max_file_size_bytes = max_file_size_bytes

    def create_staging_dir(
        self,
        *,
        user_id: str,
        session_id: str,
        producer: str,
        run_id: str | None = None,
    ) -> Path:
        """为单次工具运行创建隔离的暂存目录。"""
        root = self._ensure_root()
        staging_dir = (
            root
            / _safe_component(user_id, fallback="user")
            / _safe_component(session_id, fallback="session")
            / "staging"
            / _safe_component(producer, fallback="tool")
            / _safe_component(run_id or uuid.uuid4().hex[:16], fallback="run")
        ).resolve(strict=False)
        _ensure_within_root(staging_dir, root)

        try:
            staging_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise FileReferenceWriteError() from exc
        return staging_dir

    async def publish_file(
        self,
        *,
        user_id: str,
        session_id: str,
        producer: str,
        path: str | Path,
        filename: str | None = None,
        content_type: str | None = None,
        ttl_seconds: int | None = None,
        metadata: dict[str, object] | None = None,
        ref_prefix: str | None = None,
    ) -> FileReferenceRecord:
        """发布本地普通文件并返回短期 file_* 引用。"""
        try:
            ttl = self._ref_ttl_seconds if ttl_seconds is None else int(ttl_seconds)
        except (TypeError, ValueError) as exc:
            raise FileReferenceWriteError(
                "ttl_seconds must be an integer.",
            ) from exc
        if ttl <= 0:
            raise FileReferenceWriteError("ttl_seconds must be positive.")

        try:
            source_path = Path(path).resolve(strict=True)
            if not source_path.is_file():
                raise ReferencedFileUnreadableError()
            size_bytes = source_path.stat().st_size
        except OSError as exc:
            raise ReferencedFileUnreadableError() from exc

        if (
            self._max_file_size_bytes is not None
            and size_bytes > self._max_file_size_bytes
        ):
            raise ReferencedFileUnreadableError()

        safe_filename = _sanitize_tool_file_name(filename or source_path.name)
        try:
            sha256 = await asyncio.to_thread(_sha256_file, source_path)
        except OSError as exc:
            raise ReferencedFileUnreadableError() from exc

        root = self._ensure_root()
        object_path = (
            root
            / _safe_component(user_id, fallback="user")
            / _safe_component(session_id, fallback="session")
            / "objects"
            / sha256[:2]
            / f"{sha256}{Path(safe_filename).suffix.lower()}"
        ).resolve(strict=False)
        _ensure_within_root(object_path, root)

        await asyncio.to_thread(
            _copy_to_object_path,
            source_path,
            object_path,
        )

        now = datetime.now(timezone.utc)
        safe_prefix = _safe_component(ref_prefix, fallback="")
        ref_id = (
            f"{_REF_ID_PREFIX}"
            f"{safe_prefix + '_' if safe_prefix else ''}"
            f"{uuid.uuid4().hex[:16]}"
        )
        record = FileReferenceRecord(
            ref_id=ref_id,
            user_id=user_id,
            session_id=session_id,
            producer=producer,
            sha256=sha256,
            object_rel_path=object_path.relative_to(root).as_posix(),
            filename=safe_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
            metadata=dict(metadata or {}),
        )
        await self._repository.put(record, ttl_seconds=ttl)
        return record

    async def publish_bytes(
        self,
        *,
        user_id: str,
        session_id: str,
        producer: str,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        ttl_seconds: int | None = None,
        metadata: dict[str, object] | None = None,
        ref_prefix: str | None = None,
    ) -> FileReferenceRecord:
        """通过暂存文件发布已持有的 bytes 内容。"""
        if (
            self._max_file_size_bytes is not None
            and len(content) > self._max_file_size_bytes
        ):
            raise ReferencedFileUnreadableError()

        safe_filename = _sanitize_tool_file_name(filename)
        staging_dir = self.create_staging_dir(
            user_id=user_id,
            session_id=session_id,
            producer=producer,
        )
        staging_path = (staging_dir / safe_filename).resolve(strict=False)
        _ensure_within_root(staging_path, self._ensure_root())

        try:
            await asyncio.to_thread(
                _write_bytes_to_file,
                staging_path,
                content,
            )
            return await self.publish_file(
                user_id=user_id,
                session_id=session_id,
                producer=producer,
                path=staging_path,
                filename=safe_filename,
                content_type=content_type,
                ttl_seconds=ttl_seconds,
                metadata=metadata,
                ref_prefix=ref_prefix,
            )
        finally:
            self.remove_staging_dir(staging_dir)

    async def resolve_ref(
        self,
        *,
        user_id: str,
        session_id: str,
        ref_id: str,
    ) -> ResolvedFileReference:
        """将 file_* 引用解析为经过作用域、TTL、路径和大小校验的本地文件。"""
        if not ref_id.startswith(_REF_ID_PREFIX):
            raise InvalidFileReferenceError()

        record = await self._repository.get(ref_id)
        if record is None:
            raise ReferencedFileNotFoundError()
        if record.user_id != user_id or record.session_id != session_id:
            raise InvalidFileReferenceError()
        if record.expires_at <= datetime.now(timezone.utc):
            await self._repository.delete(ref_id)
            raise ReferencedFileNotFoundError()

        root = self._ensure_root()
        try:
            object_path = (root / record.object_rel_path).resolve(strict=True)
        except OSError as exc:
            raise ReferencedFileNotFoundError() from exc
        _ensure_within_root(object_path, root)

        try:
            if not object_path.is_file():
                raise ReferencedFileUnreadableError()
            size_bytes = object_path.stat().st_size
        except OSError as exc:
            raise ReferencedFileUnreadableError() from exc
        if size_bytes != record.size_bytes:
            raise ReferencedFileUnreadableError()

        return ResolvedFileReference(
            ref_id=record.ref_id,
            path=object_path,
            filename=record.filename,
            content_type=record.content_type,
            size_bytes=record.size_bytes,
            sha256=record.sha256,
            producer=record.producer,
            expires_at=record.expires_at,
            metadata=dict(record.metadata),
        )

    def remove_staging_dir(self, staging_dir: str | Path) -> None:
        """删除本 store 创建的单次运行暂存目录。"""
        root = self._ensure_root()
        candidate = Path(staging_dir).resolve(strict=False)
        _ensure_within_root(candidate, root)

        relative_parts = candidate.relative_to(root).parts
        if len(relative_parts) != 5 or relative_parts[2] != "staging":
            raise FileReferenceWriteError(
                "staging_dir is not a staging run directory.",
            )
        shutil.rmtree(candidate, ignore_errors=True)

    def cleanup_expired_files(self) -> FileReferenceCleanupResult:
        """按 mtime 回收过期 object 文件和陈旧暂存目录。"""
        root = self._ensure_root()
        cutoff = (
            time.time()
            - self._ref_ttl_seconds
            - self._cleanup_grace_seconds
        )

        scanned_objects = removed_objects = failed_objects = 0
        scanned_staging_dirs = removed_staging_dirs = failed_staging_dirs = 0

        for objects_dir in root.glob("*/*/objects"):
            if not objects_dir.is_dir():
                continue

            for item in list(objects_dir.rglob("*")):
                if not item.is_file():
                    continue

                scanned_objects += 1
                try:
                    resolved = item.resolve(strict=True)
                    _ensure_within_root(resolved, root)
                    if resolved.stat().st_mtime <= cutoff:
                        resolved.unlink()
                        removed_objects += 1
                except Exception:
                    failed_objects += 1

            _remove_empty_children(objects_dir)

        for staging_root in root.glob("*/*/staging"):
            if not staging_root.is_dir():
                continue

            for run_dir in list(staging_root.glob("*/*")):
                if not run_dir.is_dir():
                    continue

                scanned_staging_dirs += 1
                try:
                    resolved = run_dir.resolve(strict=True)
                    _ensure_within_root(resolved, root)
                    if resolved.stat().st_mtime <= cutoff:
                        shutil.rmtree(resolved)
                        removed_staging_dirs += 1
                except Exception:
                    failed_staging_dirs += 1

            _remove_empty_children(staging_root)

        return FileReferenceCleanupResult(
            scanned_objects=scanned_objects,
            removed_objects=removed_objects,
            failed_objects=failed_objects,
            scanned_staging_dirs=scanned_staging_dirs,
            removed_staging_dirs=removed_staging_dirs,
            failed_staging_dirs=failed_staging_dirs,
        )

    def _ensure_root(self) -> Path:
        """确保根目录存在并返回 resolved 路径。"""
        try:
            root = self._root_dir.resolve(strict=False)
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise FileReferenceWriteError() from exc

        if not root.is_dir():
            raise FileReferenceWriteError(
                "file reference root is not a directory.",
            )
        return root


def _safe_component(value: str | None, *, fallback: str) -> str:
    """将任意值清洗为安全的单层路径组件。"""
    raw = PurePosixPath(str(value or "").replace("\\", "/")).name
    safe = _SAFE_COMPONENT_PATTERN.sub("_", raw).strip("._-")
    return safe or fallback


def _sanitize_tool_file_name(
    filename: str,
    *,
    default: str = "file",
) -> str:
    """移除路径片段、危险字符和危险内层后缀，并保留最终扩展名。"""
    base = PurePosixPath(str(filename).replace("\\", "/")).name.strip()
    if not base:
        return default

    path = PurePosixPath(base)
    suffix = _SAFE_FILENAME_PATTERN.sub("", path.suffix).lower()
    stem = path.stem or default

    # 连续剥离危险内层扩展名，防止 report.exe.js.pdf 一类伪装。
    while PurePosixPath(stem).suffix.lower() in _DANGEROUS_INNER_SUFFIXES:
        stem = PurePosixPath(stem).stem or default

    safe_stem = _SAFE_FILENAME_PATTERN.sub("_", stem).strip("._-") or default
    max_stem_length = max(1, _MAX_FILENAME_LENGTH - len(suffix))
    safe_stem = (
        safe_stem[:max_stem_length].rstrip("._-")
        or default
    )
    return f"{safe_stem}{suffix}"[:_MAX_FILENAME_LENGTH] or default


def _sha256_file(path: Path) -> str:
    """分块计算文件 SHA-256。"""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_to_object_path(
    source_path: Path,
    object_path: Path,
) -> None:
    """原子写入内容寻址路径；相同对象已存在时只刷新 mtime。"""
    object_path.parent.mkdir(parents=True, exist_ok=True)
    if object_path.exists():
        object_path.touch()
        return

    tmp_path = object_path.with_name(
        f".{object_path.name}.{uuid.uuid4().hex}.tmp",
    )
    try:
        shutil.copyfile(source_path, tmp_path)
        tmp_path.replace(object_path)
    except OSError as exc:
        raise FileReferenceWriteError() from exc
    finally:
        with suppress(OSError):
            tmp_path.unlink(missing_ok=True)


def _write_bytes_to_file(path: Path, content: bytes) -> None:
    """原子写入 bytes，避免消费者读取半成品。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(
        f".{path.name}.{uuid.uuid4().hex}.tmp",
    )
    try:
        tmp_path.write_bytes(content)
        tmp_path.replace(path)
    except OSError as exc:
        raise FileReferenceWriteError() from exc
    finally:
        with suppress(OSError):
            tmp_path.unlink(missing_ok=True)


def _ensure_within_root(path: Path, root: Path) -> None:
    """拒绝逃逸 store 根目录的路径。"""
    try:
        path.resolve(strict=False).relative_to(
            root.resolve(strict=False),
        )
    except (ValueError, OSError) as exc:
        raise InvalidFileReferenceError() from exc


def _remove_empty_children(root: Path) -> None:
    """从最深层开始删除空目录。"""
    for item in sorted(
        root.rglob("*"),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        if item.is_dir():
            with suppress(OSError):
                item.rmdir()