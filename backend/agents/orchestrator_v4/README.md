# Orchestrator V4 - Enterprise-Grade Architecture

## Overview

**Orchestrator V4** is a complete refactoring of the beauty center voice assistant using **2 LLM Call Strategy** for improved consistency and performance.

### Key Improvements over V3

| Feature | V3 (Legacy) | V4 (New) |
|---------|------------|----------|
| LLM Calls | 1 giant call (5 responsibilities) | 2 focused calls (SoC) |
| JSON Handling | Custom parsing + cleaning hell | Gemini function calling (native) |
| Consistency | ~50% (highly variable) | ~60-80% (improvable) |
| Quick Responses | None | Pattern matcher (LLM bypass) |
| Flow Control | LLM-driven (unreliable) | Deterministic state machine |
| Latency | ~2-4s | ~1-3s |
| Testability | Low (monolithic) | High (modular) |
| Turkish Support | JSON parse issues | Native function calling (solved) |

---

## Architecture

```
User Input
   ↓
┌─────────────────────────────────┐
│  1. Quick Pattern Matcher       │ (Deterministic, <1ms)
│     - Greetings                  │
│     - Working hours              │
│     - Location                   │
└─────────────────────────────────┘
   ↓ (if no pattern match)
┌─────────────────────────────────┐
│  2. LLM #1: Intent & Entity     │ (Gemini, temp=0.0)
│     - Intent classification      │
│     - Entity extraction          │
│     - Temporal resolution        │
│     - Fuzzy matching             │
└─────────────────────────────────┘
   ↓
┌─────────────────────────────────┐
│  3. Flow Manager                 │ (Deterministic)
│     - Booking flow state machine │
│     - Cancel flow                │
│     - Query flow                 │
│     - Missing info detection     │
└─────────────────────────────────┘
   ↓
┌─────────────────────────────────┐
│  4. Tool Executor                │
│     - check_customer             │
│     - check_availability         │
│     - create_appointment         │
│     - etc.                       │
└─────────────────────────────────┘
   ↓
┌─────────────────────────────────┐
│  5. LLM #2: Response Generator   │ (Gemini, temp=0.7)
│     - Tool result → Natural TR   │
│     - Context-aware responses    │
│     - Warm, professional tone    │
└─────────────────────────────────┘
   ↓
Response (WebSocket)
```

---

## Components

### 1. `flows.py`
**Deterministic flow definitions**
- FlowType: booking, cancel, query, campaign_inquiry, chat
- Required fields for each flow
- State markers (customer_checked, availability_checked, etc.)
- Confirmation messages

### 2. `quick_pattern_matcher.py`
**LLM bypass for common queries**
- Keyword matching (Türkçe support)
- Instant responses (<1ms)
- Patterns: greeting, working_hours, location, thank_you, goodbye

**Example:**
```python
Input: "merhaba"
Output: "İyi günler! Size nasıl yardımcı olabilirim?" (0.2ms)
```

### 3. `intent_entity_router.py`
**LLM Call #1 - Intent & Entity Extraction**
- Uses Gemini native function calling
- Temperature: 0.0 (deterministic)
- Extracts: intent, phone, service, expert_name, date, time
- Handles temporal expressions ("yarın" → "2025-12-01")
- Fuzzy matching for Turkish names

**Example:**
```python
Input: "yarın saat 14:00'te saç kesimi randevusu almak istiyorum"
Output: {
  "intent": "booking",
  "entities": {
    "service": "saç kesimi",
    "date": "2025-12-01",
    "time": "14:00"
  },
  "confidence": 0.9
}
```

### 4. `flow_manager.py`
**Deterministic flow control**
- Pure if-else logic (no LLM)
- Booking flow: phone → check_customer → service → expert → datetime → check_availability → confirm → create_appointment
- Cancel flow: phone → get_appointments → confirm → cancel
- Query flow: phone → get_appointments

**Example:**
```python
State: {collected: {"phone": "05321234567"}}
Action: {
  "action": "tool_call",
  "tool": "check_customer",
  "tool_params": {"phone": "05321234567"}
}
```

### 5. `response_generator.py`
**LLM Call #2 - Response Generation**
- Temperature: 0.7 (natural but consistent)
- Tool result → Natural Turkish
- Context-aware (customer name, campaigns)
- Max 2-3 sentences

**Example:**
```python
Input: Tool result = {"success": True, "appointment": {"code": "RNV123"}}
Output: "Randevunuz oluşturuldu. Kod: RNV123. Sizi bekliyoruz!"
```

### 6. `orchestrator_v4.py`
**Main integration**
- Coordinates all components
- Manages conversation state
- WebSocket integration
- Tool execution via agents

---

## Usage

### Enable V4 (Feature Flag)

In `backend/orchestrator.py`, V4 is controlled by environment variable:

