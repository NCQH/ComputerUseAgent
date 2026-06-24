---
harness_version: 2.4.2
harness_kit_digest: 1c98396e54bbdb33c401c7eb032e46c66d654b4e52ab2c2eb839ab0fcba6a398
harness_schema_version: 1.0
---

# CUAMake — Consolidated Spec Roadmap

> Status: **DRAFT for review** · Created 2026-06-24 · Single source of truth for all proposed specs.
> **Confirmed scope:** CUA controls exactly two surfaces — **`local`** (real host desktop, pyautogui)
> and **`web`** (Playwright). Sandbox / VM / container is **rejected and out of scope**
> (memory `cua-project-scope`). The executor axis is fixed at `{local, web}`; only the
> **provider** axis grows.
>
> Because there is **no sandbox**, in-process safety is the *only* net — this is why
> SPEC-4 (Safety) is the top priority.

---

## Priority summary

| # | Spec | Priority | Effort | Depends on | Status |
|---|------|----------|--------|-----------|--------|
| **SPEC-4** | Safety / Policy v2 | **P1 — critical** | M | — | Detailed below |
| **SPEC-3** | Trajectory recording + telemetry | **P2** | S–M | — | Specced |
| **SPEC-2** | Accessibility-tree provider (desktop SoM) | **P3** | M–L | (SPEC-3 helps) | Specced |
| **SPEC-5** | Provider registry / plugin discovery | **P4** | S–M | — | Specced |
| **SPEC-6** | Hybrid grounding (provider composition) | **P5** | L | SPEC-2, SPEC-5 | Specced |
| **SPEC-0** | Rename `cua` package | **P6 — only if public** | S | — | Specced |
| ~~SPEC-1~~ | ~~Sandbox / VM executor~~ | **DROPPED** | — | — | Out of scope |

**Ordering principle:** criticality × dependency, then effort. SPEC-4 is the lone
safety net (no sandbox). SPEC-3 is cheap, depends on nothing, and multiplies every
later effort (debug + eval). SPEC-2 raises core desktop accuracy. SPEC-5 lets the
provider matrix grow cleanly. SPEC-6 builds on 2+5. SPEC-0 only matters if going public.

---

# P1 · SPEC-4 — Safety / Policy v2

## Why
The `IrreversibilityGate` is not *a* safety net — it is the **only** one. A wrong
click in `local` mode hits your real machine; a wrong "Send/Delete" hits real data.
Current gaps (`cua/core/safety.py`):
- **Binary verdict only** — "run" or "ask"; no "**never run, even if confirmed**".
- **Context-blind** — ignores the active window / URL. Typing a password into a
  banking page vs. a text editor look identical to it. The single highest-value
  desktop safety signal — *what am I acting on* — is unused.
- **Not composable** — denylist + key-combos + model-flag hard-coded in one method.
- **No audit trail** — nothing records what was gated / approved / rejected / run.
  With no sandbox to roll back, an append-only log is the only forensic record.

## Goals / Non-goals
**Goals:** G1 three-state verdict `ALLOW/CONFIRM/BLOCK`; G2 composable policy chain;
G3 context-aware (active app/window/URL); G4 sensitive-context policy (banking,
password managers, OS credential dialogs → escalate to ≥CONFIRM); G5 append-only
JSONL audit; G6 100% back-compat (existing 181 tests stay green).
**Non-goals:** numeric risk scoring (KISS — enum is enough); sandbox/VM; coordinate-
region host whitelisting; ML intent classification; changing confirm UX.

## Current state (ground truth)
- `cua/core/safety.py` — `IrreversibilityGate`, `DEFAULT_DENYLIST`,
  `DESTRUCTIVE_KEY_COMBOS`. Already uses `\b` word-boundary regex (keep).
- `cua/core/session.py:151` — single call site:
  `needs, reason = self.gate.needs_confirmation(action, resp.assistant_text, resp.model_flagged_risky)`.
- `cua/models.py` — `Action`, `ConfirmRequest(action, reason)`.
- `cua/executors/{base,local,web}.py` — neither surfaces active window / URL yet.

## Design

### Verdict + context types (`cua/core/safety.py`)
```python
class Verdict(Enum):
    ALLOW = "ALLOW"      # run, no prompt
    CONFIRM = "CONFIRM"  # pause, ask
    BLOCK = "BLOCK"      # refuse; never run even if user says yes

@dataclass(frozen=True)
class SafetyContext:
    executor: str                    # "local" | "web"
    active_title: str | None = None  # focused window title (local)
    url: str | None = None           # page URL (web)

@dataclass(frozen=True)
class PolicyResult:
    verdict: Verdict
    reason: str
    policy: str                      # which policy fired
```

