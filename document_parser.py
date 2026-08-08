from pathlib import Path

from docx import Document
from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
}


def extract_text(uploaded_file):
    """
    Extract text from a Streamlit UploadedFile.

    Supported formats:
        PDF, DOCX, TXT, MD

    Returns:
        Extracted text as a string.

    Raises:
        ValueError: If the file format is unsupported or no text is found.
    """

    extension = Path(uploaded_file.name).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format: {extension}"
        )

    if extension == ".pdf":
        return _extract_pdf(uploaded_file)

    if extension == ".docx":
        return _extract_docx(uploaded_file)

    if extension in {".txt", ".md"}:
        return _extract_text_file(uploaded_file)

    raise ValueError(
        f"Unsupported file format: {extension}"
    )


def _extract_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)

    pages = []

    for page in reader.pages:
        text = page.extract_text()

        if text:
            pages.append(text)

    result = "\n\n".join(pages).strip()

    if not result:
        raise ValueError(
            "No readable text was found in the PDF."
        )

    return result


def _extract_docx(uploaded_file):
    document = Document(uploaded_file)

    paragraphs = [
        paragraph.text
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]

    result = "\n\n".join(paragraphs).strip()

    if not result:
        raise ValueError(
            "No readable text was found in the DOCX file."
        )

    return result


def _extract_text_file(uploaded_file):
    data = uploaded_file.getvalue()

    try:
        result = data.decode("utf-8").strip()
    except UnicodeDecodeError:
        result = data.decode("utf-8-sig").strip()

    if not result:
        raise ValueError(
            "The uploaded file is empty."
        )

    return result