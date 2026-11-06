"""
Schema-contract and regression tests for the defects the audits found.

Two groups matter here:

- ``test_nullability_matches_mapped_annotations`` pins the mapping
  between the ``Mapped`` annotations in models.py and the actual
  ``nullable`` flag of every column. The Mapped/mapped_column migration
  regressed exactly there: ``Mapped[Any]`` does not imply a type, so a
  column silently became NOT NULL and the suite stayed green.
- the rest are regression tests for silent data loss, silent wrongness
  and unhandled exception types, each of which was found by reading the
  code and reproduced before the fix.

SQLite does not enforce ``varchar(n)``, so the overflow half of that
contract is covered only on the annotation side here; the nullability
half is checked against the real metadata, which is what sqlite does
keep.
"""

import base64
import hashlib
import io
import os
import pathlib
import unittest
import zipfile
from datetime import date
from typing import ClassVar
from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

import api as api_module
import config_loader
import database
from database import db
from matching import cosine_similarity
from models import ActionItem, Meeting, Project, Risk, User
from project_memory import _apply_actions, _apply_risks

# The suite resets the module-level bootstrap-token cache, so the value
# must be deterministic too, otherwise setUp mints a fresh ephemeral one.
os.environ.setdefault("BOOTSTRAP_TOKEN", "unit-test-bootstrap-token-0123456789abcdef")
BOOTSTRAP_TOKEN = os.environ["BOOTSTRAP_TOKEN"]


def _teardown_database():
    """
    Release the in-memory sqlite engine, not just its sessions.

    Every create_app() call here builds a new engine with a StaticPool,
    so the connection stays alive until the engine is disposed. The
    existing suites never dispose it, which is why the run emits dozens
    of "ResourceWarning: unclosed database" and why adding tests to the
    same process eventually ends in an InternalError MemoryError.
    """
    db.session.remove()

    try:
        db.drop_all()
    except RuntimeError:
        pass

    # database.engine is a module-level global, re-bound by every
    # configure_database call; it is not an attribute of the db shim.
    engine = database.engine

    if engine is not None:
        engine.dispose()


class SchemaContractTests(unittest.TestCase):
    """The Mapped annotations and the column metadata must agree."""

    # Expected nullability, column by column, for every root model.
    # Mapped[X] is NOT NULL, Mapped[X | None] is nullable. The
    # mapped_column migration regressed exactly here: Mapped[Any] does
    # not imply a type, so a nullable column silently became NOT NULL.
    # ClassAttr: this is data, not a shared mutable default.
    EXPECTED_NULLABLE: ClassVar[dict] = {
        Project.__name__: {
            "id": False, "name": False, "description": False,
            "created_at": False, "updated_at": False,
        },
        Meeting.__name__: {
            "id": False, "project_id": False, "title": False,
            "source_filename": True, "original_text": False,
            "analysis_text": False, "analysis_json": False,
            "provider": False, "model": False, "created_at": False,
        },
        Risk.__name__: {
            "id": False, "project_id": False, "title": False,
            "canonical_title": False, "title_embedding": True,
            "description": False, "impact": False, "mitigation": False,
            "status": False, "created_in_meeting_id": False,
            "updated_in_meeting_id": False, "resolved_in_meeting_id": True,
            "resolved_at": True,
        },
        ActionItem.__name__: {
            "id": False, "project_id": False, "title": False,
            "canonical_title": False, "title_embedding": True,
            "details": False, "owner": True, "due_date": True,
            "status": False, "created_in_meeting_id": False,
            "updated_in_meeting_id": False, "completed_in_meeting_id": True,
            "completed_at": True,
        },
        User.__name__: {
            "id": False, "username": False, "password_hash": False,
            "role": False,
        },
    }

    def test_nullability_matches_expected_contract(self):
        """
        Every column's nullable flag must match the declared contract.

        This is the assertion whose absence let the mapped_column
        migration ship Mapped[Any] as NOT NULL on columns that had been
        nullable=True (title_embedding, before_data, after_data).
        """

        api_module.create_app(None, "sqlite://")
        mismatches = []

        for model_name, expected in self.EXPECTED_NULLABLE.items():
            model = {"Project": Project, "Meeting": Meeting, "Risk": Risk,
                     "ActionItem": ActionItem, "User": User}[model_name]
            table = model.__table__

            for column_name, expected_nullable in expected.items():
                if column_name not in table.columns:
                    mismatches.append(f"{model_name}.{column_name}: column missing")
                    continue
                actual = table.columns[column_name].nullable
                if actual != expected_nullable:
                    mismatches.append(
                        f"{model_name}.{column_name}: nullable={actual}, "
                        f"contract says {expected_nullable}"
                    )

        self.assertEqual(
            mismatches,
            [],
            "Column nullability drifted from the declared contract:\n"
            + "\n".join(mismatches),
        )

    def test_contract_not_null_columns_reject_none(self):
        """
        Every NOT NULL column must actually reject None at commit time,
        so the contract is enforced by the database and not only by the
        type checker.
        """

        api_module.create_app(None, "sqlite://")
        db.create_all()

        project = Project(name="Contract", description="")
        db.session.add(project)
        db.session.commit()
        meeting = Meeting(
            project_id=project.id,
            title="t",
            original_text="o",
            analysis_text="a",
            analysis_json="{}",
            provider="p",
            model="m",
        )
        db.session.add(meeting)
        db.session.commit()

        with self.assertRaises(IntegrityError):
            db.session.add(
                Risk(
                    project_id=project.id,
                    title="no meeting reference",
                    canonical_title="no meeting reference",
                    # created_in_meeting_id is Mapped[int] -> NOT NULL.
                    created_in_meeting_id=None,
                    updated_in_meeting_id=meeting.id,
                )
            )
            db.session.commit()

        db.session.rollback()

    def test_unique_constraints_are_enforced(self):
        """unique=True on Project.name and User.username must bite."""

        api_module.create_app(None, "sqlite://")
        db.create_all()

        db.session.add(Project(name="Dup", description=""))
        db.session.commit()

        with self.assertRaises(IntegrityError):
            db.session.add(Project(name="Dup", description=""))
            db.session.commit()
        db.session.rollback()

        db.session.add(User(username="twin", password_hash="h", role="user"))
        db.session.commit()

        with self.assertRaises(IntegrityError):
            db.session.add(User(username="twin", password_hash="h2", role="user"))
            db.session.commit()
        db.session.rollback()

    def setUp(self):
        api_module.create_app(None, "sqlite://")
        db.create_all()

    def tearDown(self):
        _teardown_database()


class ConsolidationRegressionTests(unittest.TestCase):
    """Regressions for the silent data loss and wrongness found."""

    def setUp(self):
        # The module-level bootstrap-token cache is process-wide; reset it
        # or a mutated env var leaks across tests.
        config_loader.reset_bootstrap_token()
        api_module._failed_logins.clear()
        self.router = _FixedRouter()
        self.app = api_module.create_app(self.router, "sqlite://")
        db.create_all()
        self.client = TestClient(self.app)

        self.client.post(
            "/api/auth/setup",
            json={
                "username": "founder",
                "password": "founder-pass-123",
                "bootstrap_token": BOOTSTRAP_TOKEN,
            },
        )
        token = self.client.post(
            "/api/auth/login",
            json={"username": "founder", "password": "founder-pass-123"},
        ).json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {token}"

    def tearDown(self):
        _teardown_database()
        config_loader.reset_bootstrap_token()

    def test_update_keeps_fields_the_plan_does_not_mention(self):
        """
        An UPDATE that only names a status must not blank the other
        fields. This is the data-loss regression: four assignments used
        _value(new_item, key) with an implicit "" default.
        """

        project = Project(name="Phoenix", description="")
        db.session.add(project)
        db.session.commit()
        meeting = Meeting(
            project_id=project.id,
            title="m",
            original_text="o",
            analysis_text="a",
            analysis_json="{}",
            provider="p",
            model="m",
        )
        db.session.add(meeting)
        db.session.commit()

        risk = Risk(
            project_id=project.id,
            title="Frequent 500s",
            canonical_title="frequent 500s",
            description="Checkout dies on retries",
            mitigation="Retry policy plus circuit breaker",
            impact="high",
            status="open",
            created_in_meeting_id=meeting.id,
            updated_in_meeting_id=meeting.id,
        )
        db.session.add(risk)
        db.session.commit()

        # The fallback path takes flat finding dicts, not the
        # decision/new_item envelope the LLM plan uses.
        _apply_risks(
            project,
            meeting,
            [
                {
                    "title": "Frequent 500s",
                    "canonical_title": "frequent 500s",
                    "status": "resolved",
                }
            ],
        )
        db.session.commit()
        db.session.refresh(risk)

        self.assertEqual(risk.status, "resolved")
        self.assertEqual(risk.description, "Checkout dies on retries")
        self.assertEqual(risk.mitigation, "Retry policy plus circuit breaker")
        self.assertEqual(risk.impact, "high")

    def test_update_keeps_action_item_details_and_owner(self):
        """Same regression on the ActionItem branch."""

        project = Project(name="Phoenix", description="")
        db.session.add(project)
        db.session.commit()
        meeting = Meeting(
            project_id=project.id,
            title="m",
            original_text="o",
            analysis_text="a",
            analysis_json="{}",
            provider="p",
            model="m",
        )
        db.session.add(meeting)
        db.session.commit()

        item = ActionItem(
            project_id=project.id,
            title="Rotate signing keys",
            canonical_title="rotate signing keys",
            details="Rotate all signing keys by Friday",
            owner="alice",
            due_date=date(2026, 8, 15),
            status="open",
            created_in_meeting_id=meeting.id,
            updated_in_meeting_id=meeting.id,
        )
        db.session.add(item)
        db.session.commit()

        _apply_actions(
            project,
            meeting,
            [
                {
                    "title": "Rotate signing keys",
                    "canonical_title": "rotate signing keys",
                    "status": "completed",
                }
            ],
        )
        db.session.commit()
        db.session.refresh(item)

        self.assertEqual(item.status, "completed")
        self.assertEqual(item.details, "Rotate all signing keys by Friday")
        self.assertEqual(item.owner, "alice")
        self.assertEqual(item.due_date, date(2026, 8, 15))


