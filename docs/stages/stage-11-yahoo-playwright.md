# Stage 11: Playwright Yahoo Draft Room Bridge

## Before starting, read:
- `docs/LIVE_DRAFT.md` — full bridge spec
- `docs/rules/PATTERNS.md` — Pattern 7: No polling, Pattern 9: Model strings

---

## Goal
The app controls Yahoo's draft room directly. Nominations, bids, and live draft
events all flow through the app — no Yahoo tab needed during the auction.
Zero lag. Zero polling. Graceful failure handling at every layer.

---

## Why this stage is high risk
Playwright automation against a live JavaScript web app is the most brittle
component in the entire system. Yahoo can update their frontend and break
selectors. WebSocket frame formats can change. The browser instance can
drop its connection. Any of these mid-draft is catastrophic.

The solution is layered redundancy and explicit failure handling — not
hoping nothing goes wrong.

---

## Step 1 — Ask user before writing any code

**ASK USER for all of the following before touching any implementation:**

1. "Can you navigate to your Yahoo fantasy league page and share the URL 
   format for the draft room? It usually looks like:
   `https://football.fantasysports.yahoo.com/f1/{league_id}/draftclient`"

2. "We need to capture real Yahoo WebSocket frames for the test suite.
   Please do the following:
   - Open a Yahoo fantasy draft room (last year's recap works, or the 
     practice draft if available)
   - Open Chrome DevTools (F12) → Network tab → filter by WS
   - Look for the WebSocket connection to Yahoo
   - Click on it and go to the Messages tab
   - Record the raw payload for at least one of each:
     * Nomination event (player nominated, clock starts)
     * Bid update (someone bids, price changes)
     * Draft pick confirmed (player goes off board)
     * Clock warning (low time remaining)
   - Share those raw JSON payloads
   These go in tests/fixtures/yahoo_ws_frames.json and are required 
   for the test suite."

Do NOT proceed to implementation until both items are provided.

---

## Step 2 — Architecture (read before writing any code)

The full event chain — zero polling at every layer:

```
Yahoo Server
  ↓ (Yahoo pushes WS frames)
Playwright browser instance
  ↓ page.on("websocket") → frame handler fires on receipt
YahooPlaywrightBridge
  ↓ parses frame → emits structured event
FastAPI WebSocket manager
  ↓ pushes to connected React clients
React draft UI (Zustand store update → re-render)

User action (bid/nominate)
  ↑ React → POST to FastAPI endpoint
  ↑ FastAPI → bridge.place_bid() or bridge.nominate_player()
  ↑ Playwright → page.evaluate() or page.click() in Yahoo tab
  ↑ Yahoo draft room executes action
```

Every layer is push-based. If you find yourself writing `asyncio.sleep()`
inside an event handler or `setInterval` in the frontend, stop and redesign.
`asyncio.sleep()` is only acceptable in `health_check_loop()` with a comment
explaining why.

---

## Step 3 — Implementation

### File: `backend/integrations/yahoo_playwright.py`

