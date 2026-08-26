# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for shared_ui.uploads."""

from __future__ import annotations

import asyncio

import pytest
from shared_ui.uploads import UploadTooLarge, read_capped

_CHUNK = 64 * 1024


class _RecordingUpload:
    """Serves a fixed body, recording the size of every ``read()`` request."""

    def __init__(self, body: bytes) -> None:
        self._body = body
        self._offset = 0
        self.requested_sizes: list[int] = []

    @property
    def served(self) -> int:
        """Number of body bytes handed out so far."""
        return self._offset

    async def read(self, size: int = -1) -> bytes:
        self.requested_sizes.append(size)
        if self._offset >= len(self._body):
            return b""
        if size == -1:
            chunk = self._body[self._offset :]
            self._offset = len(self._body)
            return chunk
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


class TestReadCapped:
    """Tests for read_capped()."""

    def test_body_under_limit_returned_intact(self) -> None:
        body = b"hello world" * 100
        assert asyncio.run(read_capped(_RecordingUpload(body), 100_000)) == body

    def test_body_exactly_at_limit_is_allowed(self) -> None:
        body = b"x" * 1000
        assert asyncio.run(read_capped(_RecordingUpload(body), 1000)) == body

    def test_empty_upload_returns_empty_bytes(self) -> None:
        assert asyncio.run(read_capped(_RecordingUpload(b""), 1000)) == b""

    def test_oversized_raises_before_full_body_is_read(self) -> None:
        body = b"x" * 200_000
        upload = _RecordingUpload(body)
        with pytest.raises(UploadTooLarge):
            asyncio.run(read_capped(upload, 100_000))
        # Reads stay bounded at 64 KB each; a single-read rewrite would ask
        # for -1 and this assertion would fail.
        assert upload.requested_sizes == [_CHUNK, _CHUNK]
        assert -1 not in upload.requested_sizes
        # The whole body was never consumed.
        assert upload.served < len(body)


class TestUploadTooLarge:
    """Tests for UploadTooLarge."""

    def test_public_message_reports_limit_in_mb(self) -> None:
        err = UploadTooLarge(50 * 1024 * 1024)
        assert err.limit_bytes == 50 * 1024 * 1024
        assert err.public_message == "File exceeds 50 MB upload limit"
