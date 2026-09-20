"""A stand-in for google.cloud.firestore.Client, good enough for the store adapter.

WHY A FAKE AND NOT THE EMULATOR: `gcloud emulators firestore start` needs a Java 8+
JRE on PATH and the cloud-firestore-emulator component; this machine has neither
(verified: "To use the Google Cloud Firestore emulator, a Java 8+ JRE must be
installed"), and it is not a development machine, so nothing is installed for it.

What this fake DOES check: the document paths we use, create()-as-idempotency
(AlreadyExists), snapshot.exists/to_dict, and — importantly — that values are
serialised rather than aliased, by deep-copying on the way in and out exactly as
a wire protocol would. What it CANNOT check: real transaction atomicity under
concurrency. That claim still needs the emulator or a real project.
"""

from __future__ import annotations

import copy

from google.api_core.exceptions import AlreadyExists


class FakeSnapshot:
    def __init__(self, data: dict | None) -> None:
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict | None:
        return copy.deepcopy(self._data)


class FakeDocumentRef:
    def __init__(self, store: dict, path: str) -> None:
        self._store, self._path = store, path

    def get(self, transaction=None) -> FakeSnapshot:
        return FakeSnapshot(self._store.get(self._path))

    def set(self, data: dict) -> None:
        self._store[self._path] = copy.deepcopy(data)

    def create(self, data: dict) -> None:
        if self._path in self._store:
            raise AlreadyExists(self._path)
        self._store[self._path] = copy.deepcopy(data)

    def delete(self) -> None:
        self._store.pop(self._path, None)


class FakeQuery:
    """Only what the store uses: one equality filter, a limit, and stream()."""

    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def limit(self, n: int) -> FakeQuery:
        return FakeQuery(self._docs[:n])

    def stream(self):
        return (FakeSnapshot(d) for d in self._docs)


class FakeCollection:
    def __init__(self, store: dict, name: str) -> None:
        self._store, self._name = store, name

    def document(self, doc_id: str) -> FakeDocumentRef:
        return FakeDocumentRef(self._store, f"{self._name}/{doc_id}")

    def where(self, field_path=None, op_string=None, value=None, *, filter=None) -> FakeQuery:
        if filter is None or filter.op_string != "==":
            raise NotImplementedError(
                "the fake only supports where(filter=FieldFilter(_, '==', _))"
            )
        prefix = f"{self._name}/"
        return FakeQuery(
            [
                doc
                for path, doc in self._store.items()
                if path.startswith(prefix) and doc.get(filter.field_path) == filter.value
            ]
        )


class FakeFirestore:
    """Flat dict keyed by "collection/document"."""

    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self.docs, name)
