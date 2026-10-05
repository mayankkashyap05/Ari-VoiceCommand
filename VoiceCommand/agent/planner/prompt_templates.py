_SYS_JSON_ONLY = "You are an expert at returning only JSON. Return pure JSON without explanation."

_DECOMPOSE_PROMPT = """\
Return execution steps as a JSON array to achieve the following goal.

Goal: {goal}
{context_block}
Rules:
- step_type: "python" (파이썬 코드), "shell" (CMD), "think" (判断/分析, content None)
- A single step is sufficient for simple tasks
- Write code that is immediately executable
- Python code can have multiple statements. `with`, `for`, `if`, `try` 같은 복합문은 세미콜론으로 이어붙이지 말고 줄바꿈으로 작성하세요.
- Previous step outputs are accessible via the step_outputs dictionary in Python (키: "step_0_output", "step_1_output", ...)
- Steps that depend on previous step results must set a condition (e.g., create folder then save file)
- condition: Execution condition expression (예: "len(step_outputs.get('step_0_output','')) > 0 and 'Error' not in step_outputs.get('step_0_output','')"), if omitted, always executes
- on_failure: "abort"(abort), "skip"(skip), "continue"(continue) 중 하나
- Windows 바탕화면 경로: When running Python code 'desktop_path' variable is immediately available. os.path.join(desktop_path, '폴더명') Use in the form.
- When saving files, check folder existence first or create it: os.makedirs(path, exist_ok=True)
- If web info is needed, do not use requests with arbitrary API keys, Use the already provided `web_search(query, max_results=5)` 와 `web_fetch(url)`use preferentially.
- When saving documents `save_document(directory, base_name, content, preferred_format='auto', title='')` helpers are available.
- `preferred_format='auto'`면 Automatically selects appropriate format among txt/md/pdf based on content structure.
- For file operations `rename_file`, `merge_files`, `organize_folder`, `analyze_data`, `generate_report`, `detect_file_set`, `batch_rename_files` helpers are available.
- For GUI/browser automation `open_url`, `open_path`, `launch_app`, `wait_seconds`, `click_screen`, `click_image`, `is_image_visible`, `move_mouse`, `type_text`, `press_keys`, `hotkey`, `take_screenshot`, `read_clipboard`, `write_clipboard`, `wait_for_window`, `get_active_window_title`, `list_open_windows`, `get_desktop_state`, `browser_login`, `run_browser_actions`, `run_adaptive_browser_workflow`, `run_resilient_browser_workflow`, `run_desktop_workflow`, `run_adaptive_desktop_workflow`, `run_resilient_desktop_workflow`, `get_runtime_state`, `get_state_transition_history`, `get_learned_strategies`, `get_planning_snapshot`, `get_recovery_candidates`, `get_recovery_guidance`, `get_recent_goal_episodes` helpers are available.
- Browser action types include `wait_url`, `wait_title`, `wait_selector`, `read_title`, `read_url`, `read_links`, `download_wait`are available.
- Before repetitive GUI/browser tasks `get_planning_snapshot_summary(goal_hint='...')` 또는 `get_planning_snapshot(goal_hint='...')`to read current state + past successful strategies first, When possible `run_resilient_browser_workflow(...)` / `run_resilient_desktop_workflow(...)`use preferentially.
- context에 `recent_goal_episodes`, `execution_policy_summary`, `recovery_candidates_json`, `recovery_guidance`가 있으면 우선 참고해 같은 실패를 반복하지 마세요.
- `run_browser_actions(url, actions, goal_hint='로그인 later 다운로드')`like `goal_hint`together allows reuse of previous successful action sequences.
- `run_desktop_workflow(goal_hint='메모장에 메모 Save', app_target='notepad', expected_window='메모장', actions=[...])`like 사용하면 창 전략과 later속 액션을 함께 재사용할 수 있습니다.
- If there is a possibility of overwriting existing documents `get_backup_history()` / `restore_last_backup(path)`to consider recovery paths.
- `YOUR_API_KEY`, `newsapi.org`, `nltk.download`, Code depending on external paid APIs is prohibited.
- For Korean news summaries, cutting search result text appropriately is sufficient. Do not add complex NLP libraries.
- Always return only a JSON array

Output format:
[
  {{
    "step_type": "python",
    "content": "Code to execute",
    "description_kr": "Step description",
    "expected_output": "Expected output",
    "condition": "",
    "on_failure": "abort"
  }}
]"""

