"""
Nuitka EXE Build Script (Optimized Version)

Run: py -3.11 build_exe.py

Run: py -3.11 build_exe.py --clean

Run: py -3.11 build_exe.py --onefile

Recommended: py -3.11 validate_repo.py


Nuitka import exclusion policy:

  Modules excluded with --nofollow-import-to are not included in the distribution folder.
  Only modules that have alternative paths, heavy optional features (torch,
  sentence_transformers, easyocr, etc.) and the unused mistralai client are excluded.
  Packages used by default features (openai/anthropic, httpx/pydantic, Whisper,
  web search, screen analysis) and their dependencies are not excluded.

  numpy and scipy are required by the local decision engine and Whisper worker.


Output: dist/Ari/


Included modules (2026-05-26 latest):

  agent/mcp_server.py          — local MCP HTTP server

  ui/agent_dashboard.py       — agent progress dashboard

  ui/settings_agent_page.py   — agent timeout/audit log/MCP Settings

  agent/file_tools.py         — LLM direct file tools(read/write/edit/list/search/move/delete)

  agent/llm_provider.py       — stream_chat(), analyze_image(), token-budget-based context

  agent/api_connector.py      — OpenAPI-based external API calls

  services/google_calendar.py / gmail_service.py / image_generator.py — advanced tool services



Included modules (2026-04-29):

  agent/response_cache.py     — from_config() factory + _coerce_positive_int() helper function added

  agent/task_queue.py         — AgentTaskQueue PriorityQueue + worker-thread-based asynchronous queue (new)

  agent/llm_router.py         — added Korean/Japanese keywords (CODE/PLAN/LONG multilingual routing)

  agent/safety_checker.py     — curl/wget DANGEROUS → CAUTION reclassification

  commands/weather_command.py — multilingual keywords + CommandResult return

  assistant/ai_assistant.py   — _responses() deferred translation

  commands/ai_command.py     — direct service calls from tool handlers, i18n completed

  commands/command_registry.py — CommandResult return standardization + f-string logging fix

  i18n/locales/*.po          — ko/en/ja 24 ai_command/SimpleAIAssistant translation keys added



Included modules (2026-04-22 latest):

  agent/confirmation_manager.py — all UI strings i18n applied + Codacy W1202 f-string logging fix

  agent/safety_checker.py       — thread-safe cache (_cache_lock) + _translate_matches() i18n

  agent/autonomous_executor.py  — _SENSITIVE_ENV_SUBSTRINGS sensitive environment variable substring filtering

  core/VoiceCommand.py          — LearningModeState TypedDict + _EMOTION_ALIASES ko/en/ja

  core/constants.py             — removed WAKE_RESPONSES → get_wake_responses() function for i18n support

  core/stt_provider.py          — internal log message localization

  memory/conversation_history.py — _compress_oldest() background thread handling + wait for flush()

  services/timer_manager.py     — full timer i18n + Korean/English/Japanese time-unit parsing (_iter_duration_matches)

  i18n/locales/*.po             — ko/en/ja 54 translation keys added (timer/OK dialog/safety checker)



Included modules (2026-04-14 latest):

  agent/agent_orchestrator.py — shared context cache, dynamic planning iteration, early termination on repeated failures

  agent/execution_engine.py   — repeated identical error interruption, diversified recovery strategies, step timeout hints

  agent/agent_planner.py      — StrategyMemory lift gating + optional step field passing

  agent/agent_math.py         — cosine_similarity common utility

  agent/tag_keywords.py      — common TAG_KEYWORDS dictionary

  agent/learning_engine.py    — background reflection thread + learning-item update helper

  agent/reflection_engine.py  — fallback message i18n translation during execution + estimated token measurement

  agent/skill_library.py      — goal-embedding-based skill matching + compile_failed tracking

  agent/episode_memory.py     — embedder-first save/search + background completion of missing embeddings

  agent/learning_metrics.py   — daily learning statistics/counters/estimated token summary aggregation + lift gating

  agent/weekly_report.py      — self-improvement loop activity/new skills/Python compilation/token report display

  i18n/locales/*.po           — ko/en/ja self-improvement loop string synchronization



Included modules (2026-04-06 latest):

  audio/simple_wake.py        — normalized full-phrase comparison to prevent false positives from partial matches inside sentences

  core/VoiceCommand.py        — extend_tts_resume_guard() added: extended protected ranges per segment

  core/threads.py             — VoiceRecognitionThread re-OK after detection later, TTSThread._collect_batch() added

  tts/cosyvoice_utils.py      — split_tts_segments() added: natural-unit segment splitting

  tts/cosyvoice_tts.py        — _speak_segment() + split_tts_segments()-based multi-segment internal processing

  ui/text_interface.py        — batch-play short leading sentences in streaming TTS (_queue_stream_tts_sentence)

  agent/assistant_text_utils.py — separated common goal interpretation and tool-response cleanup utilities for LLM/AICommand

  agent/planner_json_utils.py  — separated responsibility for truncated JSON response recovery/parsing

  agent/llm_retry.py           — LLM retry decision shared by planner and verifier

  agent/automation_plan_utils.py — separated browser/desktop action plan assembly and sorting utility

  agent/agent_planner.py       — improved planner cohesion by delegating to the JSON recovery helper

  agent/automation_helpers.py  — removed duplicate resilient/adaptive plan assembly



Included modules (2026-04-04 latest):

  agent/execution_engine.py    — steps execution engine separated from AgentOrchestrator (ExecutionEngine)

  agent/verification_engine.py — dedicated verification module (VerificationEngine)

  agent/learning_engine.py     — dedicated learning/recording module (LearningEngine)

  agent/autonomous_executor.py — child-process environment variable isolation (_build_child_env), zombie prevention

  agent/reflection_engine.py   — prompt injection prevention (_sanitize), length constants

  agent/skill_optimizer.py     — skill_id path traversal validation, thread-safe initialization

  agent/safety_checker.py      — added api_key sensitive keyword

  core/plugin_loader.py        — Unicode ZIP entry path validation, narrowed except scope

  core/plugin_sandbox.py       — guaranteed stdout restoration with finally block

  memory/memory_manager.py     — dual-lock singleton, regex caching

  memory/trust_engine.py       — added thread lock to update_source_weight

  ui/settings_llm_page.py      — SettingsDialog LLM tab separation (settings_dialog.py 1190→388 lines)

  ui/settings_tts_page.py      — SettingsDialog TTS tab separation

  ui/settings_plugin_page.py   — SettingsDialog Plugins tab separation



Included modules (2026-04-03 latest):

  agent/goal_predictor.py      — predict repeated failure risk + orchestrator proactive warning

  agent/learning_metrics.py    — learning component lift measurement

  agent/regression_guard.py    — weekly success-rate regression warning

  ui/text_interface.py         — streaming chunk buffering + start TTS immediately at sentence boundaries

  core/resource_manager.py     — development mode .ari_runtime separation + legacy state migration

                                  When the built exe runs, the runtime root is %AppData%/Ari

  validate_repo.py             — added clean execution environment / marketplace SHA-256 contract smoke tests

  market/web/src/*             — async handler/nullable cleanup for Codacy compatibility (behavior matching the web deployment artifact)

  market/supabase/functions     — strengthened upload-plugin / notify-developer validation logic (functions must be deployed separately for deployment)

  agent/agent_planner.py       — strengthened workspace audit template (window classification/tab estimation/backup reporting)

  core/plugin_sandbox.py       — multiprocessing-based isolated execution + timeout limit

  services/web_tools.py        — ddgs-priority search client + existing fallback path

  requirements.txt             — certifi / requests (>=2.33.0) / Pillow security updates, ddgs adopted as default



Included modules (2026-03-30):

  ui/character_widget.py       — fixed gravity-not-applied bug when dragging while climbing walls/ceiling

  ui/theme_editor.py           — added ThemeEditorDialog (separate palette editor window)

  ui/settings_dialog.py        — inline palette editor → ThemeEditorDialog separation

  core/plugin_loader.py        — PluginContext registration hooks (menu/command/tool/sandbox) + API version negotiation + ZIP package loading

  core/plugin_sandbox.py       — Plugins sandbox executor (currently kept using multiprocessing isolation)

  commands/command_registry.py — register_command() runtime dynamic registration

  commands/ai_command.py       — register_plugin_tool_handler() LLM tool dynamic dispatch

  agent/llm_provider.py        — register_plugin_tool() dynamic schema extension

  ui/tray_icon.py              — add_plugin_menu_action() dynamic insertion into the tray menu

  Main.py                      — PluginContext hook injection (menu/command/tool/sandbox)



Included modules (previous 2026-03-26):

  agent/ocr_helper.py          — easyocr/pytesseract screen text extraction (optional dependency)

  agent/dag_builder.py         — resource-conflict-based dependency DAG + parallel group calculation

  agent/embedder.py            — background ONNX embedding

  agent/real_verifier.py       — 4-step verification pipeline (heuristic→OCR→code→LLM)

  agent/agent_planner.py       — ActionStep DAG fields added, decompose() DAG comments

  agent/agent_orchestrator.py  — parallel group execution + DOM replanning flag handling

  agent/strategy_memory.py     — embedding field + 3-step search pipeline

  services/dom_analyser.py     — Selenium DOM analysis + next-action suggestions

  services/web_tools.py        — login_and_run DOM replanning, get_state includes DOM analysis

  memory/trust_engine.py       — FACT confidence update engine (source weighting/conflict/decay)

  memory/user_context.py       — record_fact and trust_engine integration, optimize_memory replaced decay logic

  ui/theme_editor.py           — palette color picker + JSON editor widget

  ui/settings_dialog.py        — ThemeEditorWidget integration, palette editing toggle

  agent/llm_provider.py        — independent LLM providers by role (planner/execution) + API key validation UI

  core/config_manager.py       — llm_planner_provider, llm_execution_provider, cosyvoice_dir

  tts/cosyvoice_worker.py      — cudnn.benchmark + dynamic ODE steps

  Main.py                      — automatic log rotation (max 10 retained)



Included modules (2026-03-25):

  agent/agent_orchestrator    — parallel execution and autonomous reflection support

  agent/agent_planner         — separation of planner/execution models, expanded app workflow templates

  agent/file_tools.py         — expanded file operation set (rename, merge, organize, analyze, log reports)

  agent/proactive_scheduler   — topic-based proactive suggestions and scheduled-time alarms

  agent/real_verifier.py      — strengthened actual-state verification based on windows/URLs/images/workflow JSON

  services/web_tools.py       — persistent memory for browser selector/action strategies + goal_hint reuse

  agent/automation_helpers.py — desktop window targeting/workflow memory + wait_image

  agent/strategy_memory.py    — workflow hint accumulation and reuse

  agent/autonomous_executor.py — adaptive/resilient workflows + plan snapshot exposure

  agent/episode_memory.py     — goal episode memory + re-injection of recovery instructions

  core/plugin_loader.py       — user plugin loader and extension entry point (.py / .zip)

  ui/theme.py, ui/common.py   — UI theme system based on %AppData%/Ari/theme/*.json

  tts/cosyvoice_tts.py        — Local TTS worker reuse + stabilized streaming output

  ui/memory_panel.py          — corrected memory panel statistics-tab layout

"""

