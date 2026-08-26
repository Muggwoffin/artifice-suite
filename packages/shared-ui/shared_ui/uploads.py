# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Streaming upload helpers.

Defensive reading of attacker-controlled upload bodies, with no web-framework
dependency so they are usable from the CLI, background threads, and the web
layer alike.  Each app's web layer translates the domain error raised here
into its own HTTP response.
"""

from __future__ import annotations

from typing import Protocol


class _Readable(Protocol):
    """Structural type for an async, chunked-readable upload body.

    Kept structural (rather than importing Starlette's ``UploadFile``) so this
    module has no web-framework dependency.
    """

    async def read(self, size: int = -1) -> bytes: ...


class UploadTooLarge(Exception):
    """An upload exceeded *limit_bytes* before the body was fully read.

    ``public_message`` is built from a string literal (the limit in MB) rather
    than a wrapped third-party exception, mirroring
    :class:`shared_ui.path_validation.PathValidationError`.
    """

    def __init__(self, limit_bytes: int) -> None:
        self.limit_bytes = limit_bytes
        self.public_message = f"File exceeds {limit_bytes // (1024 * 1024)} MB upload limit"
        super().__init__(self.public_message)


async def read_capped(upload: _Readable, limit: int) -> bytes:
    """Read *upload* in bounded 64 KB chunks, returning the full body.

    Raises :class:`UploadTooLarge` if *limit* is exceeded **during** the read,
    so an oversized body is never fully resident in memory.
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(64 * 1024):
        total += len(chunk)
        if total > limit:
            raise UploadTooLarge(limit)
        chunks.append(chunk)
    return b"".join(chunks)
