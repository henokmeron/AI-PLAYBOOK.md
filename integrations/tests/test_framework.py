"""Integration framework tests using only the in-memory fake connector."""
from __future__ import annotations

import io
import json
import logging
import os
import random
import tempfile
import unittest
from pathlib import Path

from integrations.approvals import ApprovalService
from integrations.audit import AuditLog
from integrations.connector import Connector, Operation
from integrations.errors import (
    ApprovalRequired, AuthenticationError, InvalidRequest, NotFound, PermissionDenied,
    RateLimited, TenantBoundaryViolation, TransientError, WebhookVerificationError, classify_http_status,
)
from integrations.fake import FakeDocumentConnector
from integrations.resilience import Page, RetryPolicy, TokenBucket, call_with_retry, iterate_pages
from integrations.secrets import EnvSecretProvider, FileSecretProvider, Secret
from integrations.tenancy import Access, Scope, TenantContext
from integrations.webhooks import WebhookVerifier, sign

TOKEN = "fake-token-" + "x" * 24


class NoticeConnector(Connector):
    """One idempotent status put and one non-idempotent send, for retry tests."""

    name = "notices"
    operations = {
        "send_notice": Operation(
            "send_notice", Access.WRITE, Scope.parse("notices:write"),
            idempotent=False, requires_approval=True,
        ),
        "put_status": Operation(
            "put_status", Access.WRITE, Scope.parse("notices:write"),
            idempotent=True, requires_approval=True,
        ),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sent: list[str] = []
        self.puts = 0
        self.fail_next_put = True

    def authenticate(self, ctx: TenantContext) -> None:
        return None

    def _perform(self, ctx: TenantContext, op: Operation, params: dict) -> dict:
        if op.name == "send_notice":
            self.sent.append(str(params.get("text", "")))
            if len(self.sent) == 1:
                raise TransientError("accepted then timed out")
            return {"sent": len(self.sent)}
        self.puts += 1
        if self.fail_next_put:
            self.fail_next_put = False
            raise TransientError("timeout before the status was stored")
        return {"status": params.get("status"), "puts": self.puts}


class Clock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def make_connector(**kwargs):
    clock = kwargs.pop("clock", Clock())
    sleeps: list[float] = []
    connector = FakeDocumentConnector(
        secrets=EnvSecretProvider({"FAKE_DOCS_TOKEN"}, {"FAKE_DOCS_TOKEN": TOKEN}),
        audit=AuditLog(clock=clock),
        approvals=ApprovalService(clock=clock),
        rate_limiter=kwargs.pop("rate_limiter", TokenBucket(100, 100, clock=clock)),
        retry_policy=RetryPolicy(max_attempts=3, base_delay=0.01),
        sleep=sleeps.append,
    )
    return connector, sleeps, clock


READER_A = TenantContext.create("tenant-a", "alice", ["documents:read"])
WRITER_A = TenantContext.create("tenant-a", "alice", ["documents:read", "documents:write"])
APPROVER_A = TenantContext.create("tenant-a", "bob", ["documents:read"])
READER_B = TenantContext.create("tenant-b", "carol", ["documents:read"])


class ScopeAndTenantTests(unittest.TestCase):
    def test_read_requires_read_scope(self) -> None:
        connector, _, _ = make_connector()
        none = TenantContext.create("tenant-a", "eve", [])
        with self.assertRaises(PermissionDenied):
            connector.read(none, "list_documents")

    def test_write_scope_does_not_imply_read(self) -> None:
        connector, _, _ = make_connector()
        write_only = TenantContext.create("tenant-a", "eve", ["documents:write"])
        with self.assertRaises(PermissionDenied):
            connector.read(write_only, "list_documents")

    def test_read_and_write_entry_points_are_separate(self) -> None:
        connector, _, _ = make_connector()
        with self.assertRaises(InvalidRequest):
            connector.read(WRITER_A, "create_document", {"title": "x", "body": "y"})
        with self.assertRaises(InvalidRequest):
            connector.write(WRITER_A, "get_document", {"id": "doc-1"}, approval_id=None)

    def test_cross_tenant_access_is_blocked_and_audited(self) -> None:
        connector, _, _ = make_connector()
        doc_b = connector.seed("tenant-b", "B pricing", "secret B")
        connector.seed("tenant-a", "A policy", "A text")
        with self.assertRaises(TenantBoundaryViolation):
            connector.read(READER_A, "get_document", {"id": doc_b})
        listed = list(iterate_pages(lambda c: connector.read(READER_A, "list_documents", {"cursor": c})))
        self.assertEqual([d["title"] for d in listed], ["A policy"])
        last = connector.audit.entries("tenant-a")[-2]
        self.assertEqual((last.outcome, last.error_category), ("denied", "tenant_boundary"))
        self.assertEqual(connector.read(READER_B, "get_document", {"id": doc_b})["body"], "secret B")

    def test_scope_parsing(self) -> None:
        self.assertEqual(str(Scope.parse("mail.messages:read")), "mail.messages:read")
        for bad in ["documents", "documents:admin", "Docs:read", ""]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Scope.parse(bad)


class ApprovalTests(unittest.TestCase):
    def test_write_without_approval_is_refused(self) -> None:
        connector, _, _ = make_connector()
        with self.assertRaises(ApprovalRequired):
            connector.write(WRITER_A, "create_document", {"title": "t", "body": "b"}, approval_id=None)
        self.assertEqual(connector.calls, 0)

    def test_approved_write_executes_once(self) -> None:
        connector, _, _ = make_connector()
        params = {"title": "Minutes", "body": "text"}
        request = connector.request_write(WRITER_A, "create_document", params, "Create minutes doc")
        connector.approvals.decide(request.approval_id, APPROVER_A, approve=True)
        result = connector.write(WRITER_A, "create_document", params, approval_id=request.approval_id)
        self.assertFalse(result["deduplicated"])
        with self.assertRaises(ApprovalRequired):
            connector.write(WRITER_A, "create_document", params, approval_id=request.approval_id)

    def test_self_approval_and_param_tampering_refused(self) -> None:
        connector, _, _ = make_connector()
        params = {"title": "Minutes", "body": "text"}
        request = connector.request_write(WRITER_A, "create_document", params, "Create")
        with self.assertRaises(PermissionDenied):
            connector.approvals.decide(request.approval_id, WRITER_A, approve=True)
        with self.assertRaises(PermissionDenied):
            connector.approvals.decide(request.approval_id, READER_B, approve=True)
        connector.approvals.decide(request.approval_id, APPROVER_A, approve=True)
        with self.assertRaises(ApprovalRequired):
            connector.write(WRITER_A, "create_document", {"title": "Other", "body": "x"},
                            approval_id=request.approval_id)

    def test_denied_and_expired_approvals(self) -> None:
        connector, _, clock = make_connector()
        params = {"title": "a", "body": "b"}
        denied = connector.request_write(WRITER_A, "create_document", params, "x")
        connector.approvals.decide(denied.approval_id, APPROVER_A, approve=False)
        with self.assertRaises(ApprovalRequired):
            connector.write(WRITER_A, "create_document", params, approval_id=denied.approval_id)
        late = connector.request_write(WRITER_A, "create_document", params, "x")
        connector.approvals.decide(late.approval_id, APPROVER_A, approve=True)
        clock.now += 10_000
        with self.assertRaises(ApprovalRequired):
            connector.write(WRITER_A, "create_document", params, approval_id=late.approval_id)

    def test_write_operations_must_require_approval(self) -> None:
        from integrations.connector import Operation
        from integrations.tenancy import Access
        with self.assertRaises(ValueError):
            Operation("x", Access.WRITE, Scope.parse("documents:write"), idempotent=False)


class RetryAndRateLimitTests(unittest.TestCase):
    def test_reads_retry_transient_errors_with_backoff(self) -> None:
        connector, sleeps, _ = make_connector()
        doc = connector.seed("tenant-a", "t", "b")
        connector.inject_faults(lambda: TransientError("503"), lambda: RateLimited("429", retry_after=2.0))
        self.assertEqual(connector.read(READER_A, "get_document", {"id": doc})["title"], "t")
        self.assertEqual(connector.calls, 3)
        self.assertEqual(sleeps[1], 2.0)
        self.assertEqual(connector.audit.entries()[-1].detail["retries"], ["transient", "rate_limited"])

    def test_non_retryable_errors_are_not_retried(self) -> None:
        connector, sleeps, _ = make_connector()
        connector.inject_faults(lambda: NotFound("gone"))
        with self.assertRaises(NotFound):
            connector.read(READER_A, "get_document", {"id": "doc-9"})
        self.assertEqual((connector.calls, sleeps), (1, []))

    def test_writes_without_idempotency_key_are_not_retried(self) -> None:
        connector, _, _ = make_connector()
        params = {"title": "a", "body": "b"}
        req = connector.request_write(WRITER_A, "create_document", params, "x")
        connector.approvals.decide(req.approval_id, APPROVER_A, approve=True)
        connector.inject_faults(lambda: TransientError("timeout"))
        with self.assertRaises(TransientError):
            connector.write(WRITER_A, "create_document", params, approval_id=req.approval_id)
        self.assertEqual(connector.calls, 1)

    def test_idempotency_key_does_not_retry_a_non_idempotent_create(self) -> None:
        connector, _, _ = make_connector()
        params = {"title": "a", "body": "b"}
        req = connector.request_write(WRITER_A, "create_document", params, "x")
        connector.approvals.decide(req.approval_id, APPROVER_A, approve=True)
        connector.inject_faults(lambda: TransientError("timeout"))
        with self.assertRaises(TransientError):
            connector.write(WRITER_A, "create_document", params, approval_id=req.approval_id,
                            idempotency_key="k-1")
        self.assertEqual(connector.calls, 1)

    def test_non_idempotent_send_is_not_repeated_after_it_is_accepted(self) -> None:
        clock = Clock()
        connector = NoticeConnector(
            secrets=EnvSecretProvider({"FAKE_DOCS_TOKEN"}, {"FAKE_DOCS_TOKEN": TOKEN}),
            audit=AuditLog(clock=clock),
            approvals=ApprovalService(clock=clock),
            rate_limiter=TokenBucket(100, 100, clock=clock),
            retry_policy=RetryPolicy(max_attempts=3, base_delay=0.01),
            sleep=lambda _delay: None,
        )
        sender = TenantContext.create("tenant-a", "alice", ["notices:write"])
        params = {"text": "Invoice ready"}
        request = connector.request_write(sender, "send_notice", params, "Send notice")
        connector.approvals.decide(request.approval_id, APPROVER_A, approve=True)
        with self.assertRaises(TransientError):
            connector.write(sender, "send_notice", params, approval_id=request.approval_id,
                            idempotency_key="notice-1")
        self.assertEqual(connector.sent, ["Invoice ready"])

    def test_idempotent_write_with_key_still_retries(self) -> None:
        clock = Clock()
        connector = NoticeConnector(
            secrets=EnvSecretProvider({"FAKE_DOCS_TOKEN"}, {"FAKE_DOCS_TOKEN": TOKEN}),
            audit=AuditLog(clock=clock),
            approvals=ApprovalService(clock=clock),
            rate_limiter=TokenBucket(100, 100, clock=clock),
            retry_policy=RetryPolicy(max_attempts=3, base_delay=0.01),
            sleep=lambda _delay: None,
        )
        sender = TenantContext.create("tenant-a", "alice", ["notices:write"])
        params = {"status": "open"}
        request = connector.request_write(sender, "put_status", params, "Set status")
        connector.approvals.decide(request.approval_id, APPROVER_A, approve=True)
        out = connector.write(sender, "put_status", params, approval_id=request.approval_id,
                              idempotency_key="status-1")
        self.assertEqual(connector.puts, 2)
        self.assertEqual(out["status"], "open")
        connector.fail_next_put = True
        bare = connector.request_write(sender, "put_status", params, "Set status again")
        connector.approvals.decide(bare.approval_id, APPROVER_A, approve=True)
        with self.assertRaises(TransientError):
            connector.write(sender, "put_status", params, approval_id=bare.approval_id)
        self.assertEqual(connector.puts, 3)

    def test_token_bucket(self) -> None:
        clock = Clock()
        bucket = TokenBucket(rate_per_second=1, burst=2, clock=clock)
        bucket.acquire("t")
        bucket.acquire("t")
        with self.assertRaises(RateLimited) as caught:
            bucket.acquire("t")
        self.assertAlmostEqual(caught.exception.retry_after, 1.0)
        bucket.acquire("other-tenant")
        clock.now += 1
        bucket.acquire("t")

    def test_retry_gives_up(self) -> None:
        calls = []

        def always_fail():
            calls.append(1)
            raise TransientError("down")

        with self.assertRaises(TransientError):
            call_with_retry(always_fail, idempotent=True, policy=RetryPolicy(max_attempts=3),
                            sleep=lambda s: None, rng=random.Random(1))
        self.assertEqual(len(calls), 3)

    def test_http_status_classification(self) -> None:
        self.assertIsInstance(classify_http_status(401), AuthenticationError)
        self.assertTrue(classify_http_status(503).retryable)
        self.assertTrue(classify_http_status(429, 3).retryable)
        self.assertFalse(classify_http_status(400).retryable)


class PaginationTests(unittest.TestCase):
    def test_pages_are_followed_and_bounded(self) -> None:
        connector, _, _ = make_connector()
        for i in range(25):
            connector.seed("tenant-a", f"d{i}", "b")
        fetch = lambda c: connector.read(READER_A, "list_documents", {"cursor": c, "page_size": 10})
        self.assertEqual(len(list(iterate_pages(fetch))), 25)
        self.assertEqual(len(list(iterate_pages(fetch, max_items=12))), 12)
        self.assertEqual(len(list(iterate_pages(fetch, max_pages=2))), 20)

    def test_cursor_loop_detected(self) -> None:
        from integrations.errors import IntegrationError
        with self.assertRaises(IntegrationError):
            list(iterate_pages(lambda c: Page([1], "same")))


class SecretTests(unittest.TestCase):
    def test_secret_never_rendered(self) -> None:
        secret = Secret("API_TOKEN", "very-secret-value")
        stream = io.StringIO()
        logger = logging.getLogger("secret-test")
        logger.addHandler(logging.StreamHandler(stream))
        logger.warning("token=%s %r", secret, secret)
        self.assertNotIn("very-secret-value", stream.getvalue() + str(secret) + repr(secret) + f"{secret}")
        with self.assertRaises(TypeError):
            import pickle
            pickle.dumps(secret)

    def test_env_provider_allowlist(self) -> None:
        provider = EnvSecretProvider({"FAKE_DOCS_TOKEN"}, {"FAKE_DOCS_TOKEN": TOKEN, "OTHER": "x" * 20})
        self.assertEqual(provider.get("FAKE_DOCS_TOKEN").reveal(), TOKEN)
        with self.assertRaises(AuthenticationError):
            provider.get("OTHER")
        with self.assertRaises(ValueError):
            provider.get("../etc/passwd")

    def test_file_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "FAKE_DOCS_TOKEN"
            path.write_text("\ufeff" + TOKEN + "\n", encoding="utf-8")
            provider = FileSecretProvider(Path(tmp), enforce_permissions=False)
            self.assertEqual(provider.get("FAKE_DOCS_TOKEN").reveal(), TOKEN)
            with self.assertRaises(AuthenticationError):
                provider.get("MISSING_TOKEN")
            if os.name == "posix":
                os.chmod(path, 0o644)
                with self.assertRaises(AuthenticationError):
                    FileSecretProvider(Path(tmp)).get("FAKE_DOCS_TOKEN")

    def test_missing_credential_fails_closed(self) -> None:
        connector = FakeDocumentConnector(
            secrets=EnvSecretProvider({"FAKE_DOCS_TOKEN"}, {}), audit=AuditLog(), approvals=ApprovalService(),
        )
        with self.assertRaises(AuthenticationError):
            connector.read(READER_A, "list_documents")
        self.assertEqual(connector.calls, 0)
        self.assertEqual(connector.audit.entries()[-1].error_category, "authentication")


class WebhookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock(1_700_000_000)
        self.secret = Secret("WEBHOOK_SECRET", "whsec-" + "s" * 30)
        self.verifier = WebhookVerifier(self.secret, clock=self.clock)
        self.body = json.dumps({"event": "doc.created"}).encode()
        self.ts = str(int(self.clock.now))

    def test_valid_signature_then_replay_rejected(self) -> None:
        sig = sign(self.secret, int(self.ts), self.body)
        self.verifier.verify(self.body, sig, self.ts, "d-1")
        with self.assertRaises(WebhookVerificationError):
            self.verifier.verify(self.body, sig, self.ts, "d-1")

    def test_tampered_stale_or_missing(self) -> None:
        sig = sign(self.secret, int(self.ts), self.body)
        cases = [
            (self.body + b" ", sig, self.ts, "d-2"),
            (self.body, sig, str(int(self.ts) - 3600), "d-3"),
            (self.body, None, self.ts, "d-4"),
            (self.body, sign(Secret("X_SECRET", "wrong-secret-123"), int(self.ts), self.body), self.ts, "d-5"),
            (self.body, sig, "not-a-number", "d-6"),
        ]
        for body, signature, ts, delivery in cases:
            with self.subTest(delivery=delivery), self.assertRaises(WebhookVerificationError):
                self.verifier.verify(body, signature, ts, delivery)


class AuditTests(unittest.TestCase):
    def test_chain_and_redaction(self) -> None:
        connector, _, _ = make_connector()
        connector.read(READER_A, "list_documents", {"api_key": "should-not-appear", "page_size": 5})
        connector.seed("tenant-a", "t", "b")
        entries = connector.audit.entries()
        self.assertTrue(connector.audit.verify_chain())
        self.assertNotIn("should-not-appear", json.dumps([e.detail for e in entries]))
        self.assertNotIn(TOKEN, json.dumps([e.detail for e in entries]))
        object.__setattr__(entries[0], "outcome", "tampered")
        self.assertFalse(connector.audit.verify_chain())


if __name__ == "__main__":
    unittest.main()
