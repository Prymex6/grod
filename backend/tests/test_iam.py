"""IAM: machine identities, and the permissions that travel across the cloud."""

from typing import Any

import httpx
import pytest

from grod.main import API_PREFIX
from tests.test_collaboration import OTHER_LOGIN, sign_in
from tests.test_repositories import OTHER_EMAIL, OTHER_PASSWORD, register_other

ACCOUNTS = f"{API_PREFIX}/iam/service-accounts"
GRANTS = f"{API_PREFIX}/iam/grants"
BUCKETS = f"{API_PREFIX}/storage/buckets"
QUEUES = f"{API_PREFIX}/queues"

BUCKET = "shared-storage"
QUEUE = "shared-queue"
GROUP = "deployment-team"


async def make_bucket(client: httpx.AsyncClient, name: str = BUCKET) -> dict[str, Any]:
    """Create a private bucket under whoever the client is signed in as."""
    response = await client.post(BUCKETS, json={"name": name})
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    return created


async def make_service_account(client: httpx.AsyncClient, name: str = "deployment") -> str:
    """Create a machine identity and return the token it signs in with."""
    response = await client.post(ACCOUNTS, json={"name": name})
    assert response.status_code == httpx.codes.CREATED, response.text
    token: str = response.json()["token"]
    return token


def as_service(token: str) -> dict[str, str]:
    """The header an application sends instead of a session cookie."""
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def bucket(client: httpx.AsyncClient, account: dict[str, Any]) -> dict[str, Any]:
    del account
    return await make_bucket(client)


async def test_a_token_is_shown_once_and_never_again(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    token = await make_service_account(client)
    assert token.startswith("grodsrv_")

    listed = await client.get(ACCOUNTS)
    assert [item["name"] for item in listed.json()] == ["deployment"]
    assert "token" not in listed.json()[0]


async def test_a_machine_does_not_inherit_what_its_owner_owns(
    client: httpx.AsyncClient, bucket: dict[str, Any]
) -> None:
    """Owning the machine is not the same as owning what it may touch."""
    del bucket
    token = await make_service_account(client)

    client.cookies.clear()
    refused = await client.get(f"{BUCKETS}/{BUCKET}", headers=as_service(token))
    assert refused.status_code == httpx.codes.NOT_FOUND

    empty = await client.get(BUCKETS, headers=as_service(token))
    assert empty.json() == []


async def test_a_grant_lets_a_machine_read_but_not_write(
    client: httpx.AsyncClient, bucket: dict[str, Any]
) -> None:
    token = await make_service_account(client)
    given = await client.post(
        GRANTS,
        json={
            "resourceKind": "bucket",
            "resourceId": bucket["id"],
            "subjectKind": "service",
            "subject": "deployment",
            "role": "viewer",
        },
    )
    assert given.status_code == httpx.codes.CREATED, given.text

    client.cookies.clear()
    read = await client.get(f"{BUCKETS}/{BUCKET}", headers=as_service(token))
    assert read.status_code == httpx.codes.OK
    assert read.json()["name"] == BUCKET

    listed = await client.get(BUCKETS, headers=as_service(token))
    assert [item["name"] for item in listed.json()] == [BUCKET]

    refused = await client.put(
        f"{BUCKETS}/{BUCKET}/objects/file.txt", content=b"not allowed", headers=as_service(token)
    )
    assert refused.status_code == httpx.codes.NOT_FOUND


async def test_a_stronger_role_opens_what_the_weaker_one_did_not(
    client: httpx.AsyncClient, bucket: dict[str, Any]
) -> None:
    token = await make_service_account(client)
    for role in ("viewer", "operator"):
        given = await client.post(
            GRANTS,
            json={
                "resourceKind": "bucket",
                "resourceId": bucket["id"],
                "subjectKind": "service",
                "subject": "deployment",
                "role": role,
            },
        )
        assert given.status_code == httpx.codes.CREATED, given.text

    client.cookies.clear()
    written = await client.put(
        f"{BUCKETS}/{BUCKET}/objects/file.txt", content=b"allowed", headers=as_service(token)
    )
    assert written.status_code == httpx.codes.CREATED, written.text

    # Taking the bucket down still belongs to whoever set it up.
    refused = await client.delete(f"{BUCKETS}/{BUCKET}", headers=as_service(token))
    assert refused.status_code == httpx.codes.NOT_FOUND


async def test_a_person_can_be_let_into_somebody_elses_bucket(
    client: httpx.AsyncClient, bucket: dict[str, Any]
) -> None:
    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    hidden = await client.get(f"{BUCKETS}/{BUCKET}")
    assert hidden.status_code == httpx.codes.NOT_FOUND

    await sign_in(client, email="anna.k@grod.dev", password="correct-horse-battery")
    given = await client.post(
        GRANTS,
        json={
            "resourceKind": "bucket",
            "resourceId": bucket["id"],
            "subjectKind": "user",
            "subject": OTHER_LOGIN,
            "role": "operator",
        },
    )
    assert given.status_code == httpx.codes.CREATED, given.text

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    written = await client.put(f"{BUCKETS}/{BUCKET}/objects/note.txt", content=b"od Piotra")
    assert written.status_code == httpx.codes.CREATED, written.text
    assert [item["name"] for item in (await client.get(BUCKETS)).json()] == [BUCKET]


async def test_a_grant_to_a_group_reaches_everybody_in_it(
    client: httpx.AsyncClient, bucket: dict[str, Any]
) -> None:
    await register_other(client)
    await sign_in(client, email="anna.k@grod.dev", password="correct-horse-battery")

    made = await client.post(
        f"{API_PREFIX}/groups", json={"slug": GROUP, "name": "Deployment team"}
    )
    assert made.status_code == httpx.codes.CREATED, made.text
    added = await client.post(
        f"{API_PREFIX}/groups/{GROUP}/members", json={"login": OTHER_LOGIN, "role": "developer"}
    )
    assert added.status_code == httpx.codes.CREATED, added.text

    given = await client.post(
        GRANTS,
        json={
            "resourceKind": "bucket",
            "resourceId": bucket["id"],
            "subjectKind": "group",
            "subject": GROUP,
            "role": "viewer",
        },
    )
    assert given.status_code == httpx.codes.CREATED, given.text

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    read = await client.get(f"{BUCKETS}/{BUCKET}")
    assert read.status_code == httpx.codes.OK


async def test_taking_a_permission_away_closes_the_door_again(
    client: httpx.AsyncClient, bucket: dict[str, Any]
) -> None:
    await register_other(client)
    await sign_in(client, email="anna.k@grod.dev", password="correct-horse-battery")
    given = await client.post(
        GRANTS,
        json={
            "resourceKind": "bucket",
            "resourceId": bucket["id"],
            "subjectKind": "user",
            "subject": OTHER_LOGIN,
            "role": "viewer",
        },
    )
    subject_id = given.json()["subjectId"]

    listed = await client.get(GRANTS, params={"resourceKind": "bucket", "resourceId": bucket["id"]})
    assert [item["subject"] for item in listed.json()] == [OTHER_LOGIN]

    removed = await client.delete(
        GRANTS,
        params={
            "resourceKind": "bucket",
            "resourceId": bucket["id"],
            "subjectKind": "user",
            "subjectId": subject_id,
        },
    )
    assert removed.status_code == httpx.codes.NO_CONTENT

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    assert (await client.get(f"{BUCKETS}/{BUCKET}")).status_code == httpx.codes.NOT_FOUND


async def test_only_somebody_who_may_change_a_resource_may_share_it(
    client: httpx.AsyncClient, bucket: dict[str, Any]
) -> None:
    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)

    refused = await client.post(
        GRANTS,
        json={
            "resourceKind": "bucket",
            "resourceId": bucket["id"],
            "subjectKind": "user",
            "subject": OTHER_LOGIN,
            "role": "admin",
        },
    )
    assert refused.status_code == httpx.codes.FORBIDDEN


