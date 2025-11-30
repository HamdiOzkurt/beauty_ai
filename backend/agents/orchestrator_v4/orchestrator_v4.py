"""
Orchestrator V4 - Main Integration
2 LLM Call Strategy with Separation of Concerns

Architecture:
1. Quick Pattern Matcher (deterministic)
2. LLM Call #1: Intent & Entity Router (temp=0.0)
3. Flow Manager (deterministic)
4. Tool Executor (via agents)
5. LLM Call #2: Response Generator (temp=0.7)
"""

import google.generativeai as genai
import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import asyncio

# Local imports
from .quick_pattern_matcher import QuickPatternMatcher
from .intent_entity_router import IntentEntityRouter, IntentType
from .flow_manager import FlowManager
from .response_generator import ResponseGenerator
from .flows import StateMarker, TOOL_MAPPING

# Parent imports (mevcut system)
from agents.appointment_agent import AppointmentAgent
from agents.customer_agent import CustomerAgent
from agents.marketing_agent import MarketingAgent
from config import settings
from repository import ServiceRepository


class OrchestratorV4:
    """
    Orchestrator V4 - Enterprise-grade conversation orchestration

    Improvements over V3:
    - 2 focused LLM calls instead of 1 giant call
    - Deterministic routing (no LLM for simple decisions)
    - Better state management with explicit markers
    - Improved consistency (>95% target)
    - Faster response time (<2s target)
    """

    def __init__(self, conversations: Dict[str, Dict]):
        """
        Initialize orchestrator with all components.

        Args:
            conversations: Shared conversation dict (from main app)
        """
        self.logger = logging.getLogger(__name__)
        self.conversations = conversations

        # Initialize agents (mevcut system)
        self.agents = {
            "appointment_agent": AppointmentAgent(),
            "customer_agent": CustomerAgent(),
            "marketing_agent": MarketingAgent(),
        }

        # Initialize Gemini models
        genai.configure(api_key=settings.GEMINI_API_KEY)

        # LLM #1: Intent & Entity Router (temperature=0.0)
        # NOT: response_mime_type JSON yerine function calling kullanacağız
        self.llm1_model = genai.GenerativeModel(
            settings.AGENT_MODEL,
            generation_config={
                "temperature": 0.0,  # Deterministik
                "top_p": 0.95,
                "top_k": 20,
                "max_output_tokens": 300
            }
        )

        # LLM #2: Response Generator (temperature=0.7)
        self.llm2_model = genai.GenerativeModel(
            settings.AGENT_MODEL,
            generation_config={
                "temperature": 0.7,  # Doğal
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 200
            }
        )

        # Load knowledge base (services, experts)
        self._load_knowledge_base()

        # Initialize components
        self.pattern_matcher = QuickPatternMatcher()
        self.intent_router = IntentEntityRouter(
            gemini_model=self.llm1_model,
            knowledge_base_summary=self.knowledge_base_summary
        )
        self.flow_manager = FlowManager()
        self.response_generator = ResponseGenerator(gemini_model=self.llm2_model)

        self.logger.info("✅ OrchestratorV4 initialized")

    def _load_knowledge_base(self):
        """
        CMS'den hizmet ve uzman bilgilerini yükle (cache)

        Mevcut system ile aynı, ama format biraz farklı
        """
        try:
            service_repo = ServiceRepository()
            services = service_repo.list_all()
            service_names = [service.name for service in services if hasattr(service, 'name')]

            if service_names:
                hizmetler_str = ", ".join(service_names)
            else:
                hizmetler_str = "şu anda tanımlı bir hizmetimiz bulunmuyor"

            # TODO: Expert listesini de ekle (mcp_server'daki get_all_experts_from_cms'i kullan)
            # Şimdilik sadece hizmetler

            self.knowledge_base_summary = (
                f"Biz Güzellik Merkeziyiz. 09:00-19:00 arası açığız. "
                f"Sunduğumuz hizmetler: {hizmetler_str}. "
                f"Adresimiz: İstanbul, Şişli."
            )

            self.logger.info(f"📚 Knowledge base loaded: {len(service_names)} services")

        except Exception as e:
            self.logger.error(f"Knowledge base loading error: {e}", exc_info=True)
            self.knowledge_base_summary = (
                "Biz Güzellik Merkeziyiz. 09:00-19:00 arası açığız. "
                "Adresimiz: İstanbul, Şişli."
            )

    async def process_request(
        self,
        session_id: str,
        user_message: str,
        websocket=None
    ) -> str:
        """
        Ana işlem akışı - V4
        Flow:
        1. Get/create conversation
        2. Quick pattern check
        3. LLM #1: Intent & Entity extraction
        4. Flow Manager: Next action decision
        5. Tool execution (if needed)
        6. LLM #2: Response generation
        7. Send response
        """
        self.logger.info(f"\n{'='*60}\n🎯 REQUEST: {user_message}\n{'='*60}")

        # STEP 0: Get or create conversation
        conv = self.conversations.get(session_id)
        if not conv:
            conv = {"context": {}, "collected": {}, "history": []}
            self.conversations[session_id] = conv

        # User mesajını history'e ekle
        conv["history"].append({"role": "user", "content": user_message})

        try:
            # STEP 1: Quick Pattern Check (deterministic)
            quick_response = self.pattern_matcher.check(
                user_message,
                conversation_history=conv.get("history")
            )

            if quick_response:
                self.logger.info(f"⚡ Quick pattern matched - skipping LLM")
                await self._send_response(quick_response, conv, websocket, session_id)
                return quick_response

            # STEP 2: LLM Call #1 - Intent & Entity Extraction
            route_result = await self.intent_router.route(
                user_message=user_message,
                collected_state=conv.get("collected", {}),
                conversation_history=conv.get("history", []),
                context=conv.get("context", {})
            )

            intent = route_result.intent.value
            entities = route_result.entities.model_dump(exclude_none=True)

            # Handle the new 'confirmed' entity from stateful pre-routing
            if "confirmed" in entities:
                conv["context"][StateMarker.CONFIRMED] = entities["confirmed"]
                conv["context"]["confirmation_pending"] = False  # Reset the flag
                # Don't add 'confirmed' to the collected entities
                del entities["confirmed"]

            # Entities'leri collected'a merge et
            for key, value in entities.items():
                if value:
                    if key in ["date", "time", "expert_name"]:
                        old_value = conv["collected"].get(key)
                        if old_value and old_value != value:
                            self.logger.info(f"♻️ {key} changed: {old_value} → {value}")
                            self.flow_manager.reset_availability_check(conv["context"])
                    conv["collected"][key] = value

            # STEP 3: Flow Manager - Next Action Decision
            next_action = self.flow_manager.get_next_action(
                intent=intent,
                collected=conv["collected"],
                context=conv["context"]
            )
            action_type = next_action["action"]

            # STEP 4: Tool Execution (if needed)
            tool_result = None
            DATA_QUERYING_TOOLS = [
                "list_experts", "check_availability", "get_customer_appointments",
                "check_campaigns", "suggest_alternative_times", "list_services"
            ]

            if action_type == "tool_call":
                tool_name = next_action["tool"]
                tool_params = next_action["tool_params"]

                tool_result = await self._execute_tool(
                    tool_name=tool_name,
                    tool_params=tool_params,
                    conv=conv
                )

                self._update_context_from_tool(tool_name, tool_result, conv)

                if tool_name not in DATA_QUERYING_TOOLS:
                    next_action = self.flow_manager.get_next_action(
                        intent=intent,
                        collected=conv["collected"],
                        context=conv["context"]
                    )
            
            # STEP 5: Handle "ask_alternative" special case
            if action_type == "ask_alternative":
                response = next_action.get("message", "Alternatif saatler önerelim mi?")
                conv["context"]["waiting_for_alternative_approval"] = True
                await self._send_response(response, conv, websocket, session_id)
                return response
            
            if "evet" in user_message.lower() and conv["context"].get("waiting_for_alternative_approval"):
                tool_result = await self._execute_tool(
                    tool_name="suggest_alternative_times",
                    tool_params={
                        "service_type": conv["collected"].get("service"),
                        "date": conv["collected"].get("date"),
                        "expert_name": conv["collected"].get("expert_name")
                    },
                    conv=conv
                )
                conv["context"]["waiting_for_alternative_approval"] = False
                conv["context"][StateMarker.ALTERNATIVES_SHOWN] = True
                next_action = {"action": "tool_call", "tool": "suggest_alternative_times"}

            # STEP 6: LLM Call #2 - Response Generation
            final_response = await self.response_generator.generate(
                action=next_action,
                tool_result=tool_result,
                context=conv["context"]
            )

            # STEP 7: Send Response
            await self._send_response(final_response, conv, websocket, session_id)
            return final_response

        except Exception as e:
            self.logger.error(f"❌ Process request error: {e}", exc_info=True)
            error_response = "Üzgünüm, bir hata oluştu. Lütfen tekrar dener misiniz?"
            await self._send_response(error_response, conv, websocket, session_id)
            return error_response

    async def _execute_tool(
        self,
        tool_name: str,
        tool_params: Dict[str, Any],
        conv: Dict
    ) -> Dict[str, Any]:
        """
        Tool'u ilgili agent üzerinden çalıştır.

        Args:
            tool_name: Tool adı (check_customer, create_appointment, vb.)
            tool_params: Tool parametreleri
            conv: Conversation state

        Returns:
            Tool result dict
        """
        # Agent mapping
        agent_key = TOOL_MAPPING.get(tool_name)

        if not agent_key:
            self.logger.error(f"❌ Unknown tool: {tool_name}")
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        agent = self.agents.get(agent_key)

        if not agent:
            self.logger.error(f"❌ Agent not found: {agent_key}")
            return {"success": False, "error": f"Agent not found: {agent_key}"}

        try:
            self.logger.info(f"🔧 Executing tool: {agent_key}.{tool_name}")
            self.logger.debug(f"   Params: {tool_params}")

            # Agent execute
            task_payload = {
                "task": tool_name,
                "parameters": tool_params
            }

            result = await agent.execute(task_payload, conv)

            self.logger.info(f"✅ Tool result: success={result.get('success')}")
            return result

        except Exception as e:
            self.logger.error(f"❌ Tool execution error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _update_context_from_tool(
        self,
        tool_name: str,
        tool_result: Dict[str, Any],
        conv: Dict
    ):
        """
        Tool sonucuna göre context ve state marker'ları güncelle.

        Args:
            tool_name: Tool adı
            tool_result: Tool sonucu
            conv: Conversation state (mutate edilir)
        """
        context = conv.setdefault("context", {})
        collected = conv.setdefault("collected", {})

        if not tool_result.get("success"):
            self.logger.warning(f"⚠️ Tool failed: {tool_name} with error: {tool_result.get('error')}")
            # Handle special case: check_customer fails because customer is not found
            if tool_name == "check_customer" and ("bulunamadı" in tool_result.get("error", "").lower() or "not found" in tool_result.get("error", "").lower()):
                self.logger.info("ℹ️ Customer not found via tool. Treating as a new customer.")
                context["is_new_customer"] = True
                context[StateMarker.CUSTOMER_CHECKED] = True
                return  # This is a valid, handled outcome
            
            # Handle special case: get_customer_appointments fails because none are found
            if tool_name == "get_customer_appointments" and ("bulunamadı" in tool_result.get("error", "").lower() or "not found" in tool_result.get("error", "").lower()):
                self.logger.info("ℹ️ No appointments found for customer. Treating as success with empty list.")
                context[StateMarker.APPOINTMENTS_FETCHED] = True
                context["appointments"] = []
                return # This is a valid, handled outcome

            return

        # check_customer
        if tool_name == "check_customer":
            customer = tool_result.get("customer", {})
            if not customer: # Double check if customer object is empty
                self.logger.info("ℹ️ Customer not found (empty result). Treating as a new customer.")
                context["is_new_customer"] = True
            else:
                context["customer_name"] = customer.get("name")
                context["customer_id"] = customer.get("id")
                context["is_new_customer"] = False # Customer was found
                self.logger.info(f"📝 Customer found: {customer.get('name')}")
            
            context[StateMarker.CUSTOMER_CHECKED] = True

        # get_customer_appointments
        elif tool_name == "get_customer_appointments":
            appointments = tool_result.get("appointments", [])
            context[StateMarker.APPOINTMENTS_FETCHED] = True

            if appointments:
                # En son randevuyu kaydet (cancel için)
                latest = appointments[0]
                context["latest_appointment"] = latest
                context["appointment_code"] = latest.get("id")
                self.logger.info(f"📋 {len(appointments)} appointments fetched")
            else:
                self.logger.info("📋 No appointments found for customer (success case).")
                context["latest_appointment"] = None
                context["appointment_code"] = None
                context["appointments"] = []

        # check_availability
        elif tool_name == "check_availability":
            is_available = tool_result.get("available", False)
            context[StateMarker.AVAILABILITY_CHECKED] = True
            context[StateMarker.AVAILABLE] = is_available

            if not is_available:
                # Alternative soracağız
                context["waiting_for_alternative_approval"] = True

            self.logger.info(f"📅 Availability: {is_available}")

        # list_experts
        elif tool_name == "list_experts":
            experts = tool_result.get("experts", [])
            context[StateMarker.EXPERTS_LISTED] = True
            context["expert_list"] = [e.get("name") for e in experts]
            self.logger.info(f"👥 {len(experts)} experts listed")

        # suggest_alternative_times
        elif tool_name == "suggest_alternative_times":
            alternatives = tool_result.get("alternatives", [])
            context[StateMarker.ALTERNATIVES_SHOWN] = True
            context["alternative_times"] = alternatives
            self.logger.info(f"⏰ {len(alternatives)} alternatives suggested")

        # check_campaigns
        elif tool_name == "check_campaigns":
            campaigns = tool_result.get("campaigns", [])
            if campaigns:
                context["active_campaigns"] = campaigns
                self.logger.info(f"🎁 {len(campaigns)} campaigns found")

        # create_appointment
        elif tool_name == "create_appointment":
            appointment = tool_result.get("appointment", {})
            context["last_appointment_code"] = appointment.get("code")
            # Flow tamamlandı, collected'ı temizle
            self.logger.info(f"✅ Appointment created: {appointment.get('code')}")

        # cancel_appointment
        elif tool_name == "cancel_appointment":
            self.logger.info(f"✅ Appointment cancelled")

    async def _send_response(
        self,
        text: str,
        conv: Dict,
        websocket,
        session_id: str
    ):
        """
        Yanıtı kaydet ve WebSocket üzerinden gönder.

        Mevcut system ile uyumlu (değişiklik yok)
        """
        # Assistant yanıtını history'e ekle
        conv["history"].append({"role": "assistant", "content": text})

        # History sınırla (son 20 mesaj)
        if len(conv["history"]) > 20:
            conv["history"] = conv["history"][-20:]

        # Session'ı kaydet
        if session_id:
            self.conversations[session_id] = conv

        # WebSocket gönderimi
        if websocket:
            try:
                await websocket.send_text(text)
                await websocket.send_text(json.dumps({"type": "stream_end"}))
                self.logger.info(f"📤 Response sent: {text[:50]}...")
            except Exception as e:
                self.logger.error(f"WebSocket send error: {e}")

    def _reset_conversation(self, session_id: str):
        """Oturumu sıfırla (opsiyonel)"""
        self.conversations[session_id] = {
            "context": {},
            "collected": {},
            "history": []
        }
        self.logger.info(f"♻️ Conversation reset: {session_id}")


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*60)
    print("ORCHESTRATOR V4 - INITIALIZATION TEST")
    print("="*60 + "\n")

    try:
        conversations = {}
        orchestrator = OrchestratorV4(conversations)
        print("✅ Orchestrator V4 initialized successfully")
        print(f"   Knowledge base: {orchestrator.knowledge_base_summary[:100]}...")
        print(f"   Agents: {list(orchestrator.agents.keys())}")
        print(f"   Components: Pattern Matcher, Intent Router, Flow Manager, Response Generator")
    except Exception as e:
        print(f"❌ Initialization failed: {e}")

    print("\n" + "="*60)
