"""Sample data must satisfy the domain contracts and reference real files."""

import pytest

from underwriter.ingestion.documents import DATA_DIR, load_application

APPS = sorted((DATA_DIR / "applications").glob("APP-*.json"))


def test_there_are_sample_applications():
    assert len(APPS) >= 8


@pytest.mark.parametrize("path", APPS, ids=lambda p: p.stem)
def test_application_validates_and_documents_exist(path):
    app = load_application(path)
    for doc in app.documents:
        assert (DATA_DIR / doc.path).exists(), doc.path


def test_policy_document_exists():
    assert (DATA_DIR / "policies" / "unsecured_personal_lending_policy.md").exists()
