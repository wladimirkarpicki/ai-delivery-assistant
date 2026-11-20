"""Unit tests for the upload parser's edge cases.

extract_text's security posture is that a malformed upload must surface
as the ValueError the API layer already turns into a 400, never a 500:
a non-ZIP under a .docx name, a truncated archive, a damaged PDF, a
non-UTF-8 text file, an oversized upload, and an inflated result that
exceeds the transcript budget all land here. The happy paths for txt/md
and .docx are exercised by the API-layer suite; this module pins the
guards the audit run flagged as uncovered.
"""

import io
import unittest
import zipfile
from unittest.mock import Mock, patch

from pypdf.errors import PyPdfError

from document_parser import (
    MAX_EXTRACTED_CHARS,
    MAX_FILE_SIZE,
    extract_text,
)


class MemoryUpload:
    """The in-memory file object the upload endpoints hand the parser.

    BytesIO with a .name: it answers the whole protocol extract_text
    probes for (seek/tell/read/getvalue), which is what an UploadFile
    looks like by the time the parser sees it.
    """

    def __init__(self, data, name):
        self._stream = io.BytesIO(data)
        self.name = name

    def seek(self, *args):
        return self._stream.seek(*args)

    def tell(self):
        return self._stream.tell()

    def read(self, *args):
        return self._stream.read(*args)

    def getvalue(self):
        return self._stream.getvalue()


class StreamUpload:
    """A read-only file object: the protocol extract_text probes for,
    minus getvalue, because the parser's fallback path (_extract_text_file)
    is written for objects that only answer read()."""

    def __init__(self, data, name):
        self._stream = io.BytesIO(data)
        self.name = name

    def seek(self, *args):
        return self._stream.seek(*args)

    def tell(self):
        return self._stream.tell()

    def read(self, *args):
        return self._stream.read(*args)


class OversizedUpload:
    """An upload whose measured size is one byte over the cap.

    The payload itself stays small on purpose: the size guard measures
    the stream, and 20 MB of test allocation to prove one comparison is
    a waste of both time and memory.
    """

    def __init__(self):
        self.name = "huge.txt"

    def seek(self, *args):
        pass

    def tell(self):
        return MAX_FILE_SIZE + 1


class UnsupportedAndSizeGuardTests(unittest.TestCase):
    def test_unsupported_extension_raises(self):
        with self.assertRaises(ValueError) as ctx:
            extract_text(MemoryUpload(b"data", "notes.exe"))

        self.assertIn(".exe", str(ctx.exception))

    def test_the_extension_dispatches_case_insensitively(self):
        # Dispatch is by lowercased extension, matching the API contract.
        result = extract_text(MemoryUpload(b"plain text", "notes.TXT"))

        self.assertEqual(result, "plain text")

    def test_an_upload_larger_than_the_cap_raises(self):
        with self.assertRaises(ValueError) as ctx:
            extract_text(OversizedUpload())

        self.assertIn("maximum allowed size", str(ctx.exception))


class TextFileTests(unittest.TestCase):
    def test_a_read_only_stream_is_read_without_getvalue(self):
        # A real uploaded file object exposes read() but not getvalue().
        result = extract_text(StreamUpload(b"plain text", "notes.txt"))

        self.assertEqual(result, "plain text")

    def test_a_non_utf8_file_raises(self):
        with self.assertRaises(ValueError) as ctx:
            extract_text(MemoryUpload(b"\xff\xfe invalid bytes", "notes.txt"))

        self.assertIn("UTF-8", str(ctx.exception))

    def test_an_empty_file_raises(self):
        with self.assertRaises(ValueError) as ctx:
            extract_text(MemoryUpload(b"   \n", "notes.txt"))

        self.assertIn("No readable text", str(ctx.exception))

    def test_a_result_larger_than_the_transcript_budget_raises(self):
        # MAX_EXTRACTED_CHARS is the real memory bound: the size guard
        # above measures the compressed stream, which is only a floor.
        payload = ("x" * (MAX_EXTRACTED_CHARS + 1)).encode()

        with self.assertRaises(ValueError) as ctx:
            extract_text(MemoryUpload(payload, "notes.txt"))

        self.assertIn("too much text", str(ctx.exception))


class PdfTests(unittest.TestCase):
    @patch("document_parser.PdfReader")
    def test_pdf_pages_are_joined_skipping_empty_ones(self, mock_reader):
        page_with_text = Mock()
        page_with_text.extract_text.return_value = "first page"
        blank_page = Mock()
        blank_page.extract_text.return_value = None
        mock_reader.return_value.pages = [page_with_text, blank_page]

        result = extract_text(MemoryUpload(b"%PDF-1.4 fake", "notes.pdf"))

        self.assertEqual(result, "first page")

    @patch("document_parser.PdfReader")
    def test_a_broken_pdf_raises_value_error(self, mock_reader):
        mock_reader.side_effect = PyPdfError("damaged")

        with self.assertRaises(ValueError) as ctx:
            extract_text(MemoryUpload(b"%PDF-1.4 broken", "notes.pdf"))

        self.assertIn("could not be read", str(ctx.exception))

    @patch("document_parser.PdfReader")
    def test_a_pdf_with_no_text_raises(self, mock_reader):
        blank_page = Mock()
        blank_page.extract_text.return_value = ""
        mock_reader.return_value.pages = [blank_page]

        with self.assertRaises(ValueError) as ctx:
            extract_text(MemoryUpload(b"%PDF-1.4 blank", "notes.pdf"))

        self.assertIn("No readable text", str(ctx.exception))


class DocxTests(unittest.TestCase):
    def _zip_bytes(self, members):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, content in members:
                archive.writestr(name, content)
        return buffer.getvalue()

    def test_a_docx_without_the_zip_signature_raises(self):
        with self.assertRaises(ValueError) as ctx:
            extract_text(MemoryUpload(b"this is plain text", "notes.docx"))

        self.assertIn("not a valid document", str(ctx.exception))

    def test_a_truncated_zip_raises(self):
        full = self._zip_bytes([("[Content_Types].xml", "<types/>")])
        truncated = full[: len(full) // 2]

        with self.assertRaises(ValueError) as ctx:
            extract_text(MemoryUpload(truncated, "notes.docx"))

        self.assertIn("could not be opened", str(ctx.exception))

    def test_a_zip_without_the_required_member_raises(self):
        payload = self._zip_bytes([("hello.txt", "not a docx")])

        with self.assertRaises(ValueError) as ctx:
            extract_text(MemoryUpload(payload, "notes.docx"))

        self.assertIn("content description", str(ctx.exception))

    @patch("document_parser.Document")
    def test_a_docx_python_docx_cannot_read_raises(self, mock_document):
        # A thin word/document.xml passes both archive checks but reaches
        # lxml in python-docx and raises AttributeError there; it must
        # become a 400, not a 500.
        mock_document.side_effect = AttributeError("no document part")
        payload = self._zip_bytes([("[Content_Types].xml", "<types/>")])

        with self.assertRaises(ValueError) as ctx:
            extract_text(MemoryUpload(payload, "notes.docx"))

        self.assertIn("could not be read", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()