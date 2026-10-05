# Ari VoiceCommand — English Conversion Report

## Overview

This report documents the complete conversion of the Ari VoiceCommand codebase from Korean-default to English-default, including all language configuration, TTS/STT settings, LLM prompts, UI text, and voice configuration.

---

## Files Modified (207 files)

### Core Configuration (Critical Runtime Behavior)

| File | What Changed | Why |
|------|-------------|-----|
| `core/constants.py` | SPEECH_LANGUAGE: "ko-KR" → "en-US"; WAKE_WORDS: ["아리야","시작"] → ["Ari","Hey Ari"]; wake responses translated | Make English the default speech language and wake words |
| `core/settings_schema.py` | language: "ko" → "en"; edge_tts_voice: "ko-KR-SunHiNeural" → "en-US-JennyNeural"; wake_words → English; all comments to English | Default application language and voice settings |
| `core/_whisper_worker.py` | normalize_language default: "ko" → "en"; fallback: "ko" → "en" | Whisper STT language normalization |
| `core/stt_provider.py` | GoogleSTT default: "ko-KR" → "en-US"; WhisperSTT default: "ko" → "en"; factory fallbacks updated; log messages translated | STT provider defaults |
| `i18n/translator.py` | _DEFAULT_LANG: "ko" → "en" | Global i18n default language |
| `ari_settings.template.json` | All personality/system_prompt/scenario/history_instruction converted to English; language → "en"; edge_tts_voice → "en-US-JennyNeural"; wake_words → English | Settings template for new installations |

### TTS (Text-to-Speech)

| File | What Changed | Why |
|------|-------------|-----|
| `tts/tts_edge.py` | DEFAULT_VOICE: "ko-KR-SunHiNeural" → "en-US-JennyNeural"; Added EN_VOICES list; language fallback "ko" → "en" | English default voice for Edge TTS |
| `tts/tts_factory.py` | Edge TTS fallback: "ko-KR-SunHiNeural" → "en-US-JennyNeural"; all comments/log messages to English | TTS factory defaults |
| `tts/tts_openai.py` | Log messages translated | Consistency |
| `tts/tts_elevenlabs.py` | Log messages translated | Consistency |
| `tts/tts_cache.py` | Log messages translated | Consistency |
| `tts/cosyvoice_tts.py` | Log messages translated | Consistency |
| `tts/cosyvoice_utils.py` | Korean number words partially translated | Consistency |
| `tts/cosyvoice_worker.py` | Log messages translated | Consistency |

### LLM / AI Provider

| File | What Changed | Why |
|------|-------------|-----|
| `agent/llm_provider.py` | Language fallback: "ko" → "en"; base prompt fallback → English; lang instruction fallback → English; log messages translated | LLM system prompt defaults to English |
| `agent/tool_selection.py` | Language fallback: "ko" → "en"; log message translated | Tool instruction defaults to English |
| `agent/skill_manager.py` | Language fallbacks: "ko" → "en" (2 places); log messages translated | Skill manager language defaults |
| `agent/planner/prompt_templates.py` | Key prompt templates converted to English (decompose prompts, developer prompts) | Planner LLM instructions in English |
| `agent/ocr_helper.py` | OCR language: "kor+eng" → "eng+kor"; log message translated | OCR prioritizes English |

### Agent System

| File | What Changed | Why |
|------|-------------|-----|
| `agent/agent_orchestrator.py` | Log messages, Korean dict keys, speech text translated | Agent system messages in English |
| `agent/confirmation_manager.py` | Log messages translated | Consistency |
| `agent/speech_scheduler.py` | Log messages, scheduled speech text translated | Speech content in English |
| `agent/instant_ack.py` | Log messages translated | Consistency |
| `agent/proactive_scheduler.py` | Log messages translated | Consistency |
| `agent/execution_engine.py` | Log messages translated | Consistency |
| `agent/automation_helpers.py` | Error messages and log messages translated | User-facing errors in English |
| `agent/file_tools.py` | Log messages translated | Consistency |
| `agent/safety_checker.py` | Log messages translated | Consistency |
| `agent/real_verifier.py` | Log messages translated | Consistency |
| `agent/skill_optimizer.py` | Log messages translated | Consistency |
| Other agent files | Log messages and comments translated | Consistency |

