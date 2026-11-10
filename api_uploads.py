"""
The upload adapter.

`document_parser.extract_text` speaks the Flask FileStorage protocol (sync
`.read()`, `.filename`, `.seek`), and the request body is already in memory
by the time a handler looks at it. This wraps those bytes in that shape so
the parser can be reused unchanged.

Kept whole rather than spread across the route that uses it: a partial
context manager is dead code that reads as if it were live, and the last
audit found exactly that, so the class carries only the methods the parser
actually calls.
"""

import io


class _SyncUpload:
    """A Flask FileStorage stand-in over bytes already read from the request."""

    def __init__(self, filename, data):
        self.filename = filename
        self._buffer = io.BytesIO(data)

    def read(self, *args):
        return self._buffer.read(*args)

    def seek(self, *args):
        return self._buffer.seek(*args)

    def seekable(self) -> bool:
        return self._buffer.seekable()

    def tell(self):
        return self._buffer.tell()

    def getvalue(self) -> bytes:
        return self._buffer.getvalue()