_DEVELOPER_DECOMPOSE_PROMPT = """\
Return execution steps as a JSON array to achieve the following source development goal.

Goal: {goal}
{context_block}
Rules:
- step_type은 "python", "shell", "think" 중 하나만 사용하세요.
- max 4steps만 반환하세요.
- shell steps는 PowerShell 명령으로 작성하세요.
- shell 명령은 Save소 루트(repo_root)를 현재 작업 디렉터리로 사용한다고 가정하세요.
- python steps에서는 `repo_root`(Save소 루트)와 `module_dir`(VoiceCommand 패키지 루트)를 바로 사용할 수 있습니다.
- content는 짧고 실행 가능해야 하며, 파일 내용 전체를 길게 복붙하지 마세요.
- Previous step outputs are accessible via the step_outputs dictionary in Python.
- Source scan results(step_0_output, step_1_output 등)if not yet available, write the first plan focused on information gathering.
- Source scan results가 이미 있으면 그 결과를 바탕으로 개선 과제 1개를 고르고, Modify only one file or one responsibility unit at a time.
- Modification/read targets are limited to `VoiceCommand/agent`, `VoiceCommand/core`, `VoiceCommand/ui`, `VoiceCommand/plugins`, `VoiceCommand/tests`, `docs`, `VoiceCommand/validate_repo.py` .
- Do not hardcode paths `repo_root`와 `module_dir`calculate based on or explore first.
- After source scan is complete, do not return to full scan(`repo_structure.txt`, `collected.json`, `repo_root.rglob('*.py')`).
- Verification steps must include `py -3.11 VoiceCommand\\validate_repo.py --compile-only` 또는 `py -3.11 VoiceCommand\\validate_repo.py` and zero-affected `VoiceCommand.tests...` / `VoiceCommand/tests/...` test execution.
- `py_compile`, `tests/` 루트 경로, `&&` chains are prohibited.
- Always return only a JSON array.

Output format:
[
  {{
    "step_type": "shell",
    "content": "PowerShell command to execute",
    "description_kr": "Step description",
    "expected_output": "Expected output",
    "condition": "",
    "on_failure": "abort"
  }}
]
"""

_DEVELOPER_RETRY_PROMPT = """\
Save소 스캔이 끝났습니다. 이제 실제 코드를 수정하는 2steps 계획을 JSON 배열로 반환하세요.

Goal: {goal}
{context_block}
Rules:
- Save소 스캔/목록 조회 steps는 절대 포함하지 마세요. 이미 완료됐습니다.
- 정확히 2steps만 반환하세요: [코드_수정, 검증].
- 코드_수정 steps: 위 컨텍스트에서 파악한 실제 파일 하나를 선택해 `open(path, 'w')`나 `path.write_text()`로 내용을 수정하세요.
  반드시 실제 Python/shell 코드를 작성하세요. `print('edit one file')` 같은 자리표시자는 절대 금지입니다.
- 수정 대상은 `VoiceCommand/agent`, `VoiceCommand/core`, `VoiceCommand/ui`, `VoiceCommand/plugins`, `VoiceCommand/tests`, `docs` 범위 안에서만 고르세요.
- Verification steps must include `py -3.11 VoiceCommand\\validate_repo.py --compile-only` and zero-affected test execution.
- `py_compile`, `tests/` 루트 경로, `&&`, 전체 Save소 재스캔은 금지합니다.
- step_type은 "python" 또는 "shell"만 사용하세요.
- python steps에서는 `repo_root`, `module_dir`, `step_outputs`를 바로 사용할 수 있습니다.
- content는 실제 실행 가능한 코드여야 하며, 반드시 6줄 이하로 작성하세요 (1000 token 제한).
- Always return only a JSON array.

나쁜 예(금지):
[{{"step_type":"python","content":"print('edit one file')","description_kr":"파일 편집"}}]

좋은 예:
[
  {{"step_type":"python","content":"import os\\npath = os.path.join(repo_root,'VoiceCommand','agent','skill_library.py')\\ntext = open(path,'r',encoding='utf-8').read()\\ntext = text.replace('old_pattern','new_pattern',1)\\nopen(path,'w',encoding='utf-8').write(text)\\nprint('done')", "description_kr":"skill_library.py 패턴 수정","expected_output":"done"}},
  {{"step_type":"shell","content":"py -3.11 VoiceCommand\\\\validate_repo.py --compile-only; py -3.11 -m unittest VoiceCommand.tests.test_skill_library","description_kr":"Save소 검증과 zero향 테스트","expected_output":"compile-only checks passed"}}
]
"""

_FIX_PROMPT = """\
다음 코드/명령이 Error로 실패했습니다. 수정된 버전을 JSON으로 반환하세요.

원래 코드:
{content}

Error 메시지:
{error}

Goal: {goal}
{context_block}
수정 시 주의:
- Error 원인을 분석하고 근본적으로 수정하세요
- 동일한 방식으로 재시도하지 마세요
- Windows 바탕화면 경로: When running Python code 'desktop_path' variable is immediately available. os.path.join(desktop_path, '폴더명') Use in the form.
- Save소/코드 작업에서는 `repo_root`와 `module_dir`를 우선 사용하고, Desktop 경로를 추측하지 마세요.
- 경로나 실행 파일 위치를 하드코딩하지 말고, 런타임 탐색 또는 제공된 헬퍼를 사용하세요.
- 웹 검색이 필요하면 `web_search` / `web_fetch`를 사용하고, `YOUR_API_KEY` 같은 자리표시자는 절대 사용하지 마세요.
- 문서 Save은 가능하면 `save_document(...)` 도우미를 사용하세요.
- 파일 작업은 가능하면 `rename_file`, `merge_files`, `organize_folder`, `analyze_data`, `generate_report`, `detect_file_set`, `batch_rename_files` 도우미를 사용하세요.
- GUI/브라우저 자동화가 필요하면 가능한 한 내장 헬퍼(`open_url`, `launch_app`, `click_screen`, `type_text`, `wait_for_window`, `list_open_windows`, `get_desktop_state`, `browser_login`, `run_browser_actions`, `run_adaptive_browser_workflow`, `run_resilient_browser_workflow`, `run_desktop_workflow`, `run_adaptive_desktop_workflow`, `run_resilient_desktop_workflow`, `get_runtime_state`, `get_state_transition_history`, `get_learned_strategies`, `get_planning_snapshot`, `get_recovery_candidates`, `get_recovery_guidance`, `get_recent_goal_episodes` 등)를 사용하세요.
- 브라우저에서 리다이렉트/동적 로딩이 예상되면 `wait_url`, `wait_title`, `wait_selector` 같은 액션을 포함하세요.
- 이미 비슷한 전략이 있다면 `get_planning_snapshot_summary(goal_hint=...)`를 우선 참고하고, 필요할 때만 전체 `get_planning_snapshot(...)` 또는 `get_learned_strategies(...)`를 읽으세요.
- 브라우저 작업은 가능하면 `goal_hint`를 명시해 재사용 가능한 액션 전략을 남기세요.
- 기존 파일을 덮어썼다면 `get_backup_history()`를 OK하고 필요 시 `restore_last_backup(path)`로 복구하도록 수정하세요.
- `with`, `for`, `if`, `try` 같은 복합문은 세미콜론 한 줄 코드로 만들지 마세요. 여러 줄로 작성하세요.
- 반드시 JSON 객체만 반환하세요

Output format:
{{
  "step_type": "python",
  "content": "수정된 코드",
  "description_kr": "수정 이유",
  "expected_output": "Expected output"
}}"""