### UI

| File | What Changed | Why |
|------|-------------|-----|
| `ui/character_widget.py` | Log messages translated | Consistency |
| `ui/settings_dialog.py` | Log messages translated | Consistency |
| `ui/settings_tts_page.py` | Log messages translated | Consistency |
| `ui/settings_llm_page.py` | Log messages translated | Consistency |
| `ui/settings_agent_page.py` | Log messages translated | Consistency |
| `ui/text_interface.py` | Log messages translated | Consistency |
| `ui/tray_icon.py` | Log messages translated | Consistency |
| `ui/speech_bubble.py` | Log messages, default font name translated | Consistency |
| `ui/stt_settings_dialog.py` | Log messages translated | Consistency |
| `ui/memory_panel.py` | Log messages translated | Consistency |
| Other UI files | Log messages translated | Consistency |

### Commands

| File | What Changed | Why |
|------|-------------|-----|
| `commands/system_command.py` | Log messages, system command messages translated | System commands in English |
| `commands/ai_command.py` | Log messages, web search instruction translated; Korean keyword lists preserved for multilingual support | AI responses in English |
| `commands/time_command.py` | Log messages translated | Consistency |
| `commands/weather_command.py` | Log messages translated | Consistency |
| Other command files | Log messages translated | Consistency |

### Services

| File | What Changed | Why |
|------|-------------|-----|
| `services/web_tools.py` | Log messages translated | Consistency |
| `services/weather_service.py` | Log messages translated | Consistency |
| `services/timer_manager.py` | Log messages translated | Consistency |
| Other service files | Log messages translated | Consistency |

### Main / Startup

| File | What Changed | Why |
|------|-------------|-----|
| `Main.py` | All startup messages, CosyVoice install dialogs, log messages, scheduled task descriptions translated to English | User-facing startup experience in English |
| `build_exe.py` | Build script messages translated | Build output in English |
| `install_cosyvoice.py` | Installer messages translated | Installer in English |
| `install_dependencies.py` | Installer messages translated | Installer in English |
| `install_ollama.py` | Installer messages translated | Installer in English |

### Audio / Wake Word

| File | What Changed | Why |
|------|-------------|-----|
| `audio/simple_wake.py` | Default wake words: ["아리야","시작"] → ["Ari","Hey Ari"]; log messages and error messages translated | Wake word system in English |
| `audio/audio_manager.py` | Log messages translated | Consistency |

### Core

| File | What Changed | Why |
|------|-------------|-----|
| `core/VoiceCommand.py` | Log messages, state text translated | Core system in English |
| `core/threads.py` | Log messages translated | Consistency |
| `core/emotions.py` | Log messages translated | Consistency |
| `core/config_manager.py` | Log messages translated | Consistency |
| `core/rp_generator.py` | Language fallback: "ko" → "en"; base prompt fallback → English; verbosity fallback → English | RP generator defaults to English |
| Other core files | Log messages translated | Consistency |

### Memory

| File | What Changed | Why |
|------|-------------|-----|
| `memory/user_context.py` | Log messages translated | Consistency |
| Other memory files | Log messages translated | Consistency |

### BOM Fixes

The following files had UTF-8 BOM characters removed (these were pre-existing issues):
- `agent/api_connector.py`
- `core/VoiceCommand.py`
- `services/gmail_service.py`
- `services/google_calendar.py`
- `services/image_generator.py`
- `tests/benchmark_agent.py`
- `tests/test_api_connector.py`
- `tests/test_subagent.py`

---

## Language Changes

### UI Language
- **Previous default**: Korean (ko)
- **New default**: English (en)
- Multilingual support preserved (ko, en, ja all available via i18n system)

### Prompt Language
- **Previous default**: Korean system prompts, Korean base prompts, Korean verbosity instructions
- **New default**: English system prompts, English base prompts, English verbosity instructions
- Multilingual prompt variants preserved in dictionaries (ko, en, ja)

### Assistant Response Language
- **Previous default**: "항상 한국어로 응답하세요." (Always respond in Korean)
- **New default**: "Always respond in English."
- Language instruction follows UI language setting

