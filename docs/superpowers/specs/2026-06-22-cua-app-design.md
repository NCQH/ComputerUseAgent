# CUA App — Design Spec

- **Date:** 2026-06-22
- **Status:** Approved (design), pending implementation plan
- **Working dir:** `D:\CUAMake`

## 1. Mục tiêu

Xây dựng một ứng dụng **Computer-Use Agent (CUA)**: nhận yêu cầu bằng ngôn ngữ tự nhiên,
điều khiển máy tính/trình duyệt để thực hiện, cho phép người dùng **bổ sung yêu cầu real-time**
trong lúc agent đang chạy, và **dừng hỏi người dùng trước các hành động không thể hoàn tác**.

### Quyết định cốt lõi (đã chốt với user)

| Khía cạnh | Lựa chọn |
|---|---|
| Steering | Queue bất đồng bộ real-time — agent đọc queue ở ranh giới giữa các bước |
| Giao diện | Desktop GUI **và** CLI, dùng chung một lõi |
| Workflow | Web = Playwright · Desktop = pyautogui |
| Irreversible | Model tự gắn cờ **+** denylist cứng (2 lớp) |
| Provider | Đa-provider ngay từ đầu: Claude (Opus 4.8) + OpenAI computer-use |
| Desktop target | Sandbox Docker + VNC (cách ly, không tranh chuột với user) |
| Kiến trúc | Hướng A — modular monolith, lõi async, 4 interface sạch |

## 2. Kiến trúc module

```
cua/
├── core/
│   ├── session.py        # AgentSession: vòng lặp agent async, điều phối
│   ├── queue.py          # InputQueue: asyncio.Queue cho yêu cầu real-time
│   ├── events.py         # EventBus: phát event (step, screenshot, log, confirm)
│   ├── history.py        # Conversation/step history (messages, tool results)
│   └── safety.py         # IrreversibilityGate: denylist + đọc cờ model
├── providers/
│   ├── base.py           # CUAProvider (interface)
│   ├── anthropic.py      # AnthropicProvider (computer_20250124)
│   └── openai.py         # OpenAIProvider (computer_use_preview)
├── executors/
│   ├── base.py           # Executor (interface)
│   ├── web.py            # WebExecutor — Playwright
│   └── desktop.py        # DesktopExecutor — pyautogui qua Docker+VNC
├── ui/
│   ├── cli.py            # frontend CLI (prompt_toolkit)
│   └── gui.py            # frontend GUI (PySide6)
├── config.py             # provider, executor, denylist, API keys (env)
├── models.py             # dataclasses: Action, StepResult, ConfirmRequest...
└── __main__.py           # entrypoint: chọn ui + workflow + provider
```

### Bốn interface độc lập