_VERIFY_PROMPT = """\
다음 실행 결과가 Goal를 달성했는지 평가하세요.

Goal: {goal}

실행 결과:
{results_summary}

평가 기준:
- 파일/폴더 생성 등 시스템 상태 변화는 코드 출력에 Error가 없을 때만 achieved=true
- steps 출력에 Error 메시지, 예외, "실패" 등이 포함되면 achieved=false
- 불확실하면 achieved=false

반드시 JSON 객체만 반환하세요:
{{
  "achieved": true,
  "summary": "달성 여부 한국어 요약 (1~2문장)"
}}"""

_REFLECT_PROMPT = """\
에이전트가 Goal 달성에 최종적으로 실패했습니다. 실패 원인을 분석하고 다음 시도를 위한 '교훈'을 JSON으로 작성하세요.

Goal: {goal}

실행 이력 요약:
{history_summary}

작성 Rules:
- 실패의 근본 원인을 기술하세요 (예: 라이브러리 부재, 권한 문제, 논리 Error 등)
- 다음 시도에서 반드시 피해야 할 접근법을 명시하세요
- 권장되는 대안 접근법을 한 문장으로 정리하세요
- 반드시 JSON 객체만 반환하세요

Output format:
{{
  "reason": "실패 원인",
  "avoid": "피해야 할 점",
  "lesson": "다음 시도를 위한 핵심 교훈"
}}"""

_DECOMPOSE_PROMPT_EN = """\
Return an execution plan as a JSON array to achieve the following goal.

Goal: {goal}
{context_block}
Rules:
- step_type: "python" (Python code), "shell" (CMD/PowerShell), "think" (analysis, no content)
- Simple tasks need only one step
- Write immediately executable code
- Use multi-line code for compound statements (with/for/if/try), not semicolons
- Previous step outputs are available as step_outputs dict (keys: "step_0_output", etc.)
- Set condition for steps that depend on previous results
- on_failure: "abort", "skip", or "continue"
- Windows desktop path: use 'desktop_path' variable directly in Python code
- Always ensure directories exist: os.makedirs(path, exist_ok=True)
- Use web_search(query) and web_fetch(url) instead of external APIs
- Use save_document(directory, base_name, content) for saving documents
- No YOUR_API_KEY or paid external API dependencies
- Return JSON array only

Output format:
[
  {{
    "step_type": "python",
    "content": "code to execute",
    "description_kr": "step description",
    "expected_output": "expected result",
    "condition": "",
    "on_failure": "abort"
  }}
]"""

_DEVELOPER_DECOMPOSE_PROMPT_EN = """\
Return an execution plan as a JSON array to achieve the following repository development goal.

Goal: {goal}
{context_block}
Rules:
- step_type: "python", "shell", or "think" only
- Return at most 4 steps
- shell steps use PowerShell commands
- shell commands assume repo root as working directory
- python steps can use repo_root and module_dir variables directly
- Keep content short and executable; do not paste entire file contents
- Previous step outputs available as step_outputs dict
- If no scan results yet, focus on information gathering only
- If scan results available, select one improvement task and modify one file at a time
- Limit target to VoiceCommand/agent, core, ui, plugins, tests, docs, validate_repo.py
- Use repo_root and module_dir for paths, do not hardcode
- Validation step must include: py -3.11 VoiceCommand\\validate_repo.py --compile-only
- No py_compile, no tests/ root path, no && chaining
- Return JSON array only

Output format:
[
  {{
    "step_type": "shell",
    "content": "PowerShell command",
    "description_kr": "step description",
    "expected_output": "expected result",
    "condition": "",
    "on_failure": "abort"
  }}
]
"""

