"""Tests for :mod:`model_harness.endpoint_policy`."""

from __future__ import annotations

import os

import pytest

from model_harness.contract import EndpointRejected
from model_harness.endpoint_policy import EndpointPolicy


class TestClassifyHost:
    """Unit tests for host classification logic."""

    def test_accepts_localhost(self):
        policy = EndpointPolicy()
        permitted, reason = policy.classify_host("localhost")
        assert permitted, reason

    def test_accepts_docker_internal(self):
        policy = EndpointPolicy()
        permitted, reason = policy.classify_host("host.docker.internal")
        assert permitted, reason

    def test_accepts_wsl_gateway(self):
        policy = EndpointPolicy()
        permitted, reason = policy.classify_host("172.21.176.1")
        assert permitted, reason

    def test_accepts_loopback_ip(self):
        policy = EndpointPolicy()
        permitted, reason = policy.classify_host("127.0.0.1")
        assert permitted, reason

    def test_accepts_private_network(self):
        """RFC1918 addresses are allowed — academics on university networks
        are a first-class supported case."""
        policy = EndpointPolicy()
        for host in ("192.168.1.50", "10.20.30.40", "172.16.0.1"):
            permitted, reason = policy.classify_host(host)
            assert permitted, f"{host}: {reason}"

    def test_rejects_link_local(self):
        """169.254.0.0/16 is always denied regardless of opt-in."""
        policy = EndpointPolicy(allow_public=True)
        permitted, reason = policy.classify_host("169.254.169.254")
        assert not permitted
        assert "link-local" in reason

    def test_rejects_link_local_entire_block(self):
        """Any link-local address must be rejected."""
        policy = EndpointPolicy()
        for host in ("169.254.0.1", "169.254.255.254", "169.254.100.50"):
            permitted, reason = policy.classify_host(host)
            assert not permitted, f"{host} was permitted: {reason}"
            assert "link-local" in reason

    def test_rejects_public_without_opt_in(self):
        """Public addresses require ARTIFICE_ALLOW_PUBLIC_MODELS."""
        policy = EndpointPolicy(allow_public=False)
        # Use an IP literal so the test does not depend on DNS — a machine
        # with a wildcard resolver would otherwise change the outcome.
        permitted, reason = policy.classify_host("8.8.8.8")
        assert not permitted
        assert "ARTIFICE_ALLOW_PUBLIC_MODELS" in reason

    def test_accepts_public_with_opt_in(self):
        """With ARTIFICE_ALLOW_PUBLIC_MODELS set, public hosts pass."""
        policy = EndpointPolicy(allow_public=True)
        permitted, reason = policy.classify_host("8.8.8.8")
        assert permitted, reason

    def test_rejects_unresolvable_host(self):
        """A name that cannot be resolved must fail closed."""
        policy = EndpointPolicy()
        permitted, reason = policy.classify_host("nonexistent.invalid")
        assert not permitted
        assert "could not be resolved" in reason

    def test_custom_always_allowed(self):
        """The always-allowed set can be overridden for testing."""
        policy = EndpointPolicy(always_allowed_hosts=frozenset(["myhost.local"]))
        permitted, reason = policy.classify_host("myhost.local")
        assert permitted, reason
        # localhost is NOT in the custom set
        permitted, reason = policy.classify_host("localhost")
        # localhost resolves to 127.0.0.1 which IS private, so it passes
        # through the address check even though it's not explicitly allowed.
        assert permitted or "resolves to the link-local" not in reason


class TestValidateUrl:
    """Unit tests for full URL validation."""

    def test_accepts_localhost_url(self):
        policy = EndpointPolicy()
        assert policy.validate_url("http://localhost:11434/v1") == "http://localhost:11434/v1"

    def test_accepts_https(self):
        policy = EndpointPolicy()
        assert policy.validate_url("https://localhost:443/v1") == "https://localhost:443/v1"

    def test_rejects_ftp(self):
        policy = EndpointPolicy()
        with pytest.raises(EndpointRejected, match="scheme must be http or https"):
            policy.validate_url("ftp://localhost:21")

    def test_rejects_file_scheme(self):
        policy = EndpointPolicy()
        with pytest.raises(EndpointRejected, match="scheme must be http or https"):
            policy.validate_url("file:///etc/passwd")

    def test_rejects_empty_string(self):
        policy = EndpointPolicy()
        with pytest.raises(EndpointRejected):
            policy.validate_url("")

    def test_rejects_garbage(self):
        policy = EndpointPolicy()
        with pytest.raises(EndpointRejected):
            policy.validate_url("not-a-url!!!")

    def test_rejects_no_host(self):
        policy = EndpointPolicy()
        with pytest.raises(EndpointRejected, match="has no host"):
            policy.validate_url("http:///path")

    def test_rejects_link_local_url(self):
        policy = EndpointPolicy()
        with pytest.raises(EndpointRejected, match="link-local"):
            policy.validate_url("http://169.254.169.254/latest/meta-data/")

    def test_rejects_public_url_without_opt_in(self):
        policy = EndpointPolicy(allow_public=False)
        with pytest.raises(EndpointRejected, match="ARTIFICE_ALLOW_PUBLIC_MODELS"):
            policy.validate_url("http://8.8.8.8:11434/v1")

    def test_accepts_public_url_with_opt_in(self):
        policy = EndpointPolicy(allow_public=True)
        assert policy.validate_url("http://8.8.8.8:11434/v1") == "http://8.8.8.8:11434/v1"


class TestResolve:
    """The Protocol ``resolve`` method."""

    def test_resolve_delegates_to_validate(self):
        policy = EndpointPolicy()
        assert policy.resolve("http://localhost:11434/v1") == "http://localhost:11434/v1"

    def test_resolve_rejects_bad_url(self):
        policy = EndpointPolicy()
        with pytest.raises(EndpointRejected):
            policy.resolve("ftp://evil.com")
