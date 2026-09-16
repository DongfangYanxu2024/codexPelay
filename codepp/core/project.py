from pathlib import Path

from ..git.repo import git_toplevel


def initialization_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    return git_toplevel(current) or current


def detect_metadata(root: Path) -> dict[str, str]:
    metadata = {"Name": root.name, "Language": "Unknown", "Framework": "Unknown", "Package Manager": "Unknown"}
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists() or (root / "setup.py").exists():
        metadata["Language"] = "Python"
        metadata["Package Manager"] = "pip"
    elif (root / "package.json").exists():
        metadata["Language"] = "JavaScript/TypeScript"
        if (root / "pnpm-lock.yaml").exists():
            metadata["Package Manager"] = "pnpm"
        elif (root / "yarn.lock").exists():
            metadata["Package Manager"] = "yarn"
        else:
            metadata["Package Manager"] = "npm"
    elif (root / "Cargo.toml").exists():
        metadata.update({"Language": "Rust", "Package Manager": "cargo"})
    elif (root / "go.mod").exists():
        metadata.update({"Language": "Go", "Package Manager": "go"})
    elif (root / "pom.xml").exists() or (root / "build.gradle").exists():
        metadata.update({"Language": "Java", "Package Manager": "Maven" if (root / "pom.xml").exists() else "Gradle"})
    return metadata
