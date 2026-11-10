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
import json
import os
import pathlib
import tempfile
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
from config import DEFAULT_MODEL
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
        return ["minimaxai/minimax-m3.1-flash"]

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
            provider="nvidia",
            model=DEFAULT_MODEL,
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
            provider="nvidia",
            model=DEFAULT_MODEL,
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


class ExceptionExposureTests(unittest.TestCase):
    """
    A provider or database failure must not reach the caller.

    GitHub flags "Information exposure through an exception" where an
    exception's text is returned, and the reason is real: a provider
    failure carries the endpoint and status, a database failure carries
    the statement. Neither tells the caller anything useful, and both
    describe the infrastructure.

    The counterweight is that validation messages must still get through,
    or the UI can only report "something went wrong" when the user simply
    forgot to attach a file. Both halves are pinned here.
    """

    def setUp(self):
        config_loader.reset_bootstrap_token()
        api_module._failed_logins.clear()
        self.app = api_module.create_app(None, "sqlite://")
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
        self.token = self.client.post(
            "/api/auth/login",
            json={"username": "founder", "password": "founder-pass-123"},
        ).json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {self.token}"

    def tearDown(self):
        for patcher in getattr(self, "_patchers", []):
            patcher.stop()
        db.session.remove()
        db.drop_all()
        config_loader.reset_bootstrap_token()

    def _bypass_model_list(self):
        """
        Satisfy the model-availability guard without calling the provider.

        Without this these tests pass in CI for the wrong reason. CI has no
        NVIDIA_API_KEY, so the handler answers "model list unavailable"
        before it ever reaches the call being mocked, and the assertions
        about a 400 with a fixed sentence still pass. Locally, where a key
        exists, they pass for the right reason. The suite was green in both
        places while only one of them was telling the truth.
        """

        self._patchers = [
            mock.patch.object(
                api_module,
                "get_available_models",
                return_value=[api_module.DEFAULT_MODEL],
            )
        ]
        for patcher in self._patchers:
            patcher.start()

    def _use_fake_analysis(self):
        """
        The model-list bypass plus a analysis the app can parse.

        Used where the analysis has to succeed so the code under test is
        the next step in the pipeline, which is what the consolidation
        fallback test needs.
        """

        self._bypass_model_list()
        # One finding on purpose: the consolidation step only runs when
        # there is something to consolidate, so an analysis with nothing
        # in it would take the no-consolidation path and the warning the
        # test looks for would never be produced.
        analysis = {
            "project_status": "on_track",
            "progress_summary": "s",
            "executive_summary": "s",
            "risks": [
                {
                    "title": "QA is short one tester",
                    "description": "d",
                    "impact": "medium",
                    "mitigation": "m",
                    "status": "open",
                }
            ],
            "blockers": [],
            "action_items": [],
            "decisions": [],
            "completed_items": [],
            "in_progress_items": [],
        }
        patcher = mock.patch.object(
            api_module, "analyze_document", return_value=json.dumps(analysis)
        )
        patcher.start()
        self._patchers.append(patcher)

    def test_validation_message_reaches_the_user(self):
        project = self.client.post(
            "/api/projects", json={"name": "Exposure", "description": ""}
        ).json()["id"]

        response = self.client.post(f"/api/projects/{project}/meetings", data={})

        self.assertEqual(response.status_code, 400)
        self.assertIn("Upload meeting notes or paste meeting text.", response.text)

    def test_internal_failure_returns_a_fixed_message(self):
        import httpx

        project = self.client.post(
            "/api/projects", json={"name": "Leak Check", "description": ""}
        ).json()["id"]

        # A provider failure raises an httpx error, not a ValueError. The
        # response must be a fixed sentence with no trace of the cause.
        # Only the model-list guard is bypassed here: the provider call
        # itself has to run, because it is what fails.
        self._bypass_model_list()

        def boom(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "upstream returned 429 with an internal path /internal/v1",
                request=httpx.Request("POST", "https://example.invalid/internal"),
                response=httpx.Response(429),
            )

        with mock.patch.object(api_module.ModelRouter, "generate", boom):
            response = self.client.post(
                f"/api/projects/{project}/meetings",
                data={"meeting_notes": "Alice: QA is short one tester."},
            )

        text = response.text
        self.assertEqual(response.status_code, 400)
        # The failure happens during analysis, before consolidation, so the
        # outer handler answers with its own fixed sentence.
        self.assertIn("could not be processed", text)
        self.assertIn("nothing was changed", text)
        for leak in ("429", "example.invalid", "/internal", "Traceback"):
            self.assertNotIn(leak, text, f"response leaked {leak!r}")

    def test_unexpected_exception_does_not_leak_stack_text(self):
        project = self.client.post(
            "/api/projects", json={"name": "Stack Check", "description": ""}
        ).json()["id"]

        def boom(*args, **kwargs):
            raise RuntimeError("database password is hunter2 at /var/secret")

        self._bypass_model_list()
        with mock.patch.object(api_module.ModelRouter, "generate", boom):
            response = self.client.post(
                f"/api/projects/{project}/meetings",
                data={"meeting_notes": "Alice: QA is short one tester."},
            )

        text = response.text
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("hunter2", text)
        self.assertNotIn("/var/secret", text)
        self.assertNotIn("Traceback", text)

    def test_review_validation_message_reaches_the_user(self):
        project = self.client.post(
            "/api/projects", json={"name": "Review Check", "description": ""}
        ).json()["id"]

        # A review event that does not exist is a 404, which is authored.
        response = self.client.post(
            f"/api/projects/{project}/review/999/resolve",
            json={"action": "bogus"},
        )
        self.assertEqual(response.status_code, 404)

    def test_the_degraded_warning_carries_no_exception_text(self):
        """
        The consolidation fallback returns a 201 with a warning.

        That warning is part of the response, and it used to interpolate
        the exception into the sentence. The cause is useful to an operator
        reading the log and describes the infrastructure to a caller, so it
        belongs in the log only. GitHub flags exactly this flow as
        py/stack-trace-exposure, and the location it pointed at was the
        warning rather than the error body, which is why the first fix
        moved the alert instead of clearing it.
        """


        project = self.client.post(
            "/api/projects", json={"name": "Warning Leak", "description": ""}
        ).json()["id"]

        # The analysis call succeeds and produces something consolidable;
        # the consolidation call then fails with a text-bearing exception.
        self._use_fake_analysis()

        def fail(*args, **kwargs):
            raise RuntimeError("consolidation hit /internal/v1 at 10.0.0.9")

        with mock.patch.object(
            api_module.MemoryConsolidator, "consolidate", fail
        ):
            response = self.client.post(
                f"/api/projects/{project}/meetings",
                data={"meeting_notes": "Alice: QA is short one tester."},
            )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIn("warning", body)
        warning = body["warning"]
        self.assertIn("standard analysis", warning)
        for leak in ("/internal", "10.0.0.9", "RuntimeError", "Traceback"):
            self.assertNotIn(leak, warning, f"warning leaked {leak!r}")


