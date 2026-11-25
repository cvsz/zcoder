"""
zcoder.credentials.seam — Credential-reference capability seam.

This module provides the CredentialProvider service definition and related
types for resolving, storing, and managing credentials. It is the zcoder
equivalent of deepseek-harness's @zharness/dsh-credentials package.

The seam has two key spaces:

- CredentialRef answers "what is behind this environment-variable name":
  the provider-managed store first, then ambient fallbacks such as the
  process environment and .env files. One seam-wide rule binds this half:
  an empty stored value is absent everywhere — resolve skips it,
  describe reports it unconfigured — so a blank never masquerades as a
  configured secret.

- CredentialKey answers "what credential does this plugin hold for this id".
  Nothing can layer here — an authorization grant has no environment to be
  read from — so presence of the record is the whole fact, and
  modifyRecord is the only write path because a correct write depends on
  the current value (a token refresh is read-decide-replace under one lock).
"""

from __future__ import annotations

import re
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from zcoder.core.exceptions import ZCoderError
from zcoder.core.security import brandString


class CredentialError(ZCoderError):
    """Raised when credential operations fail."""

    error_code = "CREDENTIAL_ERROR"


class CredentialRef(str):
    """Branded reference to a credential value.

    A CredentialRef names an environment variable (e.g. ``DEEPSEEK_API_KEY``)
    whose value is the actual secret. Consumers resolve a reference once per
    operation; a changed credential reaches the next operation without any
    plugin restart.
    """

    @classmethod
    def parse(cls, value: str) -> CredentialRef:
        if not is_credential_ref_name(value):
            raise ValueError(f'credential ref "{value}" does not match ' f"{_REF_PATTERN.pattern!r}")
        return cast(CredentialRef, brandString(value))

    def __str__(self) -> str:
        return str.__str__(self)


class CredentialKey(str):
    """Branded key identifying a stored credential record.

    A CredentialKey is "<scope>/<id>" where scope is the owning plugin's
    registered name and id is that plugin's own addressing unit.
    """

    @classmethod
    def parse(cls, value: str) -> CredentialKey:
        segments = value.split("/")
        if len(segments) != 2:
            raise ValueError(f'credential key "{value}" must be "<scope>/<id>"')
        scope, id_ = segments
        if not _KEY_SEGMENT_PATTERN.match(scope) or not _KEY_SEGMENT_PATTERN.match(id_):
            raise ValueError(
                f'credential key segment "{scope if not _KEY_SEGMENT_PATTERN.match(scope) else id_}" '
                f"must match {_KEY_SEGMENT_PATTERN.pattern!r}"
            )
        return cast(CredentialKey, brandString(f"{scope}/{id_}"))


# CredentialRef is defined as a class above; CredentialKey is defined as a class above.
# No aliasing needed between them.


@dataclass(frozen=True)
class CredentialRecord:
    """One stored credential record."""

    kind: str
    value: str | None = None


@dataclass(frozen=True)
class CredentialRecordEntry:
    """One stored record's address and tag, for enumeration — never its value."""

    key: CredentialKey
    kind: str


@dataclass(frozen=True)
class CredentialRecordInfo:
    """Presence and writability facts for one record."""

    configured: bool
    kind: str | None = None
    writable: bool = False


@dataclass(frozen=True)
class ResolvedCredential:
    """One resolved credential value and the source layer that supplied it."""

    value: str
    source: str


class CredentialInfo:
    """Describe one reference for configuration surfaces without exposing
    the full value."""

    def __init__(
        self,
        configured: bool,
        kind: str | None = None,
        writable: bool = False,
    ) -> None:
        self.configured = configured
        self.kind = kind
        self.writable = writable


