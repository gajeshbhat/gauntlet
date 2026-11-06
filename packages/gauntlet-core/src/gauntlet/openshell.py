"""Optional isolation: run commands in an OpenShell sandbox (`pip install 'gauntlet-core[openshell]'`, plus a gateway).

The sandbox starts from an image, with no network except the package index, and has no mount of
the host: the snapshot is copied in as a tar and results are copied back out as one, in small pieces because a single
call carries about 1 MB at most. Everything reaches the SDK through `import_module`, so the extra stays optional.
"""

import base64
import io
import secrets
import shutil
import tarfile
import tempfile
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from importlib import import_module
from pathlib import Path
from typing import Any

from gauntlet.errors import GauntletError
from gauntlet.sandbox import ExecResult, resolve

ROOT = "/sandbox"  # the sandbox user's home; the only place it can write
CHUNK = 512 * 1024  # bytes per call, a multiple of 4 so every base64 piece decodes on its own
MAX_FETCH = 400_000_000  # base64 characters read back at most
PYPI = ("pypi.org", "files.pythonhosted.org")
READ_ONLY = [
    "/usr",
    "/lib",
    "/etc",
    "/var/log",
    "/proc",
    "/dev/urandom",
]  # the gateway's defaults, which a policy replaces
READ_WRITE = ["/tmp", "/dev/null", "/dev/shm"]  # shared memory is what mutmut's worker pool needs
HINT = "install the SDK with `pip install 'gauntlet-core[openshell]'` and start a gateway (see docs/how-to.md)"

Connect = Callable[[str, str], AbstractContextManager[Any]]


def _rule(name: str, hosts: Sequence[str], binary: str) -> Any:
    pb = import_module("openshell._proto.sandbox_pb2")
    endpoints = [pb.NetworkEndpoint(host=host, port=443) for host in hosts]
    return pb.NetworkPolicyRule(name=name, endpoints=endpoints, binaries=[pb.NetworkBinary(path=binary)])


def gateway(name: str, image: str) -> AbstractContextManager[Any]:
    """The SDK's sandbox over `image`: the package index is open to uv, the rest is denied."""
    try:
        sdk = import_module("openshell")
        spec, policy = import_module("openshell._proto.openshell_pb2"), import_module("openshell._proto.sandbox_pb2")
    except ImportError:
        raise GauntletError(f"the openshell SDK is not installed: {HINT}") from None
    rules = {"pypi": _rule("pypi", PYPI, "/usr/local/bin/uv")}
    files = policy.FilesystemPolicy(include_workdir=True, read_only=READ_ONLY, read_write=READ_WRITE)
    template = spec.SandboxSpec(
        template=spec.SandboxTemplate(image=image),
        policy=policy.SandboxPolicy(version=1, filesystem=files, network_policies=rules),
    )
    return sdk.Sandbox(workspace="default", name=name, spec=template, delete_on_exit=True, ready_timeout_seconds=300)


class OpenShellSandbox:
    def __init__(self, project: Path, image: str, *, root: str = ROOT, connect: Connect = gateway) -> None:
        self.project, self.root, self.project_dir = project, root, f"{root}/project"
        self._tar, self._b64 = f"{root}/gauntlet.tar", f"{root}/gauntlet.b64"
        self.image, self._connect = image, connect
        self._cm: AbstractContextManager[Any] | None = None
        self._box: Any = None

    def ensure(self) -> None:
        try:
            cm = self._connect(f"gauntlet-{secrets.token_hex(4)}", self.image)
            self._box = cm.__enter__()
        except GauntletError:
            raise
        except Exception as e:  # the SDK raises its own and gRPC's errors
            raise GauntletError(f"cannot start an OpenShell sandbox: {e}; {HINT}") from None
        self._cm = cm
        self._run(["mkdir", "-p", self.project_dir])
        with tempfile.TemporaryFile() as archive:
            with tarfile.open(fileobj=archive, mode="w") as tar:
                tar.add(self.project, arcname=".")
            archive.seek(0)
            while chunk := archive.read(CHUNK):
                self._run(["sh", "-c", f"cat >> {self._tar}"], chunk)
        self._run(["tar", "-xf", self._tar, "-C", self.project_dir])
        self._run(["rm", "-f", self._tar])

    def _call(
        self, argv: Sequence[str], env: Mapping[str, str], timeout: int, workdir: str, stdin: bytes | None = None
    ) -> ExecResult:
        done = self._box.exec(list(argv), env=env, workdir=workdir, stdin=stdin, timeout_seconds=timeout)
        return ExecResult(done.exit_code, done.stdout, done.stderr)

    def _run(self, argv: Sequence[str], stdin: bytes | None = None) -> str:
        done = self._call(argv, {}, 300, self.root, stdin)  # the project directory may not exist yet
        if done.code != 0:
            raise GauntletError(f"{argv[0]} failed in the sandbox: {(done.stderr or done.stdout).strip()[-500:]}")
        return done.stdout

    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        return self._call(argv, resolve(env or {}), timeout, self.project_dir)

    def _read(self, size: int) -> bytes:
        pieces = [self._run(["dd", f"if={self._b64}", f"bs={CHUNK}", f"skip={i}", "count=1", "status=none"])
                  for i in range(-(-size // CHUNK))]  # fmt: skip
        return base64.b64decode("".join(pieces), validate=True)

    def fetch(self, subdir: str) -> None:
        self._run(["tar", "-cf", self._tar, "-C", self.project_dir, subdir])
        self._run(["sh", "-c", f"base64 -w0 {self._tar} > {self._b64}"])
        size = int(self._run(["stat", "-c", "%s", self._b64]))
        if size > MAX_FETCH:
            raise GauntletError(f"{subdir} is too big to copy out of the sandbox")
        try:
            data = self._read(size)
            old = self.project / subdir
            if old.is_dir() and not old.is_symlink():
                shutil.rmtree(old)
            else:
                old.unlink(missing_ok=True)
            with tarfile.open(fileobj=io.BytesIO(data)) as tar:
                tar.extractall(self.project, filter="data")  # refuses links and paths that leave the directory
        except (tarfile.TarError, ValueError):
            raise GauntletError(f"the sandbox returned a damaged copy of {subdir}") from None

    def remove(self) -> None:
        if self._cm is not None:
            cm, self._cm = self._cm, None
            cm.__exit__(None, None, None)
