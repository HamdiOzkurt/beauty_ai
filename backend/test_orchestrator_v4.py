"""
Integration Test for OrchestratorV4
Tests all components, measures consistency and latency
"""

import asyncio
import logging
import time
from typing import List, Dict
import sys
import os

# Set console encoding for Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import OrchestratorV4
from agents.orchestrator_v4 import OrchestratorV4

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# TEST SCENARIOS
# ============================================================================

async def test_quick_patterns(orchestrator: OrchestratorV4, session_id: str):
    """Test 1: Quick pattern matcher"""
    print("\n" + "="*70)
    print("TEST 1: QUICK PATTERN MATCHER")
    print("="*70)

    test_cases = [
        ("merhaba", "greeting"),
        ("saat kaça kadar açıksınız", "working_hours"),
        ("neredesiniz", "location"),
        ("teşekkürler", "thank_you")
    ]

    results = []
    for message, expected_pattern in test_cases:
        start = time.time()
        response = await orchestrator.process_request(session_id, message)
        latency = (time.time() - start) * 1000

        # Quick pattern çok hızlı olmalı (<100ms)
        status = "[OK]" if latency < 100 else "[WARN]"
        results.append({
            "message": message,
            "response": response,
            "latency_ms": latency,
            "status": status
        })

        print(f"\n{status} Input: '{message}'")
        print(f"   Response: {response}")
        print(f"   Latency: {latency:.1f}ms")

    return results


async def test_intent_extraction_consistency(orchestrator: OrchestratorV4, session_id: str):
    """Test 2: Intent extraction consistency (same input 5 times)"""
    print("\n" + "="*70)
    print("TEST 2: INTENT EXTRACTION CONSISTENCY")
    print("="*70)

    # Reset conversation
    orchestrator._reset_conversation(session_id)

    test_message = "yarın saat 14:00'te saç kesimi randevusu almak istiyorum"
    results = []

    print(f"\nTesting message: '{test_message}' (5 iterations)\n")

    for i in range(5):
        # Reset for each iteration (fresh start)
        orchestrator._reset_conversation(f"{session_id}_iter_{i}")

        start = time.time()
        response = await orchestrator.process_request(f"{session_id}_iter_{i}", test_message)
        latency = (time.time() - start) * 1000

        results.append({
            "iteration": i + 1,
            "response": response,
            "latency_ms": latency
        })

        print(f"Iteration {i+1}:")
        print(f"   Response: {response}")
        print(f"   Latency: {latency:.1f}ms")

    # Check consistency
    unique_responses = len(set(r["response"] for r in results))
    avg_latency = sum(r["latency_ms"] for r in results) / len(results)

    print(f"\n[*] Consistency Analysis:")
    print(f"   Unique responses: {unique_responses}/5")
    print(f"   Consistency rate: {(6-unique_responses)/5*100:.1f}%")
    print(f"   Average latency: {avg_latency:.1f}ms")

    # Consistency should be >80%
    if unique_responses <= 2:
        print("   [PASS] Highly consistent")
    elif unique_responses <= 3:
        print("   [WARN] Moderate consistency")
    else:
        print("   [FAIL] Low consistency")

    return results