### Policy protocol + chain
```python
class Policy(Protocol):
    name: str
    def evaluate(self, action, description, model_flagged, ctx) -> PolicyResult | None:
        """Assert a verdict, or None to abstain."""

class PolicyChain:
    """Evaluate all policies (full audit record), take most-severe verdict.
    Severity: BLOCK > CONFIRM > ALLOW. Empty/all-abstain => ALLOW."""
```

### Built-in policies (refactor existing + new)
| Policy | Can assert | Source |
|--------|-----------|--------|
| `ModelRiskPolicy` | CONFIRM | existing `model_flagged` branch |
| `DestructiveKeyPolicy` | CONFIRM (BLOCK for catastrophic set? OQ-3) | existing key-combo branch |
| `DenylistPolicy` | CONFIRM | existing EN+VI denylist, matching unchanged |
| `SensitiveContextPolicy` | CONFIRM | **new** — `ctx.active_title`/`url` matches sensitive set (banking, `*.bank`, keepass/1password/bitwarden, Windows "Credential", "ngân hàng", "mật khẩu"…) |
| `AuditPolicy` | abstains | **new** — pure side-effect sink |

`IrreversibilityGate` becomes a thin wrapper building the default `PolicyChain`,
keeping a **back-compat** `needs_confirmation() -> (bool, str)` (maps `CONFIRM|BLOCK
-> (True, reason)`), plus a new `decide() -> PolicyResult` for the session.

### Session wiring (`cua/core/session.py`)
```python
ctx = await self._safety_context()                    # best-effort
result = self.gate.decide(action, resp.assistant_text, resp.model_flagged_risky, ctx)
self.audit.record(action, result, ctx)
if result.verdict is Verdict.BLOCK:
    self.history.add_error(f"BLOCKED by {result.policy}: {result.reason}")
    continue                                          # never executes
if result.verdict is Verdict.CONFIRM:
    ... existing confirm flow, reason=result.reason ...
# ALLOW or approved CONFIRM -> execute
```

### Audit log
`cua/core/audit.py` — `AuditSink` writing append-only JSONL, one record per gated
action `{ts, executor, action, verdict, policy, reason, ctx, approved}`. Default
path `./.cua/audit/<session-id>.jsonl` (gitignore `.cua/`). `NullAuditSink` for tests,
injected like `clock`/`sleep` already are.

### SafetyContext from executors (optional capability, not a breaking change)
```python
async def context(self) -> SafetyContext: ...   # optional on Executor
```
- `WebExecutor.context()` → `SafetyContext("web", url=self.page.url)`.
- `LocalExecutor.context()` → `SafetyContext("local", active_title=<focused window>)`
  via `pygetwindow`/`pywinctl` (lazy; degrade to `None` if dep/title missing —
  same graceful pattern as OCR). Gate behind the `[local]` extra.
- `AgentSession._safety_context()` calls it via `getattr` if present, else minimal.

## Config
```python
@dataclass(frozen=True)
class SafetyConfig:
    denylist: list[str] | None = None
    sensitive_titles: list[str] | None = None
    sensitive_url_patterns: list[str] | None = None
    catastrophic_keys: list[str] = field(default_factory=list)  # -> BLOCK
    audit_enabled: bool = True
```
Wired in `cua/app.py:build_session`; optional CLI flags later (`--no-audit`, `--safe-mode`).

## Test plan (TDD, ≥80%)
Pure unit (`tests/test_safety_policy.py`): each policy verdict/abstain; chain severity
aggregation; `SensitiveContextPolicy` banking title/URL → CONFIRM on plain `Click`,
benign → abstain, VI keywords; back-compat `needs_confirmation()` matches current
tests; `AuditSink` writes JSONL / `NullAuditSink` no-op. Session integration (fakes):
BLOCK → never reaches executor; CONFIRM+reject → not executed; CONFIRM+approve / ALLOW
→ executed; audit recorded every branch. Whole suite stays green (181 passed).

## Rollout
1. Types + `PolicyChain` + built-ins (keep gate API). 2. Port existing safety tests.
3. Audit sink. 4. Executor `context()` + session helper. 5. `SensitiveContextPolicy`
last. 6. `.gitignore`: add `.cua/`. Each step independently shippable + test-gated.

