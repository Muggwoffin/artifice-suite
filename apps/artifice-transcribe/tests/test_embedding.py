from __future__ import annotations

import numpy as np
import pytest

from artifice_transcribe.db.models import pack_embedding, unpack_embedding


class TestPackUnpackRoundTrip:
    """A known float vector survives write → read with values intact."""

    def test_round_trip_1d(self):
        original = np.array([0.1, 0.2, 0.3, -0.4, 0.5], dtype=np.float32)
        blob = pack_embedding(original)
        assert isinstance(blob, bytes)
        assert len(blob) == 5 * 4  # 5 float32 = 20 bytes

        restored = unpack_embedding(blob, dimension=5)
        assert restored.dtype == np.float32
        np.testing.assert_array_equal(original, restored)

    def test_round_trip_high_dimensional(self):
        """512-dim is the default dimension used by PyAnnote embeddings."""
        original = np.random.randn(512).astype(np.float32)
        blob = pack_embedding(original)
        assert len(blob) == 512 * 4

        restored = unpack_embedding(blob, dimension=512)
        assert len(restored) == 512
        np.testing.assert_array_almost_equal(original, restored, decimal=5)

    def test_round_trip_2d_collapses_to_1d(self):
        """pack_embedding casts via asarray so a (1,N) shape becomes 1-D."""
        original = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        blob = pack_embedding(original)
        restored = unpack_embedding(blob, dimension=3)
        assert restored.shape == (3,)
        np.testing.assert_array_equal(restored, np.array([0.1, 0.2, 0.3], dtype=np.float32))

    def test_cast_to_float32(self):
        """A float64 input is safely cast to float32."""
        original = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        blob = pack_embedding(original)
        assert len(blob) == 3 * 4
        restored = unpack_embedding(blob, dimension=3)
        assert restored.dtype == np.float32


class TestUnpackValidation:
    """Malformed or truncated blobs must raise rather than returning a
    silently wrong vector."""

    def test_truncated_blob_raises(self):
        """A blob whose length is not a multiple of 4 is malformed."""
        with pytest.raises(ValueError, match="not a multiple of 4"):
            unpack_embedding(b"\x00\x00\x00", dimension=None)

    def test_wrong_dimension_raises(self):
        """A blob with the wrong number of floats for the declared
        dimension must raise."""
        blob = pack_embedding(np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32))
        with pytest.raises(ValueError, match="expected 5"):
            unpack_embedding(blob, dimension=5)

    def test_empty_blob_raises(self):
        with pytest.raises(ValueError, match="empty"):
            unpack_embedding(b"", dimension=0)

    def test_dimension_none_is_loose(self):
        """When dimension is not provided the check is skipped."""
        blob = pack_embedding(np.array([0.1, 0.2, 0.3], dtype=np.float32))
        restored = unpack_embedding(blob, dimension=None)
        assert len(restored) == 3

    def test_correct_dimension_passes(self):
        """Matching dimension validates cleanly."""
        blob = pack_embedding(np.array([0.1, 0.2], dtype=np.float32))
        restored = unpack_embedding(blob, dimension=2)
        assert len(restored) == 2

    def test_large_dimension_mismatch(self):
        """Big mismatches also raise."""
        blob = pack_embedding(np.zeros(1024, dtype=np.float32))
        with pytest.raises(ValueError, match="expected 512"):
            unpack_embedding(blob, dimension=512)
