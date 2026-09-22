"""The runner: a small program that asks Grod for jobs and carries them out.

Run it on any machine that may reach the platform:

    grod-runner --url http://localhost:8000/api/v1 --token grodrun_...

It takes one job at a time, unpacks the tree of the commit into a temporary
directory, runs the script line by line and sends back everything it prints.
"""

import argparse
import asyncio
import io
import os
import shutil
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

DEFAULT_URL = "http://localhost:8000/api/v1"
POLL_SECONDS = 5.0
REQUEST_TIMEOUT = 30.0
ARCHIVE_TIMEOUT = 300.0
OUTPUT_CHUNK = 4096
SUCCESS = "success"
FAILED = "failed"


@dataclass(frozen=True)
class Options:
    """What the runner was started with."""

    url: str
    token: str
    work_dir: Path
    once: bool


def parse_arguments(argv: list[str] | None = None) -> Options:
    """Read the command line."""
    parser = argparse.ArgumentParser(prog="grod-runner", description="Grod pipeline runner")
    parser.add_argument("--url", default=os.environ.get("GROD_URL", DEFAULT_URL))
    parser.add_argument("--token", default=os.environ.get("GROD_RUNNER_TOKEN", ""))
    parser.add_argument("--work-dir", default=None)
    parser.add_argument(
        "--once", action="store_true", help="take one job, then exit (used by the tests)"
    )
    parsed = parser.parse_args(argv)
    if not parsed.token:
        parser.error("pass --token or set GROD_RUNNER_TOKEN")

    work_dir = (
        Path(parsed.work_dir) if parsed.work_dir else Path(tempfile.gettempdir()) / "grod-runner"
    )
    return Options(
        url=parsed.url.rstrip("/"), token=parsed.token, work_dir=work_dir, once=parsed.once
    )


class Runner:
    """One runner process, talking to one platform."""

    def __init__(self, options: Options) -> None:
        self._options = options
        self._client = httpx.AsyncClient(
            base_url=options.url,
            headers={"Authorization": f"Bearer {options.token}"},
            timeout=REQUEST_TIMEOUT,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def take_job(self) -> dict[str, Any] | None:
        """Ask the platform for work."""
        response = await self._client.post("/runner/jobs/request")
        response.raise_for_status()
        body = response.text
        if not body or body == "null":
            return None
        job: dict[str, Any] = response.json()
        return job

    async def report(self, job_id: str, *, log: str = "", state: str | None = None) -> None:
        """Send output, and the result once the job is over."""
        payload: dict[str, Any] = {"log": log}
        if state is not None:
            payload["state"] = state
        await self._client.patch(f"/runner/jobs/{job_id}", json=payload)

    async def fetch_tree(self, job: dict[str, Any], target: Path) -> None:
        """Unpack the code of the commit into the working directory."""
        response = await self._client.get(job["archiveUrl"], timeout=ARCHIVE_TIMEOUT)
        response.raise_for_status()
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(response.content)) as archive:
            # The archive comes from the platform's own repository, so its
            # entries are trusted; "data" still refuses paths outside the tree.
            archive.extractall(target, filter="data")

    async def run_job(self, job: dict[str, Any]) -> str:
        """Run every line of the script and return how the job ended."""
        work = self._options.work_dir / str(job["id"])
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)

        try:
            await self.fetch_tree(job, work)
        except (httpx.HTTPError, tarfile.TarError) as error:
            await self.report(job["id"], log=f"Could not fetch the code: {error}\n")
            return FAILED

        environment = {**os.environ, **{str(k): str(v) for k, v in job["variables"].items()}}
        environment["GROD_PROJECT"] = job["project"]
        environment["GROD_REF"] = job["ref"]
        environment["GROD_COMMIT"] = job["commit"]

        for line in job["script"]:
            await self.report(job["id"], log=f"$ {line}\n")
            code = await self._run_line(job["id"], line, work, environment)
            if code != 0:
                await self.report(job["id"], log=f"The command exited with code {code}.\n")
                return FAILED

        shutil.rmtree(work, ignore_errors=True)
        return SUCCESS

    async def _run_line(
        self, job_id: str, line: str, work: Path, environment: dict[str, str]
    ) -> int:
        """Run one line of the script, sending its output as it comes."""
        process = await asyncio.create_subprocess_shell(
            line,
            cwd=work,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output = process.stdout
        if output is None:  # pragma: no cover - the pipe is always there
            return await process.wait()
        while True:
            chunk = await output.read(OUTPUT_CHUNK)
            if not chunk:
                break
            await self.report(job_id, log=chunk.decode(errors="replace"))
        return await process.wait()

    async def serve(self) -> None:
        """Take jobs until the process is stopped."""
        while True:
            try:
                job = await self.take_job()
            except httpx.HTTPError as error:
                print(f"Could not reach the platform: {error}", file=sys.stderr)
                await asyncio.sleep(POLL_SECONDS)
                continue

            if job is None:
                if self._options.once:
                    return
                await asyncio.sleep(POLL_SECONDS)
                continue

            print(f"Job {job['name']} ({job['project']} @ {job['ref']})")
            state = await self.run_job(job)
            await self.report(job["id"], state=state)
            print(f"Job {job['name']}: {state}")
            if self._options.once:
                return


async def run(options: Options) -> None:
    """Start a runner and keep it going."""
    runner = Runner(options)
    try:
        await runner.serve()
    finally:
        await runner.close()


def main() -> None:
    """Entry point of the `grod-runner` command."""
    options = parse_arguments()
    try:
        asyncio.run(run(options))
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