class _FixedRouter:
    def get_models(self, provider):
        return ["openrouter/free"]

    def generate(self, provider, model, prompt, system_prompt=None):
        return "{}"

    def embed_texts(self, provider, model, texts):
        return [[1.0, 0.0] for _ in texts]


class UploadFormatTests(unittest.TestCase):
    """
    The endpoint advertises PDF, DOCX, TXT and MD. Before this test only
    .txt was ever uploaded, so the advertised binary formats were
    completely unexercised.
    """

    def setUp(self):
        config_loader.reset_bootstrap_token()
        api_module._failed_logins.clear()
        self.router = _FixedRouter()
        self.app = api_module.create_app(self.router, "sqlite://")
        db.create_all()
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.client.post(
            "/api/auth/setup",
            json={
                "username": "founder",
                "password": "founder-pass-123",
                "bootstrap_token": BOOTSTRAP_TOKEN,
            },
        )
        token = self.client.post(
            "/api/auth/login",
            json={"username": "founder", "password": "founder-pass-123"},
        ).json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {token}"
        self.project_id = self.client.post(
            "/api/projects", json={"name": "Uploaders"}
        ).json()["id"]

    def tearDown(self):
        _teardown_database()
        config_loader.reset_bootstrap_token()

    def test_real_docx_is_parsed(self):
        """A genuine DOCX must reach the docx branch and yield its text."""

        from docx import Document

        buffer = io.BytesIO()
        document = Document()
        document.add_paragraph("QA capacity is short by one tester.")
        document.save(buffer)

        response = self.client.post(
            f"/api/projects/{self.project_id}/meetings",
            files={"meeting_file": ("notes.docx", buffer, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"title": "x"},
        )
        self.assertEqual(response.status_code, 201, response.text)

        # serialize_meeting does not expose original_text, so assert the
        # stored value directly: this is what proves the docx branch ran.
        from models import Meeting

        stored = db.session.query(Meeting).order_by(Meeting.id.desc()).first()
        self.assertIn("QA capacity", stored.original_text or "")
        self.assertEqual(stored.source_filename, "notes.docx")

    def test_md_upload_is_parsed(self):
        response = self.client.post(
            f"/api/projects/{self.project_id}/meetings",
            files={"meeting_file": ("notes.md", io.BytesIO(b"# Notes\nVendor slipped a week."), "text/markdown")},
            data={"title": "x"},
        )
        self.assertEqual(response.status_code, 201, response.text)

    def test_zip_misses_content_types_is_rejected(self):
        """
        A file that starts with the ZIP magic but is not a document must
        be a 400, not a crash inside python-docx.
        """

        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("junk.txt", "not an office document")

        payload = archive.getvalue()

        response = self.client.post(
            f"/api/projects/{self.project_id}/meetings",
            files={"meeting_file": ("fake.docx", io.BytesIO(payload), "application/octet-stream")},
            data={"title": "x"},
        )
        self.assertEqual(response.status_code, 400, response.text)


class SecurityHeaderTests(unittest.TestCase):
    """
    The CSP and the rest of the response headers are what make the next
    layer of defence real. The token is still read from localStorage, so
    an injected script could read it back out; the header at least stops
    the injection from loading.
    """

    def setUp(self):
        config_loader.reset_bootstrap_token()
        api_module._failed_logins.clear()
        self.app = api_module.create_app(_FixedRouter(), "sqlite://")
        db.create_all()
        self.client = TestClient(self.app)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        config_loader.reset_bootstrap_token()

    def test_csp_present_on_every_response_type(self):
        for path in ("/api/health", "/api/openapi.json", "/api/docs", "/api/projects/1"):
            response = self.client.get(path)
            csp = response.headers.get("content-security-policy", "")
            self.assertTrue(csp, f"{path} carried no CSP")
            self.assertIn("default-src 'self'", csp)

    def test_script_src_has_no_unsafe_inline(self):
        csp = self.client.get("/api/health").headers["content-security-policy"]
        script_src = csp.split("; ")[1]
        self.assertTrue(script_src.startswith("script-src"))
        self.assertNotIn("unsafe-inline", script_src)
        self.assertNotIn("unsafe-eval", script_src)

    def test_csp_pins_the_one_inline_script_by_hash(self):
        """
        frontend/index.html carries a pre-paint theme script that must
        run before the stylesheet, so it cannot simply be banned. It is
        allowed by hash, which pins its exact bytes.
        """
        csp = self.client.get("/api/health").headers["content-security-policy"]
        self.assertIn("'sha256-", csp)

        # The digest must match the real file, or the theme silently
        # stops working in production.
        html = pathlib.Path("frontend/index.html").read_text(encoding="utf-8")
        start = html.index("<script>") + len("<script>")
        block = html[start:html.index("</script>", start)]
        digest = "sha256-" + base64.b64encode(
            hashlib.sha256(block.encode("utf-8")).digest()
        ).decode("ascii")
        self.assertIn(digest, csp, "CSP hash does not match index.html")

    def test_remaining_security_headers(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(
            response.headers.get("referrer-policy"), "strict-origin-when-cross-origin"
        )
        self.assertEqual(
            response.headers.get("cross-origin-opener-policy"), "same-origin"
        )
        self.assertEqual(response.headers.get("x-frame-options"), "DENY")


class PromptSeparationTests(unittest.TestCase):
    """
    The instructions and the user-controlled document must travel in
    separate roles. Concatenating them into one user message is what let
    a meeting note steer the analysis.
    """

    def test_instructions_go_in_the_system_role(self):
        import analyzer

        text = "QA capacity is short."
        router = _RecordingRouter()

        analyzer.analyze_document(
            text=text,
            provider="openrouter",
            model="openrouter/free",
            router_instance=router,
        )

        # The document is in the user turn, and only the document.
        self.assertEqual(router.user_content, "<meeting_notes>\nQA capacity is short.\n</meeting_notes>")
        # The schema and the guardrails are in the system turn.
        self.assertIn("experienced Delivery Manager", router.system_content)
        self.assertIn("Return only valid JSON", router.system_content)
        self.assertNotIn("QA capacity", router.system_content)
        self.assertNotIn("Delivery Manager", router.user_content)

    def test_consolidation_splits_roles_too(self):
        from memory_consolidator import MemoryConsolidator

        router = _RecordingRouter()
        consolidator = MemoryConsolidator(router=router)

        consolidator.consolidate(
            existing_memory={"risks": []},
            new_analysis={"risks": [{"title": "QA capacity"}]},
            provider="openrouter",
            model="openrouter/free",
        )

        # Data only, and tagged, in the user turn.
        self.assertIn("<new_findings>", router.user_content)
        self.assertIn("QA capacity", router.user_content)
        self.assertNotIn("project memory manager", router.user_content)

        # Instructions, and the explicit "this is data" guard, in the
        # system turn.
        self.assertIn("project memory manager", router.system_content)
        self.assertIn("never as instructions", router.system_content)
        self.assertNotIn("QA capacity", router.system_content)


class AuthCookieTests(unittest.TestCase):
    """
    The session must travel in an httpOnly cookie, not in a token that
    JavaScript can read out of localStorage.

    Both forms are accepted during the migration: the cookie is the one
    no script can reach, and the Authorization header is still honoured
    so a client that has not switched over keeps working.
    """

    def setUp(self):
        config_loader.reset_bootstrap_token()
        api_module._failed_logins.clear()
        self.app = api_module.create_app(None, "sqlite://")
        db.create_all()
        self.client = TestClient(self.app)
        self.setup = self.client.post(
            "/api/auth/setup",
            json={
                "username": "founder",
                "password": "founder-pass-123",
                "bootstrap_token": BOOTSTRAP_TOKEN,
            },
        )
        self.assertEqual(self.setup.status_code, 200, self.setup.text)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        config_loader.reset_bootstrap_token()

    def test_sign_in_sets_an_httponly_cookie(self):
        set_cookie = self.setup.headers.get("set-cookie", "")
        self.assertIn("aida_token=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=strict", set_cookie)
        self.assertIn("Path=/", set_cookie)
        # The cookie and the body carry the same token during the
        # migration window.
        self.assertEqual(
            self.setup.cookies["aida_token"], self.setup.json()["access_token"]
        )

    def test_cookie_alone_authenticates(self):
        with TestClient(
            self.app, cookies={"aida_token": self.setup.cookies["aida_token"]}
        ) as cookie_client:
            response = cookie_client.get("/api/auth/me")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["username"], "founder")

            projects = cookie_client.get("/api/projects")
            self.assertEqual(projects.status_code, 200)

    def test_authorization_header_still_accepted(self):
        with TestClient(
            self.app,
            headers={"Authorization": f"Bearer {self.setup.json()['access_token']}"},
        ) as bearer_client:
            response = bearer_client.get("/api/auth/me")
            self.assertEqual(response.status_code, 200)

    def test_dead_cookie_is_refused(self):
        with TestClient(self.app, cookies={"aida_token": "garbage.token.value"}) as dead:
            self.assertEqual(dead.get("/api/auth/me").status_code, 401)

    def test_logout_clears_the_cookie(self):
        # The cookie is httpOnly, so the client cannot expire it itself:
        # without a logout endpoint it would survive a client-side sign
        # out and be re-adopted on the next request.
        response = self.client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 200)
        self.assertIn("aida_token", response.headers.get("set-cookie", ""))

    def test_logout_then_cookie_is_rejected(self):
        self.client.post("/api/auth/logout")
        token = self.setup.cookies["aida_token"]
        with TestClient(self.app, cookies={"aida_token": token}) as after:
            self.assertEqual(after.get("/api/auth/me").status_code, 401)


