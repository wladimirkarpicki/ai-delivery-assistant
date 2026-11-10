"""
Text extraction for uploaded meeting notes.

Security posture, because the input is a user-supplied file:

- the size guard measures the *uploaded* (compressed) stream, so it is a
  floor, not a ceiling: a .docx is a ZIP archive and can inflate far
  beyond its compressed size. MAX_EXTRACTED_CHARS caps the inflated
  result instead, which is what actually bounds memory.
- a .docx that is not really a ZIP (wrong content under a .docx name)
  raises zipfile.BadZipFile, and a broken .pdf raises a pypdf error.
  Both map to the same ValueError the API layer already turns into a
  400, so a malformed upload is a bad request rather than a 500.
- dispatch is by filename extension, the same as the API contract, so
  no content sniffing is implied here beyond the archive signature
  check that keeps a non-ZIP out of the docx path.

There is no Flask involvement; the 20 MB body cap lives in this module.
"""

import zipfile
from pathlib import Path

from docx import Document
from pypdf import PdfReader
from pypdf.errors import PyPdfError

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
}
MAX_FILE_SIZE = 20 * 1024 * 1024

# A meeting transcript needs far less than this, and a legitimate note
# that exceeds it is a parse error rather than a silent truncation.
MAX_EXTRACTED_CHARS = 200_000

# docx is a ZIP archive, so the magic number and required member are the
# cheapest check that the content matches the extension.
DOCX_ZIP_SIGNATURE = b"PK\x03\x04"
DOCX_REQUIRED_MEMBER = "[Content_Types].xml"


def extract_text(uploaded_file):
    """
    Extract text from a web upload object.

    Supported formats:
        PDF, DOCX, TXT, MD

    Returns:
        Extracted text as a string.

    Raises:
        ValueError: If the file format is unsupported, the content does
            not match its extension, no text is found, or the text is
            too large to be a meeting transcript.
    """

    filename = getattr(uploaded_file, "filename", None) or uploaded_file.name
    extension = Path(filename).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format: {extension}"
        )

    if hasattr(uploaded_file, "seek") and hasattr(uploaded_file, "tell"):
        uploaded_file.seek(0, 2)  # Seek to end
        size = uploaded_file.tell()
        uploaded_file.seek(0)  # Reset
        if size > MAX_FILE_SIZE:
            raise ValueError("File exceeds maximum allowed size (20 MB).")

    if extension == ".pdf":
        return _extract_pdf(uploaded_file)

    if extension == ".docx":
        return _extract_docx(uploaded_file)

    if extension in {".txt", ".md"}:
        return _extract_text_file(uploaded_file)

    raise ValueError(
        f"Unsupported file format: {extension}"
    )


def _bounded(text):
    """Reject a result too large to be a meeting transcript."""

    if not text:
        raise ValueError("No readable text was found in the document.")

    if len(text) > MAX_EXTRACTED_CHARS:
        raise ValueError(
            "The document contains too much text to treat as meeting "
            f"notes (limit {MAX_EXTRACTED_CHARS} characters)."
        )

    return text


def _extract_pdf(uploaded_file):
    try:
        reader = PdfReader(uploaded_file)
        pages = [page.extract_text() for page in reader.pages]
    except PyPdfError as exc:
        raise ValueError("The uploaded PDF could not be read.") from exc

    result = "\n\n".join(page for page in pages if page).strip()

    return _bounded(result)


def _extract_docx(uploaded_file):
    data = uploaded_file.read()
    uploaded_file.seek(0)

    if not data.startswith(DOCX_ZIP_SIGNATURE):
        raise ValueError("The uploaded .docx is not a valid document.")

    try:
        with zipfile.ZipFile(uploaded_file) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise ValueError("The uploaded .docx could not be opened.") from exc

    # Raised outside the try above, deliberately: the try exists to
    # translate BadZipFile, and a "member is missing" ValueError raised
    # inside it would be caught by an except that is not meant for it,
    # or worse, re-wrapped into a misleading message. A structurally valid
    # archive without the member it needs is its own error and must reach
    # the caller as the 400 it already is.
    if DOCX_REQUIRED_MEMBER not in names:
        raise ValueError(
            "The uploaded .docx is missing its content description."
        )

    try:
        document = Document(uploaded_file)
        paragraphs = [
            paragraph.text
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        ]
    except (zipfile.BadZipFile, KeyError, ValueError, TypeError, AttributeError) as exc:
        # AttributeError is in the tuple for a shape the guard above cannot
        # see: a docx whose word/document.xml is well-formed enough to pass
        # the archive checks but too thin for python-docx, which reaches
        # into lxml and raises AttributeError on an element it expected to
        # be a package part. Every other malformed upload becomes a 400;
        # this one was escaping as a 500.
        raise ValueError("The uploaded .docx could not be read.") from exc

    result = "\n\n".join(paragraphs).strip()

    return _bounded(result)


def _extract_text_file(uploaded_file):
    if hasattr(uploaded_file, "getvalue"):
        data = uploaded_file.getvalue()
    else:
        data = uploaded_file.read()

    for encoding in ("utf-8", "utf-8-sig"):
        try:
            result = data.decode(encoding).strip()
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("The uploaded file is not UTF-8 text.")

    return _bounded(result)
