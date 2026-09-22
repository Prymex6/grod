"""Buckets, the files inside them and who may read them."""

from typing import Any

import httpx
import pytest

from grod.main import API_PREFIX
from grod.storage import service
from tests.test_collaboration import sign_in
from tests.test_repositories import OTHER_EMAIL, OTHER_PASSWORD, register_other

BUCKETS = f"{API_PREFIX}/storage/buckets"
BUCKET = "my-storage"
CONTENT = b"file contents kept in a bucket\n"


@pytest.fixture
async def bucket(client: httpx.AsyncClient, account: dict[str, Any]) -> dict[str, Any]:
    del account
    response = await client.post(BUCKETS, json={"name": BUCKET})
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    return created


def test_a_key_may_not_walk_out_of_its_bucket() -> None:
    assert service.check_key("photos/summer/beach.jpg") == "photos/summer/beach.jpg"
    assert service.check_key("/leading-slash.txt") == "leading-slash.txt"

    for wrong in ("", "/", "../secret", "photos/../../secret", "a//b"):
        with pytest.raises(service.InvalidKeyError):
            service.check_key(wrong)


async def test_a_file_comes_back_as_it_went_in(
    client: httpx.AsyncClient, bucket: dict[str, Any]
) -> None:
    del bucket
    address = f"{BUCKETS}/{BUCKET}/objects/photos/summer/beach.jpg"

    written = await client.put(address, content=CONTENT, headers={"Content-Type": "image/jpeg"})
    assert written.status_code == httpx.codes.CREATED, written.text
    assert written.json()["size"] == len(CONTENT)
    assert written.json()["contentType"] == "image/jpeg"

    read = await client.get(address)
    assert read.content == CONTENT
    assert read.headers["content-type"].startswith("image/jpeg")


async def test_the_listing_can_be_narrowed_to_a_prefix(
    client: httpx.AsyncClient, bucket: dict[str, Any]
) -> None:
    del bucket
    for key in ("photos/summer/a.jpg", "photos/winter/b.jpg", "documents/contract.pdf"):
        await client.put(f"{BUCKETS}/{BUCKET}/objects/{key}", content=CONTENT)

    everything = await client.get(f"{BUCKETS}/{BUCKET}/objects")
    assert len(everything.json()) == 3

    summer = await client.get(f"{BUCKETS}/{BUCKET}/objects", params={"prefix": "photos/summer/"})
    assert [item["key"] for item in summer.json()] == ["photos/summer/a.jpg"]

    read_back = await client.get(f"{BUCKETS}/{BUCKET}")
    assert read_back.json()["objects"] == 3
    assert read_back.json()["bytes"] == 3 * len(CONTENT)


async def test_writing_the_same_key_replaces_the_file(
    client: httpx.AsyncClient, bucket: dict[str, Any]
) -> None:
    del bucket
    address = f"{BUCKETS}/{BUCKET}/objects/note.txt"
    await client.put(address, content=b"first")
    await client.put(address, content=b"second")

    listed = await client.get(f"{BUCKETS}/{BUCKET}/objects")
    assert len(listed.json()) == 1
    assert (await client.get(address)).content == b"second"

    removed = await client.delete(address)
    assert removed.status_code == httpx.codes.NO_CONTENT
    assert (await client.get(address)).status_code == httpx.codes.NOT_FOUND


async def test_a_private_bucket_stays_private(
    client: httpx.AsyncClient, bucket: dict[str, Any]
) -> None:
    del bucket
    address = f"{BUCKETS}/{BUCKET}/objects/note.txt"
    await client.put(address, content=CONTENT)

    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)

    assert (await client.get(f"{BUCKETS}/{BUCKET}")).status_code == httpx.codes.NOT_FOUND
    assert (await client.get(address)).status_code == httpx.codes.NOT_FOUND
    assert (
        await client.put(address, content=b"someone elses")
    ).status_code == httpx.codes.NOT_FOUND


async def test_a_public_bucket_is_open_to_everybody(
    client: httpx.AsyncClient, bucket: dict[str, Any]
) -> None:
    del bucket
    address = f"{BUCKETS}/{BUCKET}/objects/note.txt"
    await client.put(address, content=CONTENT)
    opened = await client.patch(f"{BUCKETS}/{BUCKET}", json={"access": "public"})
    assert opened.json()["access"] == "public"

    client.cookies.clear()
    read = await client.get(address)

    assert read.status_code == httpx.codes.OK, "a visitor without an account may read it"
    assert read.content == CONTENT
    # Reading is open; writing still is not.
    assert (
        await client.put(address, content=b"someone elses")
    ).status_code == httpx.codes.UNAUTHORIZED


async def test_names_are_unique_and_look_like_host_names(
    client: httpx.AsyncClient, bucket: dict[str, Any]
) -> None:
    del bucket
    again = await client.post(BUCKETS, json={"name": BUCKET})
    assert again.status_code == httpx.codes.CONFLICT

    wrong = await client.post(BUCKETS, json={"name": "My storage"})
    assert wrong.status_code == httpx.codes.UNPROCESSABLE_ENTITY


async def test_deleting_a_bucket_takes_its_files_with_it(
    client: httpx.AsyncClient, bucket: dict[str, Any]
) -> None:
    from uuid import UUID

    await client.put(f"{BUCKETS}/{BUCKET}/objects/note.txt", content=CONTENT)
    path = service.bucket_path(UUID(bucket["id"]))
    assert path.is_dir()

    removed = await client.delete(f"{BUCKETS}/{BUCKET}")

    assert removed.status_code == httpx.codes.NO_CONTENT
    assert not path.exists()
    assert (await client.get(f"{BUCKETS}/{BUCKET}")).status_code == httpx.codes.NOT_FOUND