class _RecordingRouter:
    """Captures the two roles instead of calling a provider."""

    def __init__(self):
        self.user_content = None
        self.system_content = None

    def generate(self, provider, model, prompt, system_prompt=None):
        self.user_content = prompt
        self.system_content = system_prompt
        return "{}"

    def embed_texts(self, provider, model, texts):
        return [[1.0, 0.0] for _ in texts]

    def get_models(self, provider):
        return ["openrouter/free"]


class SimilarityTests(unittest.TestCase):
    def test_mismatched_dimensions_are_not_similar(self):
        """zip would truncate and yield a number that is not a cosine."""

        self.assertEqual(cosine_similarity([0.9, 0.1], [0.9, 0.1, 0.5]), 0.0)
        self.assertEqual(cosine_similarity([0.9, 0.1, 0.5], [0.9, 0.1]), 0.0)

    def test_matching_dimensions_are_unaffected(self):
        self.assertEqual(
            pytest.approx(cosine_similarity([0.9, 0.1], [0.9, 0.1]), abs=1e-9), 1.0
        )
        self.assertEqual(
            pytest.approx(cosine_similarity([1.0, 0.0], [0.0, 1.0]), abs=1e-9), 0.0
        )


class RetryExhaustionTests(unittest.TestCase):
    def test_retry_exhaustion_reraises_the_original(self):
        """
        tenacity wraps the last failure in RetryError unless reraise is
        set. The API layer does not catch RetryError, so a failing
        upstream must surface the original exception instead.
        """

        import providers.openrouter_provider as provider_module

        def always_429(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=httpx.Request("POST", "https://openrouter.ai/api/v1/x"),
                response=httpx.Response(429),
            )

        provider = object.__new__(provider_module.OpenRouterProvider)
        provider.headers = {"Authorization": "Bearer x"}

        with mock.patch.object(httpx, "post", side_effect=always_429) as posted, \
                self.assertRaises(httpx.HTTPStatusError):
            provider.generate("model", "prompt")

        self.assertEqual(posted.call_count, 3, "expected 3 retries")

    def test_short_embedding_batch_is_an_error_not_a_silent_gap(self):
        """
        The caller matches vectors to items positionally, so a provider
        that returns fewer vectors than texts must fail loudly.
        """

        import providers.openrouter_provider as provider_module

        def short_batch(*args, **kwargs):
            response = mock.Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {"data": [{"embedding": [0.1, 0.2]}]}
            return response

        provider = object.__new__(provider_module.OpenRouterProvider)
        provider.headers = {"Authorization": "Bearer x"}

        with mock.patch.object(httpx, "post", short_batch), \
                self.assertRaises(ValueError):
            provider.embed_texts("model", ["a", "b", "c"])