async def test_a_machine_may_be_let_into_a_queue_and_nothing_else(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    """The same grants work for every cloud module, not only for storage."""
    del account
    made = await client.post(QUEUES, json={"name": QUEUE})
    assert made.status_code == httpx.codes.CREATED, made.text
    await make_bucket(client)
    token = await make_service_account(client, name="employee")

    given = await client.post(
        GRANTS,
        json={
            "resourceKind": "queue",
            "resourceId": made.json()["id"],
            "subjectKind": "service",
            "subject": "employee",
            "role": "operator",
        },
    )
    assert given.status_code == httpx.codes.CREATED, given.text

    client.cookies.clear()
    sent = await client.post(
        f"{QUEUES}/{QUEUE}/messages", json={"what": "make"}, headers=as_service(token)
    )
    assert sent.status_code == httpx.codes.CREATED, sent.text

    taken = await client.post(f"{QUEUES}/{QUEUE}/receive", headers=as_service(token))
    assert [message["body"] for message in taken.json()] == [{"what": "make"}]

    # Emptying the queue is a change, and the bucket was never mentioned.
    assert (
        await client.post(f"{QUEUES}/{QUEUE}/purge", headers=as_service(token))
    ).status_code == httpx.codes.NOT_FOUND
    assert (
        await client.get(f"{BUCKETS}/{BUCKET}", headers=as_service(token))
    ).status_code == httpx.codes.NOT_FOUND


async def test_a_deleted_machine_stops_answering(
    client: httpx.AsyncClient, bucket: dict[str, Any]
) -> None:
    token = await make_service_account(client)
    await client.post(
        GRANTS,
        json={
            "resourceKind": "bucket",
            "resourceId": bucket["id"],
            "subjectKind": "service",
            "subject": "deployment",
            "role": "viewer",
        },
    )
    removed = await client.delete(f"{ACCOUNTS}/deployment")
    assert removed.status_code == httpx.codes.NO_CONTENT

    client.cookies.clear()
    refused = await client.get(BUCKETS, headers=as_service(token))
    assert refused.status_code == httpx.codes.UNAUTHORIZED
