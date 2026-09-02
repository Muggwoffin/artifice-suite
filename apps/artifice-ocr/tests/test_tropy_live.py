# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Opt-in contract test against a real, isolated Tropy process.

Run through ``scripts/interop/run-live-tropy.sh``. The normal test suite never
starts third-party desktop software and never writes to a user's Tropy profile.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from artifice_ocr import config
from artifice_ocr.tropy_api import TropyAPIClient, connect
from artifice_ocr.tropy_jsonld import ExportPhoto, build_export

pytestmark = [
    pytest.mark.live_interop,
    pytest.mark.skipif(
        os.environ.get("ARTIFICE_LIVE_TROPY") != "1",
        reason="set ARTIFICE_LIVE_TROPY=1 or use scripts/interop/run-live-tropy.sh",
    ),
]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _source() -> Path:
    raw = os.environ.get("ARTIFICE_TROPY_SOURCE")
    if not raw:
        pytest.skip("ARTIFICE_TROPY_SOURCE does not name a built Tropy checkout")
    source = Path(raw).resolve()
    if not (source / "scripts" / "db.js").is_file():
        pytest.fail(f"Tropy source is incomplete: {source}")
    return source


def _electron(source: Path) -> Path:
    override = os.environ.get("ARTIFICE_TROPY_EXECUTABLE")
    if override:
        executable = Path(override).resolve()
    elif os.name == "nt":
        executable = source / "node_modules" / "electron" / "dist" / "electron.exe"
    else:
        executable = source / "node_modules" / ".bin" / "electron"
    if not executable.is_file():
        pytest.fail(f"Tropy Electron executable was not built: {executable}")
    return executable


def _create_project(source: Path, project: Path) -> None:
    node = os.environ.get("ARTIFICE_TROPY_NODE") or shutil.which("node")
    if not node:
        pytest.fail("Node is unavailable; run scripts/interop/bootstrap-tropy.sh")
    subprocess.run(
        [
            node,
            str(source / "scripts" / "db.js"),
            "create",
            "--file",
            str(project),
            "--name",
            "Artifice Interop",
        ],
        cwd=source,
        check=True,
        timeout=30,
    )


def _wait_for_project(base_url: str, project: Path, process: subprocess.Popen, log: Path) -> dict:
    deadline = time.monotonic() + 45
    last_error = "Tropy did not answer"
    with httpx.Client(timeout=1, trust_env=False, follow_redirects=False) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = log.read_text(encoding="utf-8", errors="replace")[-4000:]
                pytest.fail(f"Tropy exited with {process.returncode}\n{output}")
            try:
                root = client.get(f"{base_url}/")
                if root.status_code == 200:
                    payload = root.json()
                    if Path(payload["project"]).resolve() == project.resolve():
                        named = client.get(f"{base_url}/project/current/")
                        if named.status_code == 200:
                            return named.json()
                        # Tropy 1.17 has no named-project routes. Its legacy
                        # collection becomes available only after the renderer
                        # has finished opening the database.
                        legacy = client.get(f"{base_url}/project/items")
                        if legacy.status_code == 200:
                            return payload
                        last_error = f"legacy API HTTP {legacy.status_code}"
                    else:
                        last_error = "API is ready but the requested project is not current"
                else:
                    last_error = f"HTTP {root.status_code}: {root.text[:200]}"
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                last_error = str(exc)
            time.sleep(0.25)
    pytest.fail(f"Tropy did not open the isolated project: {last_error}")


@contextmanager
def _running_tropy(source: Path, project: Path, runtime: Path, port: int):
    electron = _electron(source)
    data = runtime / "data"
    cache = runtime / "cache"
    logs = runtime / "logs"
    data.mkdir()
    cache.mkdir()
    logs.mkdir()
    process_log = runtime / "process.log"
    command = [str(electron)]
    if not os.environ.get("ARTIFICE_TROPY_EXECUTABLE"):
        command.extend(["--app", str(source), "--dev"])
    command.extend(
        [
            "--data",
            str(data),
            "--cache",
            str(cache),
            "--logs",
            str(logs),
            "--port",
            str(port),
            "--disable-hardware-acceleration",
            "--no-auto-updates",
            str(project),
        ]
    )
    with process_log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(
            command,
            cwd=source,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=os.name != "nt",
        )
        try:
            payload = _wait_for_project(f"http://127.0.0.1:{port}", project, process, process_log)
            yield process, payload
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    process.terminate()
                else:
                    os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    if os.name == "nt":
                        process.kill()
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)


def test_real_tropy_jsonld_and_note_contract(tmp_path):
    """Prove Artifice's JSON-LD and note client against the real application."""
    source = _source()
    project = tmp_path / "Artifice Contract.tropy"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    _create_project(source, project)

    image = tmp_path / "contract.jpg"
    shutil.copyfile(source / "test" / "fixtures" / "images" / "PA140105.JPG", image)
    exported = build_export(
        [
            ExportPhoto(
                abs_path=image,
                text="Imported OCR note",
                label="Contract image",
                language="en",
                item_node=None,
                group=None,
                photo_index=None,
                path_rel=None,
                checksum="",
                mimetype="image/jpeg",
            )
        ]
    )

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    config.reset()
    config.load_config()
    config.apply_overrides({"tropy_api_port": port})
    try:
        with _running_tropy(source, project, runtime, port) as (_process, discovery):
            assert discovery["version"]
            connection = connect(project)
            assert connection.port == port
            endpoint = f"{base_url}{connection.project_prefix}"
            with httpx.Client(timeout=10, trust_env=False) as client:
                imported = client.post(
                    f"{endpoint}/import",
                    data={"data": json.dumps(exported)},
                )
                assert imported.status_code == 200, imported.text

                items_response = client.get(f"{endpoint}/items")
                items_response.raise_for_status()
                items = items_response.json()
                assert len(items) == 1

                photos_response = client.get(f"{endpoint}/items/{items[0]['id']}/photos")
                photos_response.raise_for_status()
                photos = photos_response.json()
                assert len(photos) == 1

            if discovery["version"].startswith("1.17"):
                assert connection.project_prefix == "/project"
            else:
                assert connection.project_prefix == "/project/current"
            api = TropyAPIClient(connection)
            photo = api.photo(int(photos[0]["id"]))
            assert photo is not None
            note_ids = api.create_note(int(photo["id"]), "Live contract note", "en")
            assert len(note_ids) == 1
            assert api.note_text(note_ids[0]) == "Live contract note"
            assert api.has_identical_note(api.photo(int(photo["id"])), "Live contract note")
    finally:
        config.reset()
