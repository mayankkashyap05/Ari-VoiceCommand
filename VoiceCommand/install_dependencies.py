"""Install Ari dependencies into project-local virtual environments."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path
from typing import Sequence


HERE = Path(__file__).resolve().parent
REQUIREMENTS = HERE / "requirements.txt"
VALIDATOR = HERE / "validate_repo.py"
MAIN_VENV = HERE / ".venv"
TTS_VENV = HERE / ".venv-tts"
TTS_PACKAGES = ("huggingface_hub", "torch", "torchaudio")


def _venv_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _ensure_venv(venv_dir: Path) -> Path:
    python_exe = _venv_python_path(venv_dir)
    if python_exe.exists():
        print(f"Using existing virtual environment: {venv_dir}")
        return python_exe

    print(f"Creating virtual environment: {venv_dir}")
    venv.EnvBuilder(with_pip=True).create(str(venv_dir))
    if not python_exe.exists():
        raise RuntimeError(f"Cannot find virtual environment Python: {python_exe}")
    return python_exe


def _run_pip(python_exe: Path, *arguments: str) -> None:
    subprocess.run(
        [str(python_exe), "-m", "pip", *arguments],
        check=True,
        cwd=str(HERE),
    )


def _install_main_dependencies(python_exe: Path) -> None:
    print("Installing main dependencies...")
    _run_pip(python_exe, "install", "--upgrade", "pip")
    _run_pip(python_exe, "install", "-r", str(REQUIREMENTS))


def _install_tts_dependencies() -> None:
    tts_python = _ensure_venv(TTS_VENV)
    print("Installing CosyVoice3 dedicated dependencies...")
    _run_pip(tts_python, "install", "--upgrade", "pip")
    _run_pip(tts_python, "install", "--upgrade", *TTS_PACKAGES)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install Ari dependencies into project virtual environments."
    )
    parser.add_argument(
        "--with-tts",
        action="store_true",
        help="Create .venv-tts and install core CosyVoice3 dependencies.",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip validation after installation.",
    )
    parser.add_argument(
        "--no-venv",
        action="store_true",
        help="Install into the current Python environment instead of .venv (for CI).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not REQUIREMENTS.exists():
        print(f"requirements.txt not found: {REQUIREMENTS}")
        return 1

    try:
        if args.no_venv:
            main_python = Path(sys.executable).resolve()
            print(f"Using current Python: {main_python}")
        else:
            main_python = _ensure_venv(MAIN_VENV)

        _install_main_dependencies(main_python)
        if args.with_tts:
            _install_tts_dependencies()

        print("All packages installed successfully.")
        if not args.skip_validate:
            if not VALIDATOR.exists():
                raise RuntimeError(f"Validation script not found: {VALIDATOR}")
            print("Running default validation...")
            subprocess.run(
                [str(main_python), str(VALIDATOR)],
                check=True,
                cwd=str(HERE),
            )
            print("Validation complete.")
    except subprocess.CalledProcessError as exc:
        print(f"An error occurred while running a command (exit code {exc.returncode}).")
        return exc.returncode or 1
    except (OSError, RuntimeError) as exc:
        print(f"An error occurred during installation: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())