- **CUAProvider** — ảnh + lịch sử → danh sách `Action` (+ cờ risky). Không biết executor.
- **Executor** — chụp ảnh & thực thi một `Action`. Không biết model.
- **AgentSession** — keo nối; không biết chi tiết hãng nào / màn hình nào.
- **ui/** — chỉ subscribe `EventBus` và gọi `session.submit()`; không chứa logic agent.

Đổi provider / executor / UI đều độc lập và test riêng được.

## 3. Vòng lặp agent, queue & steering

### Vòng đời phiên (`AgentSession.run`)

```
1. User submit yêu cầu đầu tiên → InputQueue
2. Vòng lặp:
   a. drain InputQueue → gộp mọi yêu cầu pending vào history     ◄── "check pending sau mỗi bước"
      (dạng user message "Yêu cầu bổ sung: ...")
   b. executor.screenshot() → ảnh hiện tại
   c. provider.next_actions(screenshot, history) → [Action...] (+ cờ irreversible)
   d. với mỗi Action:
        - IrreversibilityGate.check(action, context)
            • nếu cần xác nhận → phát ConfirmRequest, await user → từ chối thì bỏ/đổi hướng
        - executor.do(action) → StepResult
        - phát event StepResult + screenshot mới
   e. nếu provider báo done và queue rỗng → IDLE (chờ submit mới)
3. lặp lại
```

### Nguyên tắc steering không chặn

- `InputQueue` là `asyncio.Queue`. UI gọi `session.submit(text)` bất kỳ lúc nào, **không chặn** loop.
- Loop chỉ đọc queue ở bước (a) — ranh giới giữa hai bước → **không cắt ngang một action đang chạy dở**.
- User submit lúc agent đang `await` action dài → yêu cầu nằm sẵn trong queue, nhặt ở vòng kế tiếp.

### Trạng thái phiên

`IDLE → RUNNING → WAITING_CONFIRM → RUNNING → … → IDLE`. UI render theo state
(nút "Xác nhận/Từ chối" chỉ hiện khi `WAITING_CONFIRM`).

### Data flow

```
UI ──submit()──► InputQueue ──drain──► AgentSession ──► Provider (chọn action)
 ▲                                          │
 │                                          ▼
 └──── EventBus ◄──── StepResult/screenshot/ConfirmRequest ──── Executor
```

## 4. Lớp đa-provider

### Interface

```python
class CUAProvider(Protocol):
    async def next_actions(self, screenshot_b64: str, history: History) -> ProviderResponse: ...
# ProviderResponse = { actions: list[Action], done: bool,
#                      assistant_text: str, model_flagged_risky: bool }
```

### Action trung tính (không phụ thuộc hãng)

```
Action = Click(x,y,button) | Type(text) | Key(combo) | Scroll(x,y,dir,amt)
       | Move(x,y) | Drag(x1,y1,x2,y2) | Screenshot() | Wait(ms)
```

Mỗi provider dịch xuôi/ngược giữa Action trung tính ↔ định dạng hãng.

| | AnthropicProvider | OpenAIProvider |
|---|---|---|
| API | Messages API, tool `computer_20250124` | Responses API, tool `computer_use_preview` |
| Vòng lặp | tự nối messages + `tool_result` (kèm ảnh) | `previous_response_id` + gửi lại screenshot |
| Dịch action | `tool_use.input.action` → Action | `computer_call.action` → Action |
| Cờ risky | parse assistant text (system prompt yêu cầu khai báo) + heuristic | map từ `pending_safety_checks` |

- OpenAI có sẵn `pending_safety_checks` → map thẳng vào `model_flagged_risky`.
- Claude không có field tương đương → system prompt yêu cầu model khai báo trước hành động
  không hoàn tác; vẫn dựa vào **denylist cứng** làm lưới an toàn chung.
- Chọn provider qua `config.py` / `--provider claude|openai`.
- Toạ độ: Executor cung cấp `display_size`; provider chuẩn hoá toạ độ về đúng khung ảnh.

## 5. Lớp executor + cổng an toàn

### Interface

```python
class Executor(Protocol):
    display_size: tuple[int, int]
    async def screenshot(self) -> str: ...   # base64 PNG
    async def do(self, action: Action) -> StepResult: ...
    async def start(self) -> None: ...
    async def close(self) -> None: ...
```

### WebExecutor (Playwright)

- Mở Chromium context riêng. `screenshot()` = `page.screenshot()`.
- `do(action)`: map Action → Playwright (ưu tiên DOM khi có thể, vẫn theo toạ độ pixel để
  khớp mô hình computer-use).
- Chạy trên host, browser tách biệt → không tranh chuột với user.

### DesktopExecutor (pyautogui + Docker+VNC)

- Container Linux: Xvfb + màn hình ảo + VNC server + pyautogui (ý tưởng từ image Anthropic).
- Core nói chuyện với **HTTP agent nhỏ trong container** (`/screenshot`, `/do`) thay vì
  pyautogui ở host → cách ly hoàn toàn; user xem qua VNC (port map ra host).
- `display_size` = độ phân giải màn hình ảo (vd 1280×800).

### IrreversibilityGate (chạy trước `executor.do()`)

```
check(action, context) →
  1. DENYLIST cứng → BẮT BUỘC xác nhận
     • web: click nút/text khớp {submit, mua, thanh toán, xoá, gửi, confirm, delete...}
     • desktop: Enter sau lệnh xoá, click vùng nút nguy hiểm (heuristic theo nhãn)
     • mọi Key kết hợp phá huỷ (vd Ctrl+Shift+Del)
  2. CỜ MODEL: provider trả model_flagged_risky → BẮT BUỘC xác nhận
  3. ngược lại → cho qua
```

- Cần xác nhận → `WAITING_CONFIRM`, phát `ConfirmRequest(action, lý do)`, **await** user
  (GUI: nút; CLI: y/n). Từ chối → bỏ action, ghi vào history để model đổi hướng.
- Denylist trong `config.py`, sửa được; mặc định thiên an toàn (thà hỏi thừa).
- Mỗi Executor cung cấp "context action" (nhãn nút, text gần đó) cho Gate chấm. Gate
  **không** gọi executor — chỉ nhận context kèm theo.

## 6. Xử lý lỗi

| Tầng | Lỗi điển hình | Cách xử lý |
|---|---|---|
| Provider | API timeout, rate-limit, 5xx | Retry backoff (tối đa N). Hết → `ErrorEvent`, về IDLE, giữ history. |
| Executor | element mất, container chết | `StepResult(success=False, error)`. Đưa lỗi vào history → model tự thử lại. |
| Action không hợp lệ | toạ độ ngoài màn hình | Validate ở `models.py` trước `do()`. Fail fast, log, vào history. |
| Container/VNC | Docker chưa chạy, port bận | Kiểm tra khi `start()`. Lỗi rõ ràng, không crash âm thầm. |
| Confirm bị bỏ | user đóng app lúc WAITING_CONFIRM | Mặc định = từ chối (an toàn), dừng sạch. |

- Mọi lỗi phát `ErrorEvent` → UI hiển thị thân thiện; log chi tiết ra `logs/`.
- Loop có **giới hạn bước** (max steps) chống lặp vô hạn → đạt ngưỡng thì dừng hỏi user.

## 7. Testing (mục tiêu ≥80%, AAA)

| Loại | Phạm vi |
|---|---|
| Unit | IrreversibilityGate (denylist + cờ model), dịch Action↔hãng mỗi provider, InputQueue drain/gộp, state machine AgentSession. |
| Integration | AgentSession với **FakeProvider** + **FakeExecutor**: kiểm steering gộp pending đúng lúc, gate chặn đúng action, lỗi đẩy vào history. Không gọi API/Docker thật. |
| E2E (nhẹ) | Web: Playwright thật trên trang test tĩnh local. Desktop: smoke test container khởi động + chụp 1 ảnh. |

Vì Provider & Executor là interface → lõi test hoàn toàn bằng fake (không token, không Docker,
nhanh trong CI). API/Docker thật chỉ đụng ở vài E2E tách riêng.

## 8. Tham khảo

- Anthropic `anthropic-quickstarts/computer-use-demo` — tham khảo *ý tưởng* loop + tool schema
  + image Docker desktop; **không** fork làm nền (UI Streamlit + khoá Claude, ngược yêu cầu).
- Claude computer-use tool: `computer_20250124`.
- OpenAI computer-use: model `computer-use-preview`, Responses API, tool `computer_use_preview`,
  `pending_safety_checks`.

## 9. Ngoài phạm vi (YAGNI)

- Client-server / websocket (Hướng B) — chỉ nâng cấp khi cần nhiều frontend đồng thời.
- Web UI từ xa.
- Đa người dùng / xác thực.
- Lưu/replay phiên lâu dài (chỉ history trong RAM cho phiên hiện tại).
