from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

# Pin the environment before sentinel.config imports and runs load_dotenv().
# Tests must not change behaviour based on whatever is in a developer's local
# .env - a shakedown provider or demo profile there would silently alter what
# the suite asserts.
os.environ["SENTINEL_FAKE_LLM"] = "1"
os.environ["SENTINEL_PROFILE"] = "dev"
os.environ["SENTINEL_LLM_PROVIDER"] = "anthropic"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    from sentinel.store import repo

    repo.reset(tmp_path / "test.db")
    repo.seed_patterns()
    yield repo


@pytest.fixture
def make_scope():
    from sentinel.scope import ScopeDraft, create_scope

    def _make(
        target_id="support_bot",
        categories=("authority_impersonation", "multiturn_erosion"),
        exclusions=(),
        hours=2,
    ):
        return create_scope(
            ScopeDraft(
                target_id=target_id,
                target_endpoint=f"inproc://{target_id}",
                allowed_attack_categories=list(categories),
                exclusions=list(exclusions),
                authorizer="test-authorizer",
                expiry_timestamp=datetime.now(timezone.utc) + timedelta(hours=hours),
            )
        )

    return _make


@pytest.fixture(autouse=True)
def clean_ledger():
    from sentinel.targets import tools

    tools.reset_ledger()
    yield
    tools.reset_ledger()