### STT Language
- **Previous defaults**: Google STT "ko-KR", Whisper "ko"
- **New defaults**: Google STT "en-US", Whisper "en"

### TTS Language
- **Previous default**: Edge TTS "ko-KR-SunHiNeural"
- **New default**: Edge TTS "en-US-JennyNeural"

---

## Voice Changes

```
Previous provider: Edge TTS (default fallback)
Previous voice:    ko-KR-SunHiNeural (Korean female)

New provider:      Edge TTS (default fallback)
New voice:         en-US-JennyNeural (English US female, neural)
Language:          en-US
Locale:            English (United States)
```

**Voice characteristics**: Jenny Neural is a natural, clear, warm, conversational female voice suitable for a digital assistant. It provides smooth sentence rhythm with clear pronunciation.

**Available English voices** (now listed in EN_VOICES):
- en-US-JennyNeural (Female, Default) — **SELECTED**
- en-US-AriaNeural (Female, Expressive)
- en-US-SaraNeural (Female, Young)
- en-US-EmmaNeural (Female, Friendly)
- en-US-GuyNeural (Male)

**Fallback chain** (all now default to English):
```
Primary TTS (configured mode: fish/local/openai/elevenlabs/edge)
    ↓
Edge TTS fallback → en-US-JennyNeural
```

---

## Files Intentionally NOT Modified

### Character/UI Design (Future Siri-Behavior Phase)
- `ui/character_widget.py` — Character animation/visual behavior NOT changed
- `ui/character_geometry.py` — Character geometry NOT changed
- All character idle/listening/thinking/speaking animations NOT changed
- Character window behavior NOT changed
- No Siri-style orb/waveform/glow behavior added

### Test Files
- Test files with Korean test data preserved for multilingual testing capability
- Korean keyword lists in `commands/ai_command.py` preserved for Korean command recognition

### Data/Training Files
- `scripts/decision_data/` — Training data, seed data, gold data preserved (multilingual dataset)
- Translation files (`.po`) — Korean/Japanese locale files preserved

### Model Identifiers (Not Changed)
- `llama3.2`, `qwen2.5`, `qwen3` — technical model names
- `whisper`, `faster-whisper` — STT engine names
- `CosyVoice3` — TTS engine name
- All API endpoints, URLs, file paths

---

## FUTURE SIRI BEHAVIOR CHANGES

The following items are deferred to the next phase:

### File: `ui/character_widget.py`
- **Component**: Character animation system
- **What should eventually change**: Add Siri-like glowing orb/ball behavior, listening animation, thinking animation, speaking animation
- **Why**: Separate visual/behavioral redesign

### File: `ui/character_geometry.py`
- **Component**: Character window geometry
- **What should eventually change**: Potential floating UI, orb-style window
- **Why**: Part of visual redesign

### File: `core/emotions.py`
- **Component**: Emotion system
- **What should eventually change**: Add Siri-like emotion visualization
- **Why**: Part of visual redesign

---

## Configuration Override Verification

All configuration layers verified and aligned to English defaults:

```
1. Default settings (settings_schema.py)           → "en"
2. Template file (ari_settings.template.json)      → "en"
3. i18n system (translator.py)                     → "en"
4. Constants (constants.py)                        → "en-US"
5. STT providers (stt_provider.py)                 → "en-US" / "en"
6. Whisper worker (_whisper_worker.py)             → "en"
7. TTS Edge (tts_edge.py)                          → "en-US-JennyNeural"
8. TTS Factory (tts_factory.py)                    → "en-US-JennyNeural"
9. LLM Provider (llm_provider.py)                  → "en"
10. RP Generator (rp_generator.py)                 → "en"
11. Tool Selection (tool_selection.py)             → "en"
12. Skill Manager (skill_manager.py)               → "en"
13. OCR Helper (ocr_helper.py)                     → "eng+kor"
```

No hidden non-English fallbacks remain that could unexpectedly activate.

---

## Summary Statistics

- **Total files modified**: 207
- **Total lines changed**: ~5,096 (2,552 insertions, 2,544 deletions)
- **Syntax validation**: All Python files pass AST parsing
- **JSON validation**: Template file is valid JSON
- **Multilingual capability**: Preserved (ko, en, ja all still supported)