## Risks
- R1 `pygetwindow` cross-OS reliability → optional, degrade to `None`.
- R2 false BLOCKs frustrate → BLOCK set starts empty; default stays CONFIRM (today's behaviour).
- R3 audit may log typed passwords (`Type.text`) → **redact in sensitive context (OQ-5)**.

## Open questions
- OQ-1 3-state `ALLOW/CONFIRM/BLOCK`, or keep binary + only add context/audit (smaller)?
- OQ-2 add `policy: str` to `ConfirmRequest` so UI shows which rule fired?
- OQ-3 any key combo = `BLOCK` (never run)? candidate catastrophic set?
- OQ-4 config dataclass-in-code vs external `safety.yaml`?
- OQ-5 redact `Type.text` in audit when sensitive context? (lean **yes**)
- OQ-6 `pygetwindow` vs `pywinctl` for local active-window title?
- OQ-7 audit path `./.cua/audit/` acceptable?

---

# P2 · SPEC-3 — Trajectory recording + telemetry

## Why
No persistence, no replay, no metrics (flagged P1/P2 in the audits). With no sandbox,
a recorded trajectory is also the post-hoc record of "what did the agent actually do".
Cheap, depends on nothing, and multiplies every later effort (debug + eval/benchmark).

## Design
- A subscriber on the existing `EventBus` (it already publishes `ScreenshotTaken`,
  `StepCompleted`, `ConfirmRequested`, `StateChanged`, `LogMessage`, `ErrorOccurred`).
- `cua/telemetry/recorder.py` — writes a per-session **trajectory**: JSONL of
  `(step, ts, screenshot_ref, action, result, model_text, verdict, timing_ms)`.
  Screenshots saved as files (`./.cua/runs/<session>/NNN.png`), referenced by path
  to keep JSONL small.
- Optional **replay viewer** (later): a tiny static HTML that scrubs through the
  trajectory (screenshot + action overlay). Not required for v1.
- Aggregate counters: steps, confirms, rejects, blocks, provider retries, wall-clock.

## Interface
```python
class TrajectoryRecorder:           # EventBus subscriber
    def __init__(self, run_dir: Path): ...
    def on_event(self, event) -> None: ...   # dispatch by event type
```
Wire in `cua/app.py`; off by default in tests (don't subscribe), or inject a `Null`
recorder. **Zero changes to core logic** — purely additive subscriber.

## Effort: S–M. Depends on: nothing.
## Open questions
- OQ-3a screenshots: every step (storage cost) or only on change / on confirm?
- OQ-3b reuse `.cua/` dir (shared with SPEC-4 audit) — one run dir per session?
- OQ-3c is the replay viewer wanted in v1, or JSONL only?

---

# P3 · SPEC-2 — Accessibility-tree provider (desktop Set-of-Marks)

## Why
On the desktop surface, grounding today is **vision-only** (`GenericVisionProvider`:
OCR + grid) — the least precise option. The web surface already has the far more
reliable **DOM Set-of-Marks** (`DomVisionProvider`). The desktop analog is the
**accessibility tree** (Windows UIA / macOS AX / Linux AT-SPI): enumerate real UI
elements with their bounds, number them, Set-of-Marks, let the model pick by id.
This **completes the "all grounding paradigms" thesis on desktop** and is genuinely
differentiating — no small project pairs DOM-SoM + a11y-SoM + vision-SoM behind one
interface.

## Design
- `cua/providers/a11y/provider.py` — `A11yVisionProvider`, mirroring
  `cua/providers/browser/provider.py` exactly:
  - enumerate interactive elements from the platform a11y API → `[{id, role, name, bounds}]`
  - reuse `vision/imaging.py` (`annotate_marks`, `overlay_grid`) for the overlay
  - reuse `vision/actions.py` (`ACTION_SCHEMA`, `parse_action`) for output
  - model targets by mark id; fall back to grid/point when the element isn't listed
    (same `_targeting_hint` contract).
- Platform backends behind one tiny interface (`elements() -> list`):
  - Windows: UIA via `pywinauto` / `uiautomation`
  - macOS: AX via `pyobjc` (ApplicationServices)
  - Linux: AT-SPI via `pyatspi`
  Lazy-imported; absent backend → empty list → graceful degrade to grid/point
  (never crash — same pattern as `_elements()` in the browser provider).
- New factory key `a11y` in `cua/config.py:build_provider` (paired with `--executor local`).

## Interface
```python
class A11yVisionProvider:           # same shape as DomVisionProvider
    def __init__(self, client, backend, model, display_size, use_grid=True): ...
    async def next_actions(self, screenshot_b64, history) -> ProviderResponse: ...
```

## Effort: M–L (one a11y backend per OS; ship Windows first per the dev's platform).
## Depends on: nothing hard; SPEC-3 telemetry helps measure the accuracy gain.
## Open questions
- OQ-2a ship Windows-only (UIA) first, defer macOS/Linux?
- OQ-2b library choice for Windows UIA: `uiautomation` vs `pywinauto`?
- OQ-2c how to scope element enumeration to the focused window (perf — full desktop
  tree can be huge)?

---

# P4 · SPEC-5 — Provider registry / plugin discovery

## Why
`cua/config.py` is an if/elif factory; it already handles 4 providers and will get a
5th (a11y) and 6th. The "matrix" thesis needs providers/executors to be **pluggable**,
not hand-edited (audit P2).

## Design
- Registry keyed by name; providers/executors register via `importlib.metadata`
  entry-points (e.g. `cua.providers`, `cua.executors`).
- `build_provider`/`build_executor` resolve from the registry; unknown name → clear
  error listing registered names.
- Built-ins register themselves; third-party packages can add a provider without
  forking `config.py`.

## Effort: S–M. Depends on: nothing (but pairs naturally before SPEC-6).
## Open questions
- OQ-5a entry-points (heavier, real plugins) vs a simple internal decorator registry
  (lighter, no third-party plugins)? KISS may favour the latter given personal-tool scope.

---

# P5 · SPEC-6 — Hybrid grounding (provider composition)

## Why
Every provider does planning **and** grounding in one call. Stronger systems
(Agent-S2's "mixture of grounding") split them: a **planner** decides *what* to do;
a **grounding** provider returns *precise coordinates*. This is the natural evolution
of CUAMake's orthogonal-axes idea — now the provider axis itself becomes composable.

## Design
- A `CompositeProvider(planner, grounder)`:
  - planner (e.g. Claude / a vision model) emits an intent + target description
  - grounder (DOM-SoM for web, a11y-SoM for desktop) resolves the description to a
    concrete mark/coordinate
- Requires a small contract extension so a provider can expose "ground this
  description → coordinate" separately from "decide next action".

## Effort: L (touches the `next_actions` contract). Depends on: SPEC-2 + SPEC-5.
## Open questions
- OQ-6a is this worth it for a personal tool, or is it over-engineering (YAGNI)?
  Revisit only after SPEC-2/4/3 land and real grounding-accuracy pain is observed.

---

# P6 · SPEC-0 — Rename `cua` package (only if going public)

## Why
Hard name collision with **`trycua/cua`** (18.8k★, same niche, package `cua`). Both
project name and PyPI package would clash. Blocks a clean public/PyPI release.

## Design
- Pick a free name (check PyPI + GitHub). Rename the `cua/` package dir, `pyproject`
  `name`, `python -m <pkg>` entrypoint, imports, README.
- Pure mechanical refactor; one PR; tests guard it.

## Effort: S. Depends on: nothing. **Trigger: only if/when publishing.**
## Open questions
- OQ-0a are we going public at all? If never, this is moot.
- OQ-0b candidate names?

---

# Global decision log (fill during review)

| Decision | Choice |
|----------|--------|
| Build order confirmed? | Shared `.cua/` audit infra + SPEC-4 core first (DONE 2026-06-24) |
| SPEC-4 OQ-1 verdict states | **3-state ALLOW/CONFIRM/BLOCK**, BLOCK set empty by default (default behaviour == old binary gate) |
| SPEC-4 OQ-5 redaction | **Yes, mandatory** — `Type.text` redacted in audit on sensitive context (`«redacted»`) |
| SPEC-4 OQ-6 window lib | `pygetwindow` (lazy, `[local]` extra; degrade to `None`) |
| SPEC-2 OQ-2a Windows-first | **Yes** — Windows UIA only; macOS AX / Linux AT-SPI deferred behind same `A11yBackend` interface |
| SPEC-2 OQ-2b UIA library | **`uiautomation`** (gentler API for enumerate + bounds than pywinauto) |
| SPEC-2 OQ-2c element scope | Foreground window only (`GetForegroundControl`), depth+count capped |
| SPEC-5 OQ-5a registry style | **Lightweight internal decorator registry** — NO entry-points/third-party plugins (YAGNI for a personal tool) |
| SPEC-0 going public? | (pending) |

## SPEC-4 — implemented 2026-06-24
- `cua/core/safety.py`: `Verdict`, `SafetyContext`, `PolicyResult`, `SafetyConfig`, `Policy`
  protocol, `PolicyChain` (most-severe; ties→first policy, preserving reason strings),
  built-ins `ModelRiskPolicy`/`DestructiveKeyPolicy`(+catastrophic BLOCK)/`DenylistPolicy`/
  `SensitiveContextPolicy`. `IrreversibilityGate` keeps back-compat `needs_confirmation()`,
  adds `decide()`, `is_sensitive_context()`, `from_config()`.
- `cua/core/audit.py`: `AuditSink` (append-only JSONL) + `NullAuditSink`; `Type.text` redaction.
- `cua/core/session.py`: ctx fetched per-step via optional `executor.context()`; BLOCK never
  executes; every gated action audited (BLOCK/CONFIRM/ALLOW).
- `cua/executors/{web,local}.py`: optional `context()` (URL / focused-window title, graceful).
- `cua/app.py`: builds gate from `SafetyConfig`, wires `AuditSink` (`.cua/audit/<sid>.jsonl`).
- `.gitignore`: `.cua/`. Tests: +45 (`test_safety_policy`, `test_audit`, `test_session_safety`);
  suite 181→226 passed, 0 regressions.

## SPEC-3 — implemented 2026-06-24
- `cua/telemetry/recorder.py`: `TrajectoryRecorder` — pure `EventBus` subscriber (`on_event`),
  zero core changes. Writes `.cua/runs/<sid>/trajectory.jsonl` (one row/step:
  `step, ts, screenshot_ref, action, result`) + `NNN.png` screenshots referenced by path.
  Aggregate `counters`/`summary()` (steps, confirms, blocks, errors).
- OQ-3a: one screenshot per step. OQ-3b: one run dir per session under `.cua/` (shared root
  with SPEC-4 audit). OQ-3c: replay viewer deferred — JSONL only for v1.
- `cua/app.py`: subscribes a recorder by default (`trajectory_enabled`, `runs_dir`); shares `sid`
  with audit. Both sinks **mkdir lazily on first write** (building a session that never runs
  touches no disk — no test pollution).
- Tests: +4 (`test_trajectory`); suite 226→230 passed, 0 regressions.

## SPEC-2 — implemented 2026-06-24 (Windows-first)
- `cua/providers/a11y/uia_backend.py`: `UiaBackend` walks the foreground window's UIA
  tree (`uiautomation`, lazy + fully guarded → [] on absent lib / COM error / non-Windows);
  emits the SAME raw record shape as the DOM backend (`x,y,width,height,tag,role,type,text`),
  so `dom_marks.parse_elements/boxes_of/describe` are reused verbatim (DRY). `NullBackend`
  for tests / unsupported platforms.
- `cua/providers/a11y/provider.py`: `A11yVisionProvider` — desktop twin of `DomVisionProvider`,
  same Set-of-Marks contract, reuses `vision.{imaging,actions}` + `_targeting_hint`/
  `summarize_history`. Desktop system prompt; degrades to grid/point when the tree is empty.
- `cua/config.py`: `build_provider("a11y"|"uia")` → `A11yVisionProvider(UiaBackend())`.
- `cua/__main__.py`: `--provider a11y|uia`; guard — a11y requires `--executor local` (rejects web).
- `pyproject.toml` `[local]`: `uiautomation` (win32 marker) + `pygetwindow` (SPEC-4 dep).
- Tests: +14 (`test_a11y_provider`, `test_a11y_backend`, +config/+main-args); suite 230→244, 0 regressions.
- NOTE: backend logic is unit-tested against fakes; the *real* UIA walk needs a manual smoke
  on the Windows desktop (no live-API coverage in CI).

## SPEC-5 — implemented 2026-06-24
- `cua/registry.py`: `Registry` (decorator `register(*names)`, `create(name, **kw)`, `names()`);
  module-level `PROVIDERS` / `EXECUTORS`. Internal only — no `importlib.metadata` entry-points
  (OQ-5a KISS). Unknown name → `ValueError` listing registered names.
- `cua/config.py`: rewrote the 7-branch provider + 2-branch executor if/elif as registered
  factories; same lazy-client / page-required / environment-threading behaviour preserved.
  `build_provider`/`build_executor` kept as thin wrappers (unchanged signatures → app.py untouched).
- Tests: +4 (`test_registry`); all existing config/executor/build_session tests green.
  Suite 244→248, 0 regressions.

## NOT done (gated by the plan's own analysis — need a decision/signal, not code)
- **SPEC-6 (hybrid grounding)** — OQ-6a: revisit only after real grounding-accuracy pain is
  observed on SPEC-2. None observed yet → YAGNI. Touches the `next_actions` contract; do not
  build on theory.
- **SPEC-0 (rename `cua`)** — trigger is "only if publishing"; OQ-0a (going public?) unanswered.