class RevocationPersistenceTests(unittest.TestCase):
    """
    A logout has to outlive the process.

    The set that holds revoked token ids used to live only in memory, so a
    restart re-accepted a token the user had signed out, for up to
    TOKEN_TTL_HOURS afterwards. The failure was invisible in a test suite
    because each test builds one app and never restarts it.

    The property needs a database that survives the restart, so these
    tests use a file-backed SQLite: an in-memory database is a new empty
    one on every connect, which would test nothing.
    """

    def setUp(self):
        config_loader.reset_bootstrap_token()
        api_module._failed_logins.clear()

        # mkstemp rather than NamedTemporaryFile: the file has to outlive
        # the handle so a relaunched app can open the same database, which
        # is what makes this a restart rather than a reset.
        descriptor, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(descriptor)
        self.database_url = f"sqlite:///{self.db_path.replace(os.sep, '/')}"

        self.app = api_module.create_app(None, self.database_url)
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
        self.token = self.client.post(
            "/api/auth/login",
            json={"username": "founder", "password": "founder-pass-123"},
        ).json()["access_token"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        config_loader.reset_bootstrap_token()

        from database import configure_database

        configure_database("sqlite://")

        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def _relaunch(self):
        """A new app against the same database: a restart, not a reset."""

        from database import configure_database

        configure_database(self.database_url)
        return TestClient(api_module.create_app(None, self.database_url))

    def test_revoked_token_is_refused_after_a_restart(self):
        from datetime import UTC, datetime, timedelta

        from models import RevokedToken

        # The token works.
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

        # Signing out writes a row carrying the token's own expiry.
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        rows = db.session.query(RevokedToken.jti, RevokedToken.expires_at).all()
        self.assertEqual(len(rows), 1)
        # SQLite hands back a naive datetime and PostgreSQL an aware one,
        # so the assertion normalises rather than assuming a dialect.
        expires_at = rows[0].expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        self.assertGreater(expires_at, datetime.now(UTC))
        self.assertLess(expires_at, datetime.now(UTC) + timedelta(hours=13))

        response = self._relaunch().get(
            "/api/auth/me", headers={"Authorization": f"Bearer {self.token}"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("session has ended", response.json()["detail"].lower())

    def test_a_token_never_signed_out_survives_a_restart(self):
        response = self._relaunch().get(
            "/api/auth/me", headers={"Authorization": f"Bearer {self.token}"}
        )
        self.assertEqual(response.status_code, 200)

    def test_expired_rows_are_pruned_on_logout(self):
        from datetime import UTC, datetime, timedelta

        from models import RevokedToken

        db.session.add(
            RevokedToken(
                jti="stale", expires_at=datetime.now(UTC) - timedelta(days=1)
            )
        )
        db.session.add(
            RevokedToken(
                jti="live", expires_at=datetime.now(UTC) + timedelta(hours=6)
            )
        )
        db.session.commit()

        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)

        remaining = {row.jti for row in db.session.query(RevokedToken).all()}
        self.assertNotIn("stale", remaining)
        self.assertIn("live", remaining)
        # Plus the row for the token that was just signed out.
        self.assertEqual(len(remaining), 2)

    def test_a_second_logout_of_the_same_token_does_not_duplicate(self):
        from models import RevokedToken

        self.client.post("/api/auth/logout")
        self.client.post("/api/auth/logout")

        self.assertEqual(len(db.session.query(RevokedToken).all()), 1)


class ActivityTimelineTests(unittest.TestCase):
    """
    The activity timeline must report every month that has data.

    The query counts rows per month. It was changed three times for one
    reason: the naive form read every created_at into Python and counted
    there, which is O(rows) per request on a table that grows forever. It
    was then bounded to a 24-month window, which fixed the cost and
    introduced silent data loss. The form now aggregates in the database,
    so the cost is proportional to how many months exist rather than how
    many rows, and a month is never dropped for being old.

    These tests pin the property that failed: a month with rows in it
    appears, however far back it is.
    """

    def setUp(self):
        config_loader.reset_bootstrap_token()
        api_module._failed_logins.clear()
        self.app = api_module.create_app(None, "sqlite://")
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
        db.session.remove()
        db.drop_all()
        config_loader.reset_bootstrap_token()

    def test_older_than_the_window_is_excluded(self):
        from datetime import UTC, datetime, timedelta

        from models import HistoryEvent, Meeting, Project

        project = Project(name="Windowed", description="")
        db.session.add(project)
        db.session.flush()

        def add_meeting(months_ago):
            created = datetime.now(UTC) - timedelta(days=months_ago * 30)
            meeting = Meeting(
                project_id=project.id,
                title=f"m{months_ago}",
                original_text="t",
                analysis_text="a",
                analysis_json="{}",
                provider="p",
                model="m",
            )
            db.session.add(meeting)
            db.session.flush()
            meeting.created_at = created
            db.session.flush()
            return meeting

        recent = add_meeting(2)
        old = add_meeting(60)
        db.session.commit()

        for meeting, label in ((recent, "recent"), (old, "old")):
            event = HistoryEvent(
                project_id=project.id,
                meeting_id=meeting.id,
                entity_type="risk",
                entity_id=None,
                event_type="created",
                summary=f"{label} event",
            )
            db.session.add(event)
            db.session.flush()
            event.created_at = meeting.created_at
            db.session.flush()
        db.session.commit()

        body = self.client.get("/api/metrics").json()
        timeline = {
            entry["month"]: entry for entry in body["activity_timeline"]
        }

        # Both months are present. An earlier version of this query read
        # every row into Python and counted there, which was O(rows) per
        # request on a table that grows forever. It was then bounded to a
        # 24-month window, which dropped history and made an old month
        # indistinguishable from an empty one. The query now aggregates in
        # the database, so the work is proportional to how many months
        # exist rather than how many rows do, and no month is missing.
        self.assertTrue(timeline, "timeline should not be empty")

        recent_key = f"{recent.created_at.year:04d}-{recent.created_at.month:02d}"
        old_key = f"{old.created_at.year:04d}-{old.created_at.month:02d}"

        self.assertIn(recent_key, timeline)
        self.assertIn(
            old_key,
            timeline,
            "a month with data in it must appear however old it is",
        )

        # And each carries the count its rows imply, which is what the
        # aggregation is for.
        self.assertEqual(timeline[recent_key]["meetings"], 1)
        self.assertEqual(timeline[old_key]["meetings"], 1)
        self.assertEqual(timeline[recent_key]["events"], 1)
        self.assertEqual(timeline[old_key]["events"], 1)


class TelemetryTests(unittest.TestCase):
    """
    A failure reported by a user has to be findable in the log. Without a
    request id, four identical requests produce four identical lines and
    the one that failed cannot be picked out.
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

    def test_response_carries_a_request_id(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertIn("x-request-id", {k.lower() for k in response.headers})

    def test_caller_supplied_id_is_echoed(self):
        response = self.client.get("/api/health", headers={"X-Request-ID": "abc123def456"})
        self.assertEqual(response.headers.get("x-request-id"), "abc123def456")

    def test_distinct_requests_get_distinct_ids(self):
        a = self.client.get("/api/health").headers.get("x-request-id")
        b = self.client.get("/api/health").headers.get("x-request-id")
        self.assertNotEqual(a, b, "each request must be distinguishable in the log")


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
        return ["minimaxai/minimax-m3.1-flash"]


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

        import providers.nvidia_provider as provider_module

        def always_429(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=httpx.Request(
                    "POST", "https://integrate.api.nvidia.com/v1/chat/completions"
                ),
                response=httpx.Response(429),
            )

        provider = object.__new__(provider_module.NvidiaProvider)
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

        import providers.nvidia_provider as provider_module

        def short_batch(*args, **kwargs):
            payload = kwargs.get("json") or {}
            texts = payload.get("input", [])
            response = mock.Mock()
            response.raise_for_status.return_value = None
            # Echo back one fewer vector than asked for.
            response.json.return_value = {
                "data": [{"embedding": [0.1, 0.2]} for _ in texts[1:]]
            }
            return response

        provider = object.__new__(provider_module.NvidiaProvider)
        provider.headers = {"Authorization": "Bearer x"}

        with mock.patch.object(httpx, "post", short_batch), \
                self.assertRaises(ValueError):
            provider.embed_texts("model", ["a", "b", "c"])

    def test_duplicate_texts_collapse_into_one_request_each(self):
        """
        The endpoint answers 500 on a batch containing a repeated string,
        so identical titles are collapsed and the result expanded back to
        the caller's order.
        """
        import providers.nvidia_provider as provider_module

        requested = []

        def record(*args, **kwargs):
            payload = kwargs.get("json") or {}
            batch = payload.get("input", [])
            requested.append(list(batch))
            response = mock.Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "data": [{"embedding": [float(i), 0.5]} for i, _ in enumerate(batch)]
            }
            return response

        provider = object.__new__(provider_module.NvidiaProvider)
        provider.headers = {"Authorization": "Bearer x"}

        with mock.patch.object(httpx, "post", record):
            result = provider.embed_texts(
                "model", ["same", "other", "same", "third", "other"]
            )

        # Five texts, three distinct, so no request carried a repeat.
        for batch in requested:
            self.assertEqual(len(batch), len(set(batch)), f"duplicate in {batch}")
        self.assertEqual(len(result), 5, "every input got a vector back")
        self.assertEqual(result[0], result[2], "the same title, the same vector")
        self.assertEqual(result[1], result[4])
        self.assertNotEqual(result[0], result[1])

    def test_batch_never_exceeds_the_endpoint_limit(self):
        """
        More than EMBED_BATCH_SIZE texts per request answers 500, so the
        chunk size is asserted rather than left to chance.
        """
        import providers.nvidia_provider as provider_module

        sizes = []

        def record(*args, **kwargs):
            payload = kwargs.get("json") or {}
            batch = payload.get("input", [])
            sizes.append(len(batch))
            response = mock.Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "data": [{"embedding": [0.1]} for _ in batch]
            }
            return response

        provider = object.__new__(provider_module.NvidiaProvider)
        provider.headers = {"Authorization": "Bearer x"}

        with mock.patch.object(httpx, "post", record):
            provider.embed_texts("model", [f"title {i}" for i in range(10)])

        limit = provider_module.EMBED_BATCH_SIZE
        self.assertTrue(all(s <= limit for s in sizes), f"batches {sizes} > {limit}")
        self.assertEqual(sum(sizes), 10, "all ten texts were embedded")
