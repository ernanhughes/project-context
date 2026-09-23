"""Reader abstraction for matched behavioural interventions.

A reader turns a frozen (prompt, context) pair into one response. The
experiment runner depends on the ReaderAdapter protocol, never on a
vendor SDK. Live adapters use only stdlib HTTP; tests use FakeReader.
"""

from project_context.readers.domain import (
    READER_REQUEST_SCHEMA,
    READER_RESPONSE_SCHEMA,
    ReaderAdapter,
    ReaderRequest,
    ReaderResponse,
    ReaderTransportError,
)

__all__ = [
    "READER_REQUEST_SCHEMA",
    "READER_RESPONSE_SCHEMA",
    "ReaderAdapter",
    "ReaderRequest",
    "ReaderResponse",
    "ReaderTransportError",
]
