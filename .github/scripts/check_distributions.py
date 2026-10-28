"""Validate built archives and install each into its own external environment."""

import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from email import message_from_bytes
from pathlib import Path

PACKAGE = "appium_connect_agent"
DEPENDENCIES = {
    "httpx==0.28.1",
    "anyio==4.15.1",
    "httpcore==1.0.9",
    "node-semver==0.9.1",
    "Appium-Python-Client==6.0.8",
    "selenium==4.51.0",
    "defusedxml==0.7.1",
}
METADATA_DEPENDENCIES = {dependency.lower() for dependency in DEPENDENCIES}
STUB = "typings/nodesemver/__init__.pyi"
ROOT = Path(__file__).resolve().parents[2]
SMOKE = """
import sys
from importlib.metadata import distribution
from importlib.resources import files
from pathlib import Path
import appium_connect_agent
from appium_connect_agent.contracts import LocalSettings

assert Path(appium_connect_agent.__file__).resolve().is_relative_to(
    Path(sys.prefix).resolve()
)
assert files(appium_connect_agent).joinpath('py.typed').is_file()
assert LocalSettings.__module__ == 'appium_connect_agent.contracts'
assert LocalSettings().appium_executable is None
metadata = distribution('appium-connect-agent').metadata
assert metadata['Name'] == 'appium-connect-agent'
assert metadata['Version'] == sys.argv[1]
assert metadata['Requires-Python'] == sys.argv[2]
assert set(metadata.get_all('Requires-Dist')) == {
    'httpx==0.28.1', 'anyio==4.15.1', 'httpcore==1.0.9', 'node-semver==0.9.1',
    'appium-python-client==6.0.8', 'selenium==4.51.0', 'defusedxml==0.7.1'
}
if sys.platform == 'darwin':
    from appium_connect_agent.runtime import InstallRequest, LocalSettings as RuntimeSettings
    from appium_connect_agent.runtime import Runtime, supported_combinations
    from appium_connect_agent.automation import Device, Element, Session
    assert RuntimeSettings is LocalSettings
    assert callable(Runtime)
    assert InstallRequest().combination_id is None
    combinations = supported_combinations()
    assert len(combinations) == 1
    assert combinations[0].combination_id == 'macos-android-uiautomator2'
    assert combinations[0].appium_version == '3.7.0'
    assert combinations[0].driver_version == '8.7.0'
    assert hasattr(Device, 'install_app') and hasattr(Device, 'remove_app')
    assert hasattr(Element, 'inspect') and hasattr(Session, 'quit')
else:
    assert 'appium_connect_agent.runtime' not in sys.modules
print('Isolated installed package, metadata and py.typed: OK')
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def run(command: list[str], cwd: Path) -> None:
    print("Running:", command, flush=True)
    subprocess.run(command, cwd=cwd, check=True, timeout=180)


def main() -> None:
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text())
    project = configuration["project"]
    require(set(project["dependencies"]) == DEPENDENCIES, "Unapproved dependencies")
    version = str(project["version"])
    python_requirement = str(project["requires-python"])
    index_arguments: list[str] = []
    for index in configuration.get("tool", {}).get("uv", {}).get("index", []):
        if index.get("explicit") is True:
            index_arguments.extend(("--index", str(index["url"])))
    stem = f"{PACKAGE}-{version}"
    expected = {
        p.relative_to(ROOT / "src").as_posix(): p.read_bytes()
        for p in (ROOT / "src" / PACKAGE).rglob("*")
        if p.is_file() and (p.suffix == ".py" or p.name == "py.typed")
    }
    for required in (
        "__init__.py",
        "py.typed",
        "contracts/__init__.py",
        "runtime/__init__.py",
        "automation/__init__.py",
    ):
        require(f"{PACKAGE}/{required}" in expected, f"Missing source: {required}")
    artifacts = sorted(p for p in (ROOT / "dist").iterdir() if p.name != ".gitignore")
    require(
        len(artifacts) == 2
        and sum(p.suffix == ".whl" for p in artifacts) == 1
        and sum(p.name.endswith(".tar.gz") for p in artifacts) == 1,
        f"Expected exactly one wheel and one sdist, got {artifacts}",
    )
    for artifact in artifacts:
        if artifact.suffix == ".whl":
            with zipfile.ZipFile(artifact) as wheel:
                names = [
                    item.filename for item in wheel.infolist() if not item.is_dir()
                ]
                info = f"{stem}.dist-info"
                metadata_names = {
                    f"{info}/{n}" for n in ("WHEEL", "METADATA", "RECORD")
                }
                require(len(names) == len(set(names)), "Duplicate wheel members")
                require(
                    set(names) == expected.keys() | metadata_names,
                    f"Unexpected wheel contents: {names}",
                )
                for name, content in expected.items():
                    require(
                        wheel.read(name) == content, f"Wheel source differs: {name}"
                    )
                metadata = wheel.read(f"{info}/METADATA")
        else:
            with tarfile.open(artifact) as sdist:
                members = sdist.getmembers()
                require(
                    all(m.isdir() or m.isfile() for m in members),
                    "Non-regular sdist members",
                )
                names = [m.name for m in members if m.isfile()]
                source_names = {f"{stem}/src/{name}" for name in expected}
                metadata_names = {
                    f"{stem}/{n}"
                    for n in ("PKG-INFO", "README.md", "pyproject.toml", STUB)
                }
                allowed = (
                    source_names | metadata_names | {f"{stem}/pyproject.toml.orig"}
                )
                require(len(names) == len(set(names)), "Duplicate sdist members")
                require(
                    source_names | metadata_names <= set(names) <= allowed,
                    f"Unexpected sdist contents: {names}",
                )
                contents: dict[str, bytes] = {}
                for name in names:
                    stream = sdist.extractfile(name)
                    require(stream is not None, f"Missing sdist member: {name}")
                    if stream is not None:
                        with stream:
                            contents[name] = stream.read()
                for name, content in expected.items():
                    require(
                        contents[f"{stem}/src/{name}"] == content,
                        f"Sdist source differs: {name}",
                    )
                metadata = contents[f"{stem}/PKG-INFO"]
                require(
                    contents[f"{stem}/{STUB}"] == (ROOT / STUB).read_bytes(),
                    "Sdist local type declaration differs",
                )
        parsed = message_from_bytes(metadata)
        require(parsed["Name"] == project["name"], "Incorrect distribution name")
        require(parsed["Version"] == version, "Incorrect version")
        require(
            parsed["Requires-Python"] == python_requirement, "Incorrect Python range"
        )
        require(
            set(parsed.get_all("Requires-Dist", [])) == METADATA_DEPENDENCIES,
            "Incorrect runtime dependencies",
        )
        print(f"Archive contents and metadata: {artifact.name} OK", flush=True)
    uv = shutil.which("uv")
    require(uv is not None, "uv is required")
    if uv is None:
        return
    with tempfile.TemporaryDirectory(prefix="aca-distributions-") as temp:
        outside = Path(temp)
        for index, artifact in enumerate(artifacts):
            environment = outside / f"venv-{index}"
            run(
                [
                    uv,
                    "venv",
                    "--python",
                    sys.executable,
                    "--no-python-downloads",
                    str(environment),
                ],
                outside,
            )
            python = environment / (
                "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
            )
            run(
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    *index_arguments,
                    str(artifact),
                ],
                outside,
            )
            run([uv, "pip", "check", "--python", str(python)], outside)
            run([str(python), "-I", "-c", SMOKE, version, python_requirement], outside)


if __name__ == "__main__":
    main()