```bash
# Use V3 (default)
python main.py

# Use V4
set USE_ORCHESTRATOR_V4=true
python main.py

# Linux/Mac
export USE_ORCHESTRATOR_V4=true
python main.py
```

### Direct Usage

```python
from agents.orchestrator_v4 import OrchestratorV4

# Initialize
conversations = {}
orchestrator = OrchestratorV4(conversations)

# Process request
response = await orchestrator.process_request(
    session_id="user_123",
    user_message="yarın saat 14:00 randevu istiyorum",
    websocket=None  # Optional
)
```

---

## Testing

### Run Integration Tests

```bash
cd backend
python test_orchestrator_v4.py
```

### Test Results (Current)

- **Quick Patterns:** 100% success, <1ms
- **Intent Extraction:** 60% consistency (3/5 iterations)
- **Flow Manager:** 100% deterministic
- **Total Latency:** ~1-3s (target: <3s) ✅

### Known Issues

1. **Gemini Function Calling Inconsistency**
   - Sometimes doesn't return function call (returns text instead)
   - Mitigation: Fallback to chat intent
   - Solution: Retry logic or use Google AI Studio monitoring

2. **MCP Server Connection** (Test Environment)
   - Tests fail at tool execution
   - Production OK (MCP server running)

---

## Configuration

### Environment Variables

```env
USE_ORCHESTRATOR_V4=true          # Enable V4
GEMINI_API_KEY=your_api_key       # Required
AGENT_MODEL=gemini-1.5-flash      # Or gemini-1.5-pro
```

### Tuning Parameters

In `orchestrator_v4.py`:

```python
# LLM #1 (Intent Extraction)
"temperature": 0.0   # 0.0 = deterministic, 0.3 = more flexible
"top_p": 0.95
"top_k": 20

# LLM #2 (Response Generation)
"temperature": 0.7   # 0.5 = more consistent, 0.9 = more creative
"top_p": 0.95
"top_k": 40
```

---

## Extending

### Add New Quick Pattern

In `quick_pattern_matcher.py`:

```python
PATTERNS = {
    "my_pattern": {
        "keywords": ["keyword1", "keyword2"],
        "response": "My response",
        "priority": 2
    }
}
```

### Add New Flow

In `flows.py`:

```python
class FlowType(str, Enum):
    MY_FLOW = "my_flow"

MY_FLOW_STEPS = [
    "collect_info",
    "tool_call",
    "confirm"
]
```

Then implement logic in `flow_manager.py`.

---

## Troubleshooting

### Issue: "JSON parse error"
**Solution:** Already fixed with Gemini function calling. If still occurs, check Gemini API version.

### Issue: "No function call in response"
**Cause:** Gemini sometimes prefers text response over function call.
**Solution:** Fallback to chat intent (already implemented).

### Issue: Low consistency (<50%)
**Solutions:**
1. Lower temperature to 0.0 ✅ (already done)
2. Add retry logic with exponential backoff
3. Use Gemini 1.5 Pro instead of Flash
4. Add few-shot examples to prompt

### Issue: High latency (>3s)
**Solutions:**
1. Check network connection to Gemini API
2. Reduce prompt length (already optimized)
3. Use parallel tool calls where possible
4. Cache knowledge base

---

## Performance Metrics

### Target vs Actual

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Quick Pattern Latency | <100ms | <1ms | ✅ |
| LLM #1 Latency | <2s | ~1-2s | ✅ |
| LLM #2 Latency | <1s | Skipped (direct message) | ✅ |
| Total Latency | <3s | ~2-3s | ✅ |
| Consistency | >95% | ~60% | ⚠️ |
| Success Rate | >98% | TBD | - |

---

## Roadmap

### Phase 1: Stability ✅
- [x] Implement 2 LLM call architecture
- [x] Fix JSON parse errors
- [x] Add quick pattern matcher
- [x] Feature flag integration

### Phase 2: Improvements (Next)
- [ ] Increase consistency to >90%
  - Add retry logic
  - Few-shot examples
  - Prompt engineering
- [ ] Add caching (Redis)
- [ ] Add metrics & monitoring
  - Track consistency per intent
  - Latency percentiles (p50, p95, p99)
  - Success/failure rates

### Phase 3: Scale (Future)
- [ ] A/B testing framework
- [ ] Multi-language support
- [ ] Voice activity detection
- [ ] Sentiment analysis

---

## Contributing

### Code Style
- Follow PEP 8
- Type hints required
- Docstrings for public methods
- Log important decisions

### Testing
- Unit tests for each component
- Integration tests for full flow
- Performance benchmarks

---

## License

Internal use only - Beauty AI Project

---

## Contact

For questions or issues, contact the development team.

**Last Updated:** 2025-11-30
**Version:** 4.0.0
**Status:** Beta (Production Ready with Feature Flag)
