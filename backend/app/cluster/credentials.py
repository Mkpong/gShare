"""Encrypted storage for a remote cluster's kubeconfig.

Registration used to validate the uploaded kubeconfig and then discard it: only a
``secret://gshare/cluster-creds/{id}`` reference string was persisted, and every later operation
re-read the YAML from a file an operator was expected to place by hand. Nothing said so, and when
the file was missing the client silently fell back to the control plane's own service account
pointed at the remote apiserver — which fails as an opaque 401 rather than "no credential".

So the credential is now kept, encrypted at rest with a key the deployment supplies. The mounted
file still wins when present, so existing external-secrets deployments keep working unchanged.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.errors import DomainError


class ClusterCredentialError(DomainError):
    """The credential cannot be encrypted or decrypted — a configuration fault, not user input."""

    code, http = "cluster_credential_unavailable", 503


def _fernet() -> Fernet:
    """The encryption key, derived from CLUSTER_CREDENTIAL_KEY.

    Any non-empty secret works: it is hashed to the 32 bytes Fernet needs, so an operator can
    supply a passphrase without knowing the key format. An empty setting is a hard error rather
    than a silent plaintext fallback.
    """
    raw = (settings.CLUSTER_CREDENTIAL_KEY or "").strip()
    if not raw:
        raise ClusterCredentialError(
            "GSHARE_CLUSTER_CREDENTIAL_KEY is not set; a remote cluster credential cannot be stored"
        )
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()))


def encrypt_kubeconfig(kubeconfig_yaml: str) -> str:
    """Ciphertext for storage. Raises when the deployment has no key configured."""
    return _fernet().encrypt(kubeconfig_yaml.encode()).decode()


def decrypt_kubeconfig(ciphertext: str | None) -> str | None:
    """Plaintext for use, or None when nothing is stored.

    A key change invalidates every stored credential; that surfaces here as a clear error rather
    than as a mysterious authentication failure against the remote apiserver.
    """
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ClusterCredentialError(
            "stored cluster credential cannot be decrypted; the credential key changed"
        ) from exc
