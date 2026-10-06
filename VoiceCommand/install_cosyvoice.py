"""
CosyVoice3 Automatic Installation Script (One-Step)
- Specify the install path using an argument or interactive input
- Verify required tools (Git, FFmpeg)
- Clone the repository and download the model
- Automatically install virtual environment dependencies

Usage:
  python install_cosyvoice.py
  python install_cosyvoice.py --dir "C:\\CosyVoice"
"""
import argparse
import os

from core.cosyvoice_installer import DEFAULT_COSYVOICE_DIR, install_cosyvoice


def _parse_args() -> str:
    """Return the install path. Determine it in order: --dir argument → interactive input → default value."""
    parser = argparse.ArgumentParser(
        description="CosyVoice3 Local TTS Engine Installation Script",
        add_help=True,
    )
    parser.add_argument(
        "--dir",
        metavar="PATH",
        default=None,
        help=f"Install path (default: {DEFAULT_COSYVOICE_DIR})",
    )
    args, _ = parser.parse_known_args()

    if args.dir:
        return os.path.abspath(args.dir)
    print("Please enter the CosyVoice3 install path.")
    print(f"  Default: {DEFAULT_COSYVOICE_DIR}")
    user_input = input("Path (press Enter to use the default): ").strip()
    return os.path.abspath(user_input) if user_input else DEFAULT_COSYVOICE_DIR


def install_to_path(cosyvoice_dir: str) -> str:
    return install_cosyvoice(cosyvoice_dir)


def install() -> None:
    print("=" * 60)
    print("   CosyVoice3 Local TTS Engine One-Stop Installer")
    print("=" * 60)

    cosyvoice_dir = _parse_args()
    install_to_path(cosyvoice_dir)


if __name__ == "__main__":
    install()