class CredentialProvider:
    """Abstract credential service over two key spaces.

    A CredentialRef answers "what is behind this environment-variable
    name": the provider-managed store first, then ambient fallbacks such as
    the process environment and .env files. One seam-wide rule binds this
    half: an empty stored value is absent everywhere — resolve skips it,
    describe reports it unconfigured — so a blank never masquerades as a
    configured secret.

    A CredentialKey answers "what credential does this plugin hold for this
    id". Nothing can layer here — an authorization grant has no environment
    to be read from — so presence of the record is the whole fact, and
    modifyRecord is the only write path because a correct write depends on
    the current value (a token refresh is read-decide-replace under one
    lock).
    """

    @abstractmethod
    def resolve(self, ref: CredentialRef) -> ResolvedCredential | None:
        """Resolve one reference to its current value.

        Resolution is per call: consumers re-resolve at each operation and
        must not cache across operations — that per-operation read is what
        makes a changed credential reach the next operation without any
        plugin restart.
        """
        ...

    @abstractmethod
    def describe(self, ref: CredentialRef) -> CredentialInfo:
        """Describe one reference for configuration surfaces without
        exposing the full value."""
        ...

    @abstractmethod
    def set(self, ref: CredentialRef, value: str) -> None:
        """Durably store one value in the provider-managed writable source.

        The stored value takes precedence over ambient fallbacks, and empty
        values are rejected (use unset).
        """

    @abstractmethod
    def unset(self, ref: CredentialRef) -> None:
        """Remove one reference from the provider-managed writable source."""
        ...

    @abstractmethod
    def readRecord(self, key: CredentialKey) -> CredentialRecord | None:
        """Read one stored record.

        The value is returned as its owner wrote it. A GrantRecord payload
        is not interpreted on the way out.
        """
        ...

    @abstractmethod
    def describeRecord(self, key: CredentialKey) -> CredentialRecordInfo:
        """Describe one record for configuration surfaces without exposing
        its value."""
        ...

    @abstractmethod
    def listRecords(self) -> list[CredentialRecordEntry]:
        """Enumerate every stored record's address and tag, values excluded."""

    @abstractmethod
    def modifyRecord(
        self,
        key: CredentialKey,
        mutate: Callable[[CredentialRecord | None], CredentialRecord | None | None],
    ) -> CredentialRecord | None:
        """Serialized read-modify-write over one record.

        mutate sees the record as it stands at the moment the write is
        exclusive, and returning undefined leaves the entry untouched.
        Exclusion holds across processes where the backing store supports
        it — which is what makes a token refresh safe.
        """
        ...

    @abstractmethod
    def deleteRecord(self, key: CredentialKey) -> None:
        """Remove one record. Removing an absent record is a no-op."""
        ...

    def notifyUpdated(self, ref: CredentialRef) -> None:
        """Fan credentials/reference-updated out with contained listener
        failures."""
        pass

    def notifyRecordUpdated(self, key: CredentialKey) -> None:
        """Fan credentials/record-updated out exactly like notifyUpdated."""
        pass


# Service Definition aliases for convenience.  Re-exported for plugin consumers.
CredentialService = CredentialProvider  # noqa: F841

# ── CredentialPattern constants ──────────────────────────────────────────

_REF_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_KEY_SEGMENT_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


def is_credential_ref_name(value: str) -> bool:
    """Whether a raw string could name a reference at all.

    Consumers that receive environment-variable names from somewhere else —
    a provider library's own ambient discovery, a hook payload — ask this
    before resolving, because a name outside the grammar has no reference
    to miss and should read as "not set" rather than as a thrown error.
    """
    return bool(_REF_PATTERN.fullmatch(value))


def credentialRef(value: str) -> CredentialRef:
    """Brand a raw string as a CredentialRef."""
    return CredentialRef.parse(value)


# Export all public symbols
__all__ = [
    "CredentialRef",
    "CredentialKey",
    "CredentialProvider",
    "CredentialRecord",
    "CredentialRecordEntry",
    "CredentialRecordInfo",
    "CredentialInfo",
    "ResolvedCredential",
    "credentialRef",
    "CredentialError",
]