```python
class YahooPlaywrightBridge:
    """
    Controls Yahoo Fantasy draft room via Playwright.
    
    Primary event source: WebSocket frame interception
    Secondary fallback: MutationObserver on key DOM elements
    Health check: ping every 10 seconds, auto-reconnect on failure
    
    NEVER use time.sleep() or asyncio.sleep() in event handlers.
    ALWAYS call on_bridge_failure() before raising any exception.
    """
    
    def __init__(self, ws_manager: WebSocketManager):
        self.ws_manager = ws_manager
        self.page = None
        self.browser = None
        self._connected = False
        self._draft_room_url = None
    
    async def connect(self, draft_room_url: str) -> None:
        """
        Launch browser, authenticate, connect to draft room.
        Sets up WS interception and MutationObserver fallback.
        Starts health check loop.
        """
    
    async def _setup_websocket_interception(self, page) -> None:
        """
        Primary event source.
        Intercepts Yahoo's own WS connection to their servers.
        Fires on every frame Yahoo receives — no polling.
        """
        async def handle_ws(ws):
            async def handle_frame(frame):
                try:
                    data = self._parse_yahoo_frame(frame.payload)
                    if data:
                        await self._dispatch_event(data)
                except Exception as e:
                    logger.error("Frame parse error: %s", e)
                    # Don't crash on bad frames — log and continue
            ws.on("framereceived", handle_frame)
        page.on("websocket", handle_ws)
    
    async def _inject_mutation_observer(self, page) -> None:
        """
        Secondary fallback.
        Watches DOM for changes Yahoo's UI makes after receiving events.
        Catches anything WS interception misses.
        Only fires on actual DOM mutations — no polling.
        """
        observer_script = """
        const observer = new MutationObserver((mutations) => {
            // Detect nomination panel appearing
            // Detect bid price updating
            // Detect player card appearing in draft board
            // Send to Python via window.__playwright_bridge_event__
        });
        observer.observe(document.body, { childList: true, subtree: true });
        """
        await page.evaluate(observer_script)
    
    async def _parse_yahoo_frame(self, payload: str) -> dict | None:
        """
        Parse a raw Yahoo WebSocket frame into a structured event.
        Returns None for frames that aren't draft events we care about.
        
        Frame types to handle:
        - nomination: player nominated, clock started
        - bid_update: current bid price changed
        - draft_pick: pick confirmed, player off board  
        - clock_warning: N seconds remaining
        - clock_expired: nomination clock ran out
        """
    
    async def _dispatch_event(self, event: dict) -> None:
        """
        Route parsed event to FastAPI WebSocket manager.
        Manager pushes to all connected React clients.
        """
        await self.ws_manager.broadcast(event)
    
    async def nominate_player(
        self, yahoo_player_id: str, opening_bid: int
    ) -> None:
        """
        Trigger nomination in Yahoo draft room.
        Uses page.evaluate() to interact with Yahoo's JS directly,
        falls back to page.click() on the nominate button.
        """
        try:
            await self._execute_action("nominate", {
                "player_id": yahoo_player_id,
                "bid": opening_bid
            })
        except Exception as e:
            await self.on_bridge_failure(
                action="nominate",
                details=f"Player {yahoo_player_id} at ${opening_bid}"
            )
    
    async def place_bid(self, amount: int) -> None:
        """Submit a bid in the current nomination."""
        try:
            await self._execute_action("bid", {"amount": amount})
        except Exception as e:
            await self.on_bridge_failure(
                action="bid",
                details=f"${amount}"
            )
    
    async def pass_nomination(self) -> None:
        """Pass on current nomination."""
        try:
            await self._execute_action("pass", {})
        except Exception as e:
            await self.on_bridge_failure(action="pass", details="")
    
    async def health_check_loop(self) -> None:
        """
        Ping draft room every 10 seconds.
        Attempt reconnect if connection dropped.
        This is the ONLY place asyncio.sleep() is acceptable in this file.
        """
        while True:
            await asyncio.sleep(10)  # Health check interval — not polling
            if not await self._ping_draft_room():
                logger.warning("Bridge health check failed — reconnecting")
                await self._reconnect()
    
    async def on_bridge_failure(
        self, action: str, details: str = ""
    ) -> None:
        """
        MANDATORY: Call this before any exception propagates.
        Emits MANUAL_ACTION_REQUIRED to the React UI immediately.
        User sees exactly what to do manually in Yahoo tab.
        Never crashes silently.
        """
        await self.ws_manager.broadcast({
            "type": "MANUAL_ACTION_REQUIRED",
            "action": action,
            "details": details,
            "urgency": "high",
            "message": f"App bridge failed — manually {action} in Yahoo tab",
            "timestamp": datetime.utcnow().isoformat()
        })
        logger.error(
            "Bridge failure: action=%s details=%s", action, details
        )
```

### File: `backend/websocket/manager.py`

```python
class WebSocketManager:
    """
    Manages WebSocket connections between FastAPI and React clients.
    Push-based — never polls. Broadcasts draft events to all clients.
    """
    
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict) -> None:
        """Push event to all connected React clients."""
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active_connections.remove(ws)
```

### FastAPI WebSocket endpoint

Add to `backend/routers/draft.py`:

```python
@router.websocket("/ws/draft")
async def draft_websocket(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive — receive any client messages
            data = await websocket.receive_json()
            # Handle any client → server messages if needed
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
```

### Action endpoints (HTTP POST, not WebSocket)

```python
POST /draft/bid         body: {"amount": int}
POST /draft/nominate    body: {"yahoo_player_id": str, "opening_bid": int}
POST /draft/pass        body: {}
```

---

## Step 4 — WebSocket frame fixtures

Once user provides real Yahoo WS payloads, create:
`tests/fixtures/yahoo_ws_frames.json`

```json
{
  "nomination": {
    "raw_payload": "...paste real Yahoo frame here...",
    "expected_parsed": {
      "type": "nomination",
      "player_id": "...",
      "player_name": "...",
      "nominated_by": "...",
      "clock_seconds": 30
    }
  },
  "bid_update": {
    "raw_payload": "...",
    "expected_parsed": {
      "type": "bid_update",
      "current_bid": 45,
      "current_bidder": "..."
    }
  },
  "draft_pick": {
    "raw_payload": "...",
    "expected_parsed": {
      "type": "draft_pick",
      "player_id": "...",
      "team_id": "...",
      "final_price": 45
    }
  },
  "clock_warning": {
    "raw_payload": "...",
    "expected_parsed": {
      "type": "clock_warning",
      "seconds_remaining": 5
    }
  }
}
```

---

## Required test cases