import os
import shutil
import sys
import multiprocessing
import importlib.util
import json
from datetime import datetime


from core import release_packaging as _release_packaging
from core.app_version import get_windows_version
from core.settings_schema import SENSITIVE_SETTINGS_KEYS, SETTINGS_TEMPLATE_FILE


_raw_package_imports = _release_packaging.raw_package_imports
_raw_packages = _release_packaging.raw_packages

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass


clean_build = "--clean" in sys.argv
one_file = "--onefile" in sys.argv

_cpu = multiprocessing.cpu_count()
jobs = _cpu


print("=" * 60)
print("   Ari EXE Optimized Build System (Nuitka)")
print("=" * 60)
print(f"• Build mode: {'Single file' if one_file else 'Folder standalone'}")
print(f"• Build type: {'Clean build' if clean_build else 'Incremental build'}")
print(f"• Parallel jobs: {jobs} cores in use\n")

print("• Recommended pre-validation: python validate_repo.py\n")


def _ensure_safe_settings_template() -> None:
    template_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        SETTINGS_TEMPLATE_FILE,
    )

    with open(template_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    leaked = [
        key
        for key in SENSITIVE_SETTINGS_KEYS
        if str(payload.get(key, "") or "").strip()
    ]

    if leaked:
        raise SystemExit(
            f"Settings template contains sensitive values: {', '.join(leaked)}"
        )


_ensure_safe_settings_template()


try:
    from nuitka.__main__ import main as nuitka_main
except ImportError:
    raise SystemExit(
        "Nuitka is not installed. "
        "Please run `python -m pip install nuitka` first."
    )


HERE = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(HERE, "dist", "Ari")
PLUGIN_RUNTIME_DIR = os.path.join(HERE, "plugin_runtime")


def _module_exists(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _optional_include_packages(*module_names: str) -> list[str]:
    args: list[str] = []

    for module_name in module_names:
        if _module_exists(module_name):
            args.append(f"--include-package={module_name}")
        else:
            print(f"• Optional package skipped: {module_name}")

    return args

if clean_build and os.path.exists(os.path.join(HERE, "dist")):
    print("Deleting existing build cache and output...")
    shutil.rmtree(os.path.join(HERE, "dist"))


if os.path.exists(PLUGIN_RUNTIME_DIR):
    print("Cleaning plugin runtime cache...")
    shutil.rmtree(PLUGIN_RUNTIME_DIR, ignore_errors=True)


nuitka_args = [
    "--standalone" if not one_file else "--onefile",
    f"--jobs={jobs}",
    "--windows-console-mode=attach",
    "--output-filename=Ari",
    "--output-dir=dist",
    "--show-progress",
    "--remove-output",
    "--assume-yes-for-downloads",

    "--enable-plugin=pyside6",
    "--include-qt-plugins=multimedia",

    "--include-data-dir=images=images",
    "--include-data-dir=theme=theme",
    "--include-data-dir=i18n/locales=i18n/locales",
    "--include-data-dir=resources/decision=resources/decision",

    *(
        ["--include-data-files=resources/build_info.json=resources/build_info.json"]
        if os.path.isfile(
            os.path.join(HERE, "resources", "build_info.json")
        )
        else []
    ),

    "--include-data-files=DNFBitBitv2.ttf=DNFBitBitv2.ttf",
    "--include-data-files=icon.png=icon.png",
    "--include-data-files=icon.ico=icon.ico",
    *(
        ["--include-data-files=reference.wav=reference.wav"]
        if os.path.exists(os.path.join(HERE, "reference.wav"))
        else []
    ),
    f"--include-data-files={SETTINGS_TEMPLATE_FILE}={SETTINGS_TEMPLATE_FILE}",
    "--include-data-files=tts/cosyvoice_worker.py=cosyvoice_worker.py",
    "--include-data-files=install_cosyvoice.py=install_cosyvoice.py",

    *(
        ["--windows-icon-from-ico=icon.ico"]
        if os.path.exists("icon.ico")
        else []
    ),

    "--include-module=agent.confirmation_manager",
    "--include-module=agent.agent_orchestrator",
    "--include-module=agent.agent_planner",
    "--include-module=agent.agent_math",
    "--include-module=agent.assistant_text_utils",
    "--include-module=agent.autonomous_executor",
    "--include-module=agent.automation_plan_utils",
    "--include-module=agent.execution_analysis",
    "--include-module=agent.file_tools",
    "--include-module=agent.goal_predictor",
    "--include-module=agent.learning_metrics",
    "--include-module=agent.llm_provider",
    "--include-module=agent.api_connector",
    "--include-module=agent.llm_router",
    "--include-module=agent.mcp_server",
    "--include-module=agent.real_verifier",
    "--include-module=agent.regression_guard",
    "--include-module=agent.safety_checker",
    "--include-module=agent.tag_keywords",
    "--include-module=agent.proactive_scheduler",
    "--include-module=agent.strategy_memory",
    "--include-module=agent.episode_memory",
    "--include-module=agent.automation_helpers",
    "--include-module=agent.llm_retry",
    "--include-module=agent.planner_json_utils",
    "--include-module=agent.few_shot_injector",
    "--include-module=agent.response_cache",
    "--include-module=agent.task_queue",
    "--include-module=agent.skill_library",
    "--include-module=agent.skill_optimizer",
    "--include-module=agent.reflection_engine",
    "--include-module=agent.planner_feedback",
    "--include-module=agent.weekly_report",
    "--include-module=memory.user_profile_engine",
    "--include-module=memory.memory_index",
    "--include-module=memory.memory_consolidator",
    "--include-module=commands.memory_command",
    "--include-module=core.plugin_loader",
    "--include-module=core.plugin_sandbox",
    "--include-module=core._whisper_worker",
    "--include-module=core.resource_manager",
    "--include-module=services.web_tools",
    "--include-module=services.google_calendar",
    "--include-module=services.gmail_service",
    "--include-module=services.image_generator",
    "--include-module=ui.theme",
    "--include-module=ui.theme_runtime",
    "--include-module=ui.common",
    "--include-module=ui.scheduler_panel",
    "--include-module=ui.agent_dashboard",
    "--include-module=ui.settings_agent_page",

    "--include-package=agent",
    "--include-package=assistant",
    "--include-package=audio",
    "--include-package=commands",
    "--include-package=core",
    "--include-package=memory",
    "--include-package=tts",
    "--include-package=ui",
    "--include-package=services",

    "--include-package-data=agent",
    "--include-package-data=memory",
    "--include-package-data=faster_whisper",

    *_optional_include_packages(
        "pycaw",
        "comtypes",
        "ormsgpack",
        "speech_recognition",
        "pyaudio",
        "certifi",
        "watchdog",
        "requests",
        "httpx",
        "faster_whisper",
        "huggingface_hub",
        "onnxruntime",
        "tokenizers",
        "cv2",
        "lxml",
        "pydantic",
        "pydantic_core",
        "edge_tts",
        "fastapi",
        "uvicorn",
        "psutil",
        "ddgs",
        "duckduckgo_search",
        "pyautogui",
        "pyperclip",
        "pygetwindow",
        "selenium",
        "webdriver_manager",
        "easyocr",
        "pytesseract",
        "torch",
        "PIL",
        "docx",
        "bs4",
        "win32api",
    ),

    *_raw_packages(
        "pandas",
        "openpyxl",
        "matplotlib",
        "reportlab",
        raw_dependencies=True,
    ),

    "--nofollow-import-to=*.tests",
    "--nofollow-import-to=numpy.f2py",

    "--nofollow-import-to=torch",
    "--nofollow-import-to=torchvision",
    "--nofollow-import-to=torchaudio",
    "--nofollow-import-to=sentence_transformers",
    "--nofollow-import-to=transformers",
    "--nofollow-import-to=easyocr",
    "--nofollow-import-to=tensorflow",
    "--nofollow-import-to=sklearn",

    *_raw_packages("openai", "anthropic"),

    "--no-deployment-flag=excluded-module-usage",

    "--nofollow-import-to=mistralai",

    "--nofollow-import-to=pytest",
    "--nofollow-import-to=IPython",
    "--nofollow-import-to=pygments",
    "--nofollow-import-to=mouseinfo",
    "--nofollow-import-to=comtypes.test",
    "--nofollow-import-to=win32api",
    "--nofollow-import-to=win32con",
    "--nofollow-import-to=win32com",


    "Main.py",
]


_windows_version = get_windows_version()

if _windows_version:
    nuitka_args.extend([
        f"--file-version={_windows_version}",
        f"--product-version={_windows_version}",
    ])


start_time = datetime.now().strftime("%H:%M:%S")
print(f"Build start time: {start_time}")


try:
    original_argv = sys.argv[:]

    try:
        sys.argv = ["nuitka", *nuitka_args]
        nuitka_main()
        build_success = True
        exit_code = 0
    finally:
        sys.argv = original_argv

except SystemExit as exc:
    exit_code = (
        0
        if exc.code is None
        else exc.code
        if isinstance(exc.code, int)
        else 1
    )
    build_success = exit_code == 0

except Exception as exc:
    print(f"\n❌ Exception during build: {exc}")
    build_success = False
    exit_code = 1


if build_success:

    NUITKA_OUT = os.path.join(HERE, "dist", "Main.dist")

    if not one_file and os.path.exists(NUITKA_OUT):
        if os.path.exists(DIST_DIR):
            shutil.rmtree(DIST_DIR)

        os.rename(NUITKA_OUT, DIST_DIR)
        print(f"\n✓ Output complete: {DIST_DIR}")


    print("\n" + "=" * 60)
    print("   Build successful! Distribution is ready.")
    print("=" * 60)

else:

    if 'exit_code' in locals():
        print(f"\n❌ Error during build (code: {exit_code})")
    else:
        print("\n❌ Error during build")

    sys.exit(exit_code or 1)