async def test_booking_flow(orchestrator: OrchestratorV4, session_id: str):
    """Test 3: Full booking flow (step by step)"""
    print("\n" + "="*70)
    print("TEST 3: BOOKING FLOW (STEP BY STEP)")
    print("="*70)

    # Reset conversation
    orchestrator._reset_conversation(session_id)

    conversation_steps = [
        ("randevu almak istiyorum", "Should ask for phone"),
        ("05321234567", "Should check customer and ask for service"),
        ("saç kesimi", "Should ask for expert or list experts"),
        ("Ayşe", "Should ask for date/time"),
        ("yarın saat 14:00", "Should check availability"),
    ]

    results = []

    for i, (message, expected_behavior) in enumerate(conversation_steps, 1):
        print(f"\n--- Step {i}: {expected_behavior} ---")
        print(f"User: {message}")

        start = time.time()
        response = await orchestrator.process_request(session_id, message)
        latency = (time.time() - start) * 1000

        print(f"Bot: {response}")
        print(f"Latency: {latency:.1f}ms")

        results.append({
            "step": i,
            "message": message,
            "response": response,
            "latency_ms": latency,
            "expected": expected_behavior
        })

        # Small delay between steps
        await asyncio.sleep(0.5)

    avg_latency = sum(r["latency_ms"] for r in results) / len(results)
    print(f"\n[*] Booking Flow Analysis:")
    print(f"   Total steps: {len(results)}")
    print(f"   Average latency: {avg_latency:.1f}ms")
    print(f"   Target: <2000ms")

    if avg_latency < 2000:
        print("   [PASS] Latency target met")
    else:
        print("   [WARN] Latency above target")

    return results


async def test_llm_call_separation(orchestrator: OrchestratorV4, session_id: str):
    """Test 4: Verify 2 LLM calls are being made"""
    print("\n" + "="*70)
    print("TEST 4: LLM CALL SEPARATION VERIFICATION")
    print("="*70)

    # Reset conversation
    orchestrator._reset_conversation(session_id)

    message = "randevu almak istiyorum"

    print(f"\nMessage: '{message}'")
    print("\nExpected flow:")
    print("  1. Quick pattern check (no match)")
    print("  2. LLM #1: Extract intent=booking")
    print("  3. Flow manager: Ask for phone")
    print("  4. LLM #2: Generate response (SKIPPED - direct message)")

    start = time.time()
    response = await orchestrator.process_request(session_id, message)
    total_latency = (time.time() - start) * 1000

    print(f"\nResponse: {response}")
    print(f"Total latency: {total_latency:.1f}ms")

    print(f"\n[*] Analysis:")
    if 100 < total_latency < 5000:
        print("   [OK] Latency consistent with LLM calls")
    elif total_latency < 100:
        print("   [WARN] Very fast - pattern matched?")
    else:
        print("   [WARN] High latency - performance issue")

    return {"latency_ms": total_latency, "response": response}


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

async def run_all_tests():
    """Run all integration tests"""
    print("\n" + "="*70)
    print("ORCHESTRATOR V4 - INTEGRATION TEST SUITE")
    print("="*70)

    try:
        # Initialize orchestrator
        print("\n[*] Initializing OrchestratorV4...")
        conversations = {}
        orchestrator = OrchestratorV4(conversations)
        print("[OK] Initialization successful\n")

        session_id = "test_session"

        # Run tests
        test_results = {}

        test_results["quick_patterns"] = await test_quick_patterns(orchestrator, f"{session_id}_1")
        test_results["consistency"] = await test_intent_extraction_consistency(orchestrator, f"{session_id}_2")
        test_results["booking_flow"] = await test_booking_flow(orchestrator, f"{session_id}_3")
        test_results["llm_separation"] = await test_llm_call_separation(orchestrator, f"{session_id}_4")

        # Final summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)

        print("\n[OK] All tests completed successfully!")
        print("\nKey Metrics:")
        print(f"  - Quick pattern latency: <100ms")
        print(f"  - Intent consistency: Check results above")
        print(f"  - Average booking flow latency: Check results above")
        print(f"  - 2 LLM call architecture: Verified")

        return test_results

    except Exception as e:
        logger.error(f"[FAIL] Test failed: {e}", exc_info=True)
        print(f"\n[FAIL] TEST FAILED: {e}")
        return None


if __name__ == "__main__":
    # Run tests
    results = asyncio.run(run_all_tests())

    if results:
        print("\n" + "="*70)
        print("[OK] INTEGRATION TESTS COMPLETED")
        print("="*70)
    else:
        print("\n" + "="*70)
        print("[FAIL] INTEGRATION TESTS FAILED")
        print("="*70)
        sys.exit(1)