_DEVELOPER_RETRY_PROMPT_EN = """\
Repository scan is complete. Return a 2-step plan as a JSON array to modify actual code.

Goal: {goal}
{context_block}
Rules:
- Do NOT include any scan/listing steps. They are already done.
- Return exactly 2 steps: [code_edit, validation]
- code_edit step: select one actual file from context and modify it using open(path,'w') or path.write_text()
  Write real Python/shell code. No placeholders like print('edit one file').
- Target files must be within: VoiceCommand/agent, core, ui, plugins, tests, docs
- Validation step must include: py -3.11 VoiceCommand\\validate_repo.py --compile-only
- No py_compile, no tests/ root path, no &&, no full repo re-scan
- step_type: "python" or "shell" only
- python steps can use repo_root, module_dir, step_outputs directly
- content must be executable code, max 6 lines
- Return JSON array only

Bad example (forbidden):
[{{"step_type":"python","content":"print('edit one file')","description_kr":"file edit"}}]

Good example:
[
  {{"step_type":"python","content":"import os\\npath = os.path.join(repo_root,'VoiceCommand','agent','skill_library.py')\\ntext = open(path,'r',encoding='utf-8').read()\\ntext = text.replace('old_pattern','new_pattern',1)\\nopen(path,'w',encoding='utf-8').write(text)\\nprint('done')", "description_kr":"Modify skill_library.py pattern","expected_output":"done"}},
  {{"step_type":"shell","content":"py -3.11 VoiceCommand\\\\validate_repo.py --compile-only; py -3.11 -m unittest VoiceCommand.tests.test_skill_library","description_kr":"Validate and run affected tests","expected_output":"compile-only checks passed"}}
]
"""

_FIX_PROMPT_EN = """\
The following code/command failed with an error. Return the fixed version as JSON.

Original code:
{content}

Error message:
{error}

Goal: {goal}
{context_block}
Fix guidelines:
- Analyze the root cause and fix it fundamentally
- Do not retry the same approach
- Windows desktop path: use 'desktop_path' variable directly in Python code
- For repo/code tasks, use repo_root and module_dir; do not guess Desktop path
- Do not hardcode paths or executable locations; use runtime discovery or provided helpers
- Use web_search / web_fetch for web access; no YOUR_API_KEY placeholders
- Use save_document(...) helper for saving documents when possible
- Use compound statements (with/for/if/try) on multiple lines, not semicolons
- Return JSON object only

Output format:
{{
  "step_type": "python",
  "content": "fixed code",
  "description_kr": "reason for fix",
  "expected_output": "expected result"
}}"""

_VERIFY_PROMPT_EN = """\
Evaluate whether the following execution results achieved the goal.

Goal: {goal}

Execution results:
{results_summary}

Criteria:
- For system state changes (file/folder creation), set achieved=true only when outputs contain no errors
- If any step output contains error messages, exceptions, or "failed", set achieved=false
- When uncertain, set achieved=false

Return JSON object only:
{{
  "achieved": true,
  "summary": "1-2 sentence summary of whether goal was achieved"
}}"""

_REFLECT_PROMPT_EN = """\
The agent ultimately failed to achieve the goal. Analyze the failure and write a 'lesson' for the next attempt as JSON.

Goal: {goal}

Execution history summary:
{history_summary}

Writing rules:
- Describe the root cause of failure (e.g., missing library, permission issue, logic error)
- Specify approaches that must be avoided in the next attempt
- Summarize the recommended alternative approach in one sentence
- Return JSON object only

Output format:
{{
  "reason": "root cause of failure",
  "avoid": "what to avoid",
  "lesson": "key lesson for the next attempt"
}}"""


