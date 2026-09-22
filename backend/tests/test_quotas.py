"""What one account may hold, and what happens when it holds that much."""

from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from grod.main import API_PREFIX
from grod.quotas.models import AccountLimits

USAGE = f"{API_PREFIX}/account/usage"
BUCKETS = f"{API_PREFIX}/storage/buckets"
QUEUES = f"{API_PREFIX}/queues"

CONTENT = b"file contents that take up room\n"


async def allow(db: AsyncSession, account: dict[str, Any], **limits: int) -> None:
    """Give one account limits of its own."""
    db.add(AccountLimits(owner_id=UUID(str(account["id"])), **limits))
    await db.commit()


async def test_a_fresh_account_holds_nothing_and_gets_the_defaults(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    answer = await client.get(USAGE)
    assert answer.status_code == httpx.codes.OK, answer.text

    held = answer.json()
    assert held["storageBytes"] == 0
    assert held["buckets"] == 0
    assert held["limits"]["buckets"] > 0
    assert held["limits"]["storageBytes"] > 0


async def test_what_is_kept_shows_up_in_the_usage(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    await client.post(BUCKETS, json={"name": "my-files"})
    await client.put(f"{BUCKETS}/my-files/objects/note.txt", content=CONTENT)
    await client.post(QUEUES, json={"name": "jobs"})

    held = (await client.get(USAGE)).json()
    assert held["buckets"] == 1
    assert held["queues"] == 1
    assert held["files"] == 1
    assert held["storageBytes"] == len(CONTENT)


async def test_one_more_than_allowed_is_refused(
    client: httpx.AsyncClient, account: dict[str, Any], db_session: AsyncSession
) -> None:
    await allow(db_session, account, buckets=1)
    first = await client.post(BUCKETS, json={"name": "first"})
    assert first.status_code == httpx.codes.CREATED, first.text

    refused = await client.post(BUCKETS, json={"name": "second"})
    assert refused.status_code == httpx.codes.CONFLICT
    assert "buckets" in refused.json()["detail"]


async def test_a_file_that_would_not_fit_is_refused(
    client: httpx.AsyncClient, account: dict[str, Any], db_session: AsyncSession
) -> None:
    await allow(db_session, account, storage_bytes=len(CONTENT))
    await client.post(BUCKETS, json={"name": "tight"})

    fits = await client.put(f"{BUCKETS}/tight/objects/first.txt", content=CONTENT)
    assert fits.status_code == httpx.codes.CREATED, fits.text

    refused = await client.put(f"{BUCKETS}/tight/objects/second.txt", content=CONTENT)
    assert refused.status_code == httpx.codes.CONFLICT
    assert "storageBytes" in refused.json()["detail"]


async def test_the_limits_of_an_account_win_over_the_defaults(
    client: httpx.AsyncClient, account: dict[str, Any], db_session: AsyncSession
) -> None:
    await allow(db_session, account, queues=3)
    limits = (await client.get(USAGE)).json()["limits"]

    assert limits["queues"] == 3
    # The ones it was not given still come from the instance.
    assert limits["buckets"] > 0


@pytest.mark.parametrize(
    ("address", "body", "field"),
    [
        (f"{API_PREFIX}/queues", {"name": "queue"}, "queues"),
        (
            f"{API_PREFIX}/functions",
            {"name": "function", "runtime": "python", "source": "x"},
            "functions",
        ),
    ],
)
async def test_every_module_answers_the_same_way_at_its_limit(
    client: httpx.AsyncClient,
    account: dict[str, Any],
    db_session: AsyncSession,
    address: str,
    body: dict[str, Any],
    field: str,
) -> None:
    """The refusal is one shape, whatever ran out."""
    await allow(db_session, account, **{field: 0})

    refused = await client.post(address, json=body)
    assert refused.status_code == httpx.codes.CONFLICT, refused.text
    assert field in refused.json()["detail"]
