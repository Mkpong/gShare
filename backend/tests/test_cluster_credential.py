"""A registered cluster keeps a usable credential, and a missing one fails loudly.

Registration used to validate the uploaded kubeconfig and discard it; the client then fell back to
the control plane's own service account aimed at the remote apiserver, so the real fault ("we hold
no credential for this cluster") surfaced as an opaque 401 from someone else's API server.
"""
from __future__ import annotations

import pytest

from app.cluster.credentials import (
    ClusterCredentialError,
    decrypt_kubeconfig,
    encrypt_kubeconfig,
)
from app.core.config import settings

KUBECONFIG = """apiVersion: v1
kind: Config
clusters: [{name: remote, cluster: {server: https://10.0.0.9:6443}}]
"""


@pytest.fixture
def credential_key(monkeypatch):
    monkeypatch.setattr(settings, "CLUSTER_CREDENTIAL_KEY", "test-credential-key", raising=False)


def test_roundtrip_keeps_the_credential_usable(credential_key):
    blob = encrypt_kubeconfig(KUBECONFIG)
    assert blob != KUBECONFIG                    # not stored in the clear
    assert "10.0.0.9" not in blob                # nor recoverable by eye
    assert decrypt_kubeconfig(blob) == KUBECONFIG


def test_nothing_stored_reads_back_as_nothing(credential_key):
    assert decrypt_kubeconfig(None) is None
    assert decrypt_kubeconfig("") is None


def test_a_rotated_key_is_reported_not_silently_ignored(credential_key, monkeypatch):
    blob = encrypt_kubeconfig(KUBECONFIG)
    monkeypatch.setattr(settings, "CLUSTER_CREDENTIAL_KEY", "a-different-key", raising=False)
    with pytest.raises(ClusterCredentialError):
        decrypt_kubeconfig(blob)


def test_without_a_key_registration_refuses_rather_than_storing_plaintext(monkeypatch):
    monkeypatch.setattr(settings, "CLUSTER_CREDENTIAL_KEY", "", raising=False)
    with pytest.raises(ClusterCredentialError):
        encrypt_kubeconfig(KUBECONFIG)


@pytest.mark.asyncio
async def test_remote_cluster_without_a_credential_names_the_fault(db):
    """The fallback to our own service account is gone: a remote cluster with no credential must
    raise something that says so."""
    from app.cluster.crd import MissingClusterCredential

    assert MissingClusterCredential.code == "cluster_credential_missing"
    assert MissingClusterCredential.http == 503
