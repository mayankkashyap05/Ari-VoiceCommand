from __future__ import annotations

import argparse
import os

from core.ollama_installer import COMMON_OLLAMA_MODELS, install_ollama, normalize_models


def _parse_args():
    parser = argparse.ArgumentParser(description="Ollama local LLM installation script")
    parser.add_argument("--install-dir", default="", help="Ollama install path (optional)")
    parser.add_argument("--models-dir", default="", help="Model save path (optional)")
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="List of models to install, e.g. llama3.2:3b qwen3:4b",
    )
    return parser.parse_args()


def _prompt_models() -> list[str]:
    print("Select Ollama models to install. Multiple selections allowed with commas.")
    for index, option in enumerate(COMMON_OLLAMA_MODELS, start=1):
        print(f"  {index}. {option.model:<18} - {option.summary}")
    print("  0. Skip model installation")
    raw = input("Enter numbers (e.g. 1,2) or press Enter → 1: ").strip()
    if not raw:
        return [COMMON_OLLAMA_MODELS[0].model]
    if raw == "0":
        return []

    selected: list[str] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            idx = int(token)
        except ValueError:
            continue
        if 1 <= idx <= len(COMMON_OLLAMA_MODELS):
            selected.append(COMMON_OLLAMA_MODELS[idx - 1].model)

    custom = input("Enter additional model names (press Enter to skip): ").strip()
    if custom:
        selected.extend(part.strip() for part in custom.split(","))
    return normalize_models(selected)


def install() -> None:
    args = _parse_args()
    models = normalize_models(args.models) if args.models is not None else _prompt_models()

    print("=" * 60)
    print("   Ollama Local LLM One-Stop Installer")
    print("=" * 60)
    if args.install_dir:
        print(f"Install path: {os.path.abspath(args.install_dir)}")
    if args.models_dir:
        print(f"Model path: {os.path.abspath(args.models_dir)}")
    print(f"Selected models: {', '.join(models) if models else 'None'}")
    print()

    result = install_ollama(
        install_dir=args.install_dir or None,
        models_dir=args.models_dir or None,
        models=models,
    )

    print("\n" + "=" * 60)
    print("Ollama installation complete!")
    print(f"Ollama path: {result['install_dir']}")
    print(f"Model path: {result['models_dir']}")
    print(f"OpenAI-compatible address: {result['base_url']}")
    if result["installed_models"]:
        print(f"Installed models: {', '.join(result['installed_models'])}")
    else:
        print("Installed models: None")
    print("=" * 60)


if __name__ == "__main__":
    install()