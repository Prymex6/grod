"""The container registry: pushing an image, pulling it and who may do either."""

import base64
import hashlib
import json
from typing import Any
from uuid import UUID

import httpx
import pytest

from grod.artifacts.registry import storage
from grod.main import API_PREFIX
from tests.test_collaboration import OTHER_LOGIN, sign_in
from tests.test_repositories import (
    OTHER_EMAIL,
    OTHER_PASSWORD,
    SLUG,
    create_project,
    register_other,
)

TOKENS = f"{API_PREFIX}/tokens"
NAME = f"anna.k/{SLUG}"
V2 = f"/v2/{NAME}"

CONFIG = b'{"architecture":"amd64","os":"linux"}'
LAYER = b"warstwa obrazu kontenera\n"


def digest_of(body: bytes) -> str:
    return f"sha256:{hashlib.sha256(body).hexdigest()}"


def basic(token: str) -> dict[str, str]:
    """What `docker login` sends: the login with a token as the password."""
    pair = base64.b64encode(f"anna.k:{token}".encode()).decode()
    return {"Authorization": f"Basic {pair}"}


def manifest_of(config: bytes, layers: list[bytes]) -> bytes:
    """A manifest of the shape the container tools push."""
    return json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "config": {
                "mediaType": "application/vnd.docker.container.image.v1+json",
                "size": len(config),
                "digest": digest_of(config),
            },
            "layers": [
                {
                    "mediaType": "application/vnd.docker.image.rootfs.diff.tar.gzip",
                    "size": len(layer),
                    "digest": digest_of(layer),
                }
                for layer in layers
            ],
        }
    ).encode()


async def make_token(client: httpx.AsyncClient) -> str:
    response = await client.post(
        TOKENS, json={"name": "Docker", "scopes": ["repo:read", "repo:write"]}
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    value: str = response.json()["value"]
    return value


async def push_blob(client: httpx.AsyncClient, token: str, body: bytes) -> str:
    """Push one blob the way a container tool does: open, send, close."""
    started = await client.post(f"{V2}/blobs/uploads/", headers=basic(token))
    assert started.status_code == httpx.codes.ACCEPTED, started.text
    location = started.headers["location"]

    sent = await client.patch(location, content=body, headers=basic(token))
    assert sent.status_code == httpx.codes.ACCEPTED, sent.text

    digest = digest_of(body)
    done = await client.put(f"{location}?digest={digest}", headers=basic(token))
    assert done.status_code == httpx.codes.CREATED, done.text
    assert done.headers["docker-content-digest"] == digest
    return digest


@pytest.fixture
async def pushable(client: httpx.AsyncClient, account: dict[str, Any]) -> str:
    """A project of the signed-in account, and a token that may push to it."""
    del account
    await create_project(client)
    return await make_token(client)


async def test_the_registry_says_what_it_is(client: httpx.AsyncClient) -> None:
    answer = await client.get("/v2/")
    assert answer.status_code == httpx.codes.OK
    assert answer.headers["docker-distribution-api-version"] == "registry/2.0"


async def test_a_bad_token_is_refused_at_the_door(client: httpx.AsyncClient, pushable: str) -> None:
    del pushable
    refused = await client.get("/v2/", headers=basic("grod_wrong_token"))
    assert refused.status_code == httpx.codes.UNAUTHORIZED
    assert refused.headers["www-authenticate"].startswith("Basic ")


async def test_an_image_comes_back_exactly_as_it_went_in(
    client: httpx.AsyncClient, pushable: str
) -> None:
    config_digest = await push_blob(client, pushable, CONFIG)
    layer_digest = await push_blob(client, pushable, LAYER)

    body = manifest_of(CONFIG, [LAYER])
    written = await client.put(
        f"{V2}/manifests/latest",
        content=body,
        headers={
            **basic(pushable),
            "Content-Type": "application/vnd.docker.distribution.manifest.v2+json",
        },
    )
    assert written.status_code == httpx.codes.CREATED, written.text
    assert written.headers["docker-content-digest"] == digest_of(body)

    read = await client.get(f"{V2}/manifests/latest", headers=basic(pushable))
    assert read.content == body
    assert read.headers["content-type"].startswith("application/vnd.docker")

    by_digest = await client.get(f"{V2}/manifests/{digest_of(body)}", headers=basic(pushable))
    assert by_digest.content == body

    layer = await client.get(f"{V2}/blobs/{layer_digest}", headers=basic(pushable))
    assert layer.content == LAYER
    config = await client.get(f"{V2}/blobs/{config_digest}", headers=basic(pushable))
    assert config.content == CONFIG


async def test_a_layer_already_there_is_not_sent_twice(
    client: httpx.AsyncClient, pushable: str
) -> None:
    digest = await push_blob(client, pushable, LAYER)

    known = await client.head(f"{V2}/blobs/{digest}", headers=basic(pushable))
    assert known.status_code == httpx.codes.OK
    assert known.headers["content-length"] == str(len(LAYER))

    missing = await client.head(
        f"{V2}/blobs/{digest_of(b'nothing like this here')}", headers=basic(pushable)
    )
    assert missing.status_code == httpx.codes.NOT_FOUND


async def test_a_blob_that_is_not_what_it_claims_is_thrown_away(
    client: httpx.AsyncClient, pushable: str
) -> None:
    started = await client.post(f"{V2}/blobs/uploads/", headers=basic(pushable))
    location = started.headers["location"]
    await client.patch(location, content=LAYER, headers=basic(pushable))

    lie = digest_of(b"something else")
    refused = await client.put(f"{location}?digest={lie}", headers=basic(pushable))
    assert refused.status_code == httpx.codes.BAD_REQUEST
    assert refused.json()["errors"][0]["code"] == "DIGEST_INVALID"

    gone = await client.head(f"{V2}/blobs/{lie}", headers=basic(pushable))
    assert gone.status_code == httpx.codes.NOT_FOUND


async def test_a_manifest_over_missing_layers_is_refused(
    client: httpx.AsyncClient, pushable: str
) -> None:
    """A registry that took this would hand out an image nobody can run."""
    await push_blob(client, pushable, CONFIG)
    body = manifest_of(CONFIG, [LAYER])

    refused = await client.put(f"{V2}/manifests/latest", content=body, headers=basic(pushable))
    assert refused.status_code == httpx.codes.BAD_REQUEST
    assert refused.json()["errors"][0]["code"] == "MANIFEST_BLOB_UNKNOWN"
    assert digest_of(LAYER) in refused.json()["errors"][0]["message"]


async def test_one_upload_in_a_single_call(client: httpx.AsyncClient, pushable: str) -> None:
    digest = digest_of(LAYER)
    written = await client.post(
        f"{V2}/blobs/uploads/?digest={digest}", content=LAYER, headers=basic(pushable)
    )
    assert written.status_code == httpx.codes.CREATED, written.text
    assert (await client.head(f"{V2}/blobs/{digest}", headers=basic(pushable))).status_code == (
        httpx.codes.OK
    )


async def test_tags_are_listed_and_a_tag_can_be_moved(
    client: httpx.AsyncClient, pushable: str
) -> None:
    await push_blob(client, pushable, CONFIG)
    await push_blob(client, pushable, LAYER)
    body = manifest_of(CONFIG, [LAYER])
    for tag in ("latest", "1.0"):
        await client.put(f"{V2}/manifests/{tag}", content=body, headers=basic(pushable))

    listed = await client.get(f"{V2}/tags/list", headers=basic(pushable))
    assert listed.json() == {"name": NAME, "tags": ["1.0", "latest"]}

    # The same manifest under two names is kept once.
    removed = await client.delete(f"{V2}/manifests/1.0", headers=basic(pushable))
    assert removed.status_code == httpx.codes.ACCEPTED
    still = await client.get(f"{V2}/manifests/latest", headers=basic(pushable))
    assert still.status_code == httpx.codes.OK


async def test_taking_an_image_down_by_digest_takes_its_tags_with_it(
    client: httpx.AsyncClient, pushable: str
) -> None:
    await push_blob(client, pushable, CONFIG)
    await push_blob(client, pushable, LAYER)
    body = manifest_of(CONFIG, [LAYER])
    await client.put(f"{V2}/manifests/latest", content=body, headers=basic(pushable))

    removed = await client.delete(f"{V2}/manifests/{digest_of(body)}", headers=basic(pushable))
    assert removed.status_code == httpx.codes.ACCEPTED
    assert (await client.get(f"{V2}/tags/list", headers=basic(pushable))).json()["tags"] == []


async def test_a_stranger_sees_nothing_of_a_private_repository(
    client: httpx.AsyncClient, pushable: str
) -> None:
    await push_blob(client, pushable, CONFIG)
    await push_blob(client, pushable, LAYER)
    body = manifest_of(CONFIG, [LAYER])
    await client.put(f"{V2}/manifests/latest", content=body, headers=basic(pushable))

    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    other = await client.post(TOKENS, json={"name": "A stranger", "scopes": ["repo:read"]})
    pair = base64.b64encode(f"{OTHER_LOGIN}:{other.json()['value']}".encode()).decode()

    hidden = await client.get(f"{V2}/manifests/latest", headers={"Authorization": f"Basic {pair}"})
    assert hidden.status_code == httpx.codes.NOT_FOUND
    assert hidden.json()["errors"][0]["code"] == "NAME_UNKNOWN"

    catalog = await client.get("/v2/_catalog", headers={"Authorization": f"Basic {pair}"})
    assert catalog.json() == {"repositories": []}


async def test_a_public_image_is_pulled_without_an_account(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    await create_project(client, slug="open", visibility="public")
    token = await make_token(client)
    public = "/v2/anna.k/open"

    started = await client.post(f"{public}/blobs/uploads/", headers=basic(token))
    await client.patch(started.headers["location"], content=CONFIG, headers=basic(token))
    await client.put(
        f"{started.headers['location']}?digest={digest_of(CONFIG)}", headers=basic(token)
    )
    body = manifest_of(CONFIG, [])
    await client.put(f"{public}/manifests/latest", content=body, headers=basic(token))

    client.cookies.clear()
    read = await client.get(f"{public}/manifests/latest")
    assert read.status_code == httpx.codes.OK
    assert read.content == body
    assert (await client.get("/v2/_catalog")).json() == {"repositories": ["anna.k/open"]}


async def test_deleting_a_project_takes_its_layers_off_the_disk(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    """Rows go by themselves; the files have to be swept on purpose."""
    del account
    project = await create_project(client)
    token = await make_token(client)
    digest = await push_blob(client, token, LAYER)

    path = storage.blob_path(UUID(project["id"]), digest)
    assert path.is_file()

    removed = await client.delete(f"{API_PREFIX}/projects/anna.k/{SLUG}")
    assert removed.status_code == httpx.codes.NO_CONTENT, removed.text
    assert not path.exists()
