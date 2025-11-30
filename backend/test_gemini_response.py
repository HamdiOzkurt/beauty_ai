import asyncio
import sys
sys.path.insert(0, ".")

from agents.orchestrator_v4 import OrchestratorV4

async def test():
    orch = OrchestratorV4({})
    response = await orch.process_request("test_session", "yarın saat 14:00 randevu istiyorum")
    print(f"\nFinal Response: {response}")

if __name__ == "__main__":
    asyncio.run(test())
