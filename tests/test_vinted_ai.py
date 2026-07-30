from __future__ import annotations

import struct
import unittest
import zlib

from agent_runtime.vinted_ai import PNG_SIGNATURE, _strip_png_metadata


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    payload = chunk_type + data
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


class VintedAiTests(unittest.TestCase):
    def test_strip_png_metadata_removes_text_chunks(self) -> None:
        ihdr = _png_chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0),
        )
        text = _png_chunk(b"tEXt", b"Comment\x00created by agent lab")
        idat = _png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00"))
        iend = _png_chunk(b"IEND", b"")

        cleaned = _strip_png_metadata(PNG_SIGNATURE + ihdr + text + idat + iend)

        self.assertTrue(cleaned.startswith(PNG_SIGNATURE))
        self.assertIn(b"IHDR", cleaned)
        self.assertIn(b"IDAT", cleaned)
        self.assertIn(b"IEND", cleaned)
        self.assertNotIn(b"tEXt", cleaned)


if __name__ == "__main__":
    unittest.main()