```python
# tests/unit/integrations/test_yahoo_playwright.py

def test_nomination_event_parsed_from_ws_frame(yahoo_ws_frames):
    """Uses fixture — no real browser."""
    result = bridge._parse_yahoo_frame(
        yahoo_ws_frames["nomination"]["raw_payload"]
    )
    assert result["type"] == "nomination"
    assert "player_id" in result
    assert "clock_seconds" in result

def test_bid_update_event_parsed(yahoo_ws_frames):
    result = bridge._parse_yahoo_frame(
        yahoo_ws_frames["bid_update"]["raw_payload"]
    )
    assert result["type"] == "bid_update"
    assert isinstance(result["current_bid"], int)

def test_draft_pick_confirmed_event_parsed(yahoo_ws_frames):
    result = bridge._parse_yahoo_frame(
        yahoo_ws_frames["draft_pick"]["raw_payload"]
    )
    assert result["type"] == "draft_pick"
    assert "final_price" in result

def test_clock_warning_event_parsed(yahoo_ws_frames):
    result = bridge._parse_yahoo_frame(
        yahoo_ws_frames["clock_warning"]["raw_payload"]
    )
    assert result["type"] == "clock_warning"

def test_unknown_frame_returns_none():
    """Non-draft frames should return None, not crash."""
    result = bridge._parse_yahoo_frame('{"type": "heartbeat"}')
    assert result is None

def test_malformed_frame_returns_none():
    """Bad JSON should return None, not raise."""
    result = bridge._parse_yahoo_frame("not json {{{{")
    assert result is None

def test_bridge_failure_emits_manual_action_alert(mock_ws_manager):
    """on_bridge_failure must broadcast MANUAL_ACTION_REQUIRED immediately."""
    asyncio.run(bridge.on_bridge_failure(action="bid", details="$45"))
    call_args = mock_ws_manager.broadcast.call_args[0][0]
    assert call_args["type"] == "MANUAL_ACTION_REQUIRED"
    assert call_args["action"] == "bid"
    assert call_args["urgency"] == "high"

def test_health_check_triggers_reconnect_on_failure(mock_bridge):
    """Simulated ping failure → reconnect attempted."""
    mock_bridge._ping_draft_room.return_value = False
    # Verify _reconnect() is called

def test_no_polling_in_event_chain():
    """
    Inspect source code for asyncio.sleep() inside event handlers.
    Only acceptable location: health_check_loop() with comment.
    """
    import ast
    import inspect
    source = inspect.getsource(YahooPlaywrightBridge)
    tree = ast.parse(source)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            if node.name == "health_check_loop":
                continue  # Allowed here only
            for child in ast.walk(node):
                if (isinstance(child, ast.Await) and
                    isinstance(child.value, ast.Call)):
                    func = child.value.func
                    if (hasattr(func, 'attr') and 
                        func.attr == 'sleep'):
                        pytest.fail(
                            f"asyncio.sleep() found in {node.name}() "
                            f"— polling not allowed in event handlers"
                        )

def test_nomination_fires_playwright_action(mock_page):
    """place_bid triggers page interaction — no real Yahoo needed."""
    asyncio.run(bridge.place_bid(45))
    assert mock_page.evaluate.called or mock_page.click.called

def test_bid_fires_playwright_action(mock_page):
    asyncio.run(bridge.nominate_player("12345", 1))
    assert mock_page.evaluate.called or mock_page.click.called

def test_broadcast_sent_after_parsed_event(mock_ws_manager, yahoo_ws_frames):
    """Parsed nomination → ws_manager.broadcast() called with correct data."""
    asyncio.run(bridge._dispatch_event({
        "type": "nomination",
        "player_id": "123"
    }))
    assert mock_ws_manager.broadcast.called
```

---

## Mock draft testing (mandatory before marking complete)

**ASK USER** to set up a Yahoo practice draft or use last year's draft room.

Run the bridge against a real draft room and verify:
- [ ] Nomination events detected in under 100ms from Yahoo pushing the frame
- [ ] Bid placement fires correctly and Yahoo reflects the bid
- [ ] Bridge failure alert appears prominently in the React UI
- [ ] Health check fires every 10 seconds (check logs)
- [ ] Auto-reconnect works when connection is manually dropped
- [ ] `test_no_polling_in_event_chain` passes

---

## Verification before marking complete
1. **ASK USER** provided draft room URL and WS frame payloads
2. All 9 named unit tests pass
3. `test_no_polling_in_event_chain` passes (this is non-negotiable)
4. Mock draft tested with real Yahoo connection
5. Bridge failure alert tested and confirmed unmissable in UI
6. Coverage 80%+ on `yahoo_playwright.py` and `websocket/manager.py`

---

## Commit
```
feat(yahoo-playwright): implement Playwright draft room bridge

WebSocket interception primary, MutationObserver fallback.
Zero polling verified by code inspection test.
Bridge failure alert implemented — never crashes silently.
Mock draft tested successfully.
Coverage: X%.
```
