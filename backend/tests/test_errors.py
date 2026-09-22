"""Error reports gathered into issues."""

from typing import Any

import httpx
import pytest

from grod.errors import service
from grod.main import API_PREFIX
from tests.test_collaboration import sign_in
from tests.test_repositories import OTHER_EMAIL, OTHER_PASSWORD, register_other

SOURCES = f"{API_PREFIX}/errors/sources"
REPORT = f"{API_PREFIX}/report"
SOURCE_NAME = "shop"
SOURCE = f"{SOURCES}/{SOURCE_NAME}"

STACK = """Traceback (most recent call last):
  File "shop/basket.py", line 42, in dodaj
    return self.pozycje[indeks]
IndexError: list index out of range"""


@pytest.fixture
async def source(client: httpx.AsyncClient, account: dict[str, Any]) -> dict[str, Any]:
    del account
    response = await client.post(SOURCES, json={"name": SOURCE_NAME})
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    return created


def test_two_reports_of_the_same_problem_look_the_same() -> None:
    first = service._fingerprint("IndexError", STACK)
    # The message changes but the kind and the stack do not.
    again = service._fingerprint("IndexError", STACK)
    other = service._fingerprint("KeyError", STACK)

    assert first == again
    assert first != other


async def test_a_report_needs_a_key(client: httpx.AsyncClient, source: dict[str, Any]) -> None:
    del source
    without = await client.post(REPORT, json={"kind": "IndexError"})
    assert without.status_code == httpx.codes.UNAUTHORIZED

    wrong = await client.post(
        REPORT, json={"kind": "IndexError"}, headers={"X-Grod-Key": "grodczuj_nonsense"}
    )
    assert wrong.status_code == httpx.codes.UNAUTHORIZED


async def test_the_same_problem_is_counted_once(
    client: httpx.AsyncClient, source: dict[str, Any]
) -> None:
    headers = {"X-Grod-Key": source["key"]}

    for number in range(3):
        answered = await client.post(
            REPORT,
            json={
                "kind": "IndexError",
                "message": f"list index out of range ({number})",
                "stack": STACK,
                "environment": "production",
            },
            headers=headers,
        )
        assert answered.status_code == httpx.codes.ACCEPTED, answered.text

    issues = await client.get(f"{SOURCE}/issues")
    assert len(issues.json()) == 1, "three reports, one problem"
    assert issues.json()[0]["count"] == 3
    assert issues.json()[0]["kind"] == "IndexError"
    assert "basket.py" in issues.json()[0]["culprit"]

    read = await client.get(SOURCE)
    assert read.json()["issues"] == 1
    assert read.json()["reports"] == 3


async def test_a_different_problem_is_a_different_issue(
    client: httpx.AsyncClient, source: dict[str, Any]
) -> None:
    headers = {"X-Grod-Key": source["key"]}
    await client.post(REPORT, json={"kind": "IndexError", "stack": STACK}, headers=headers)
    await client.post(
        REPORT, json={"kind": "KeyError", "stack": "File 'inny.py', line 7"}, headers=headers
    )

    issues = await client.get(f"{SOURCE}/issues")

    assert {item["kind"] for item in issues.json()} == {"IndexError", "KeyError"}


async def test_the_reports_of_an_issue_keep_their_details(
    client: httpx.AsyncClient, source: dict[str, Any]
) -> None:
    headers = {"X-Grod-Key": source["key"]}
    await client.post(
        REPORT,
        json={
            "kind": "IndexError",
            "message": "an empty basket",
            "stack": STACK,
            "environment": "production",
            "release": "1.4.2",
            "context": {"user": "anna", "basket": 12},
        },
        headers=headers,
    )
    issue_id = (await client.get(f"{SOURCE}/issues")).json()[0]["id"]

    reports = await client.get(f"{SOURCE}/issues/{issue_id}/reports")

    assert len(reports.json()) == 1
    assert reports.json()[0]["environment"] == "production"
    assert reports.json()[0]["release"] == "1.4.2"
    assert reports.json()[0]["context"] == {"user": "anna", "basket": 12}
    assert "IndexError" in reports.json()[0]["stack"]


async def test_a_problem_that_comes_back_opens_again(
    client: httpx.AsyncClient, source: dict[str, Any]
) -> None:
    headers = {"X-Grod-Key": source["key"]}
    await client.post(REPORT, json={"kind": "IndexError", "stack": STACK}, headers=headers)
    issue_id = (await client.get(f"{SOURCE}/issues")).json()[0]["id"]

    resolved = await client.post(f"{SOURCE}/issues/{issue_id}/resolve")
    assert resolved.json()["resolved"] is True

    await client.post(REPORT, json={"kind": "IndexError", "stack": STACK}, headers=headers)

    read = await client.get(f"{SOURCE}/issues/{issue_id}")
    assert read.json()["resolved"] is False, "it happened again, so it is open again"


async def test_only_unresolved_problems_when_asked(
    client: httpx.AsyncClient, source: dict[str, Any]
) -> None:
    headers = {"X-Grod-Key": source["key"]}
    await client.post(REPORT, json={"kind": "IndexError", "stack": STACK}, headers=headers)
    await client.post(REPORT, json={"kind": "KeyError", "stack": "other"}, headers=headers)
    first = (await client.get(f"{SOURCE}/issues")).json()[0]["id"]
    await client.post(f"{SOURCE}/issues/{first}/resolve")

    open_ones = await client.get(f"{SOURCE}/issues", params={"resolved": "false"})

    assert len(open_ones.json()) == 1
    assert open_ones.json()[0]["id"] != first


async def test_somebody_elses_source_is_not_visible(
    client: httpx.AsyncClient, source: dict[str, Any]
) -> None:
    del source
    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)

    assert (await client.get(SOURCE)).status_code == httpx.codes.NOT_FOUND
    assert (await client.get(SOURCES)).json() == []
