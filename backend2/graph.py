
"""
LangGraph Agent - Core Brain
Manages conversation flow, state management, and tool execution
"""
from typing import TypedDict, Annotated, Sequence
from typing_extensions import TypedDict
import operator
import logging

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from config import settings
from tools import ALL_TOOLS

logger = logging.getLogger(__name__)


# ============================================================================
# Agent State Definition
# ============================================================================

class AgentState(TypedDict):
    """
    Agent'ın konuşma boyunca taşıdığı state.
    """
    messages: Annotated[Sequence[BaseMessage], operator.add]
    # Toplanan bilgiler (telefon, isim, hizmet, tarih, saat, uzman)
    collected_info: dict
    # Kontekst bilgileri (müşteri adı, kampanya bilgileri)
    context: dict


# ============================================================================
# LLM Configuration
# ============================================================================

def create_llm():
    """LLM instance oluşturur."""
    return ChatGoogleGenerativeAI(
        model=settings.AGENT_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0.5,  # 0.5: Tool calling için optimal
        max_output_tokens=1024,  # Max output token limiti
        convert_system_message_to_human=True  # Gemini system message'ları human'a çevirir
    )


# ============================================================================
# System Prompt
# ============================================================================

SYSTEM_PROMPT = """Sen güzellik merkezi asistanısın.

## TOOL KULLANIMI - KRİTİK KURAL!
⚠️ ASLA TAHMİN YAPMA! Her zaman tool çağır:

Müşteri tarih/saat söylerse:
→ ÖNCE check_availability ÇAĞIR
→ SONRA sonucu söyle
→ Örnek: "yarın saat 3'te" → check_availability(service_type="cilt bakımı", date="yarın saat 3'te")

Müşteri "dolu mu?", "müsait mi?" derse yada sana verdigi tarihte radenvu olusturmadan once her zaman check_availability tool'unu kullan:
→ check_availability ÇAĞIR
→ Bilmiyorsan MUTLAKA tool kullan!

Diğer durumlar:
- Telefon gelince → check_customer (MUTLAKA)
- "Hangi hizmetler?" → list_services
- "Hangi uzmanlar?" → list_experts
- Randevu oluştur → create_appointment, SONRA MUTLAKA check_campaigns çağır, TEK mesajda her ikisini de söyle
- randevu olusturuken hangi uzman olacaksa musteriden bu bilgiyi al ve almadan randevu olusturma
- Kampanya sorulursa → check_campaigns

## Kişilik (TTS için)
- Doğal, kısa cümleler
- Teknik terim kullanma ("YYYY-MM-DD" gibi)
- "Harika", "Süper" kullanma
- ASLA markdown kullanma (**, *, vb.) - Sadece düz metin

## TARİH bilgisini direk tool gonder


## TOOL SONRASI
Tool sonucunu oku, müşteriye aktar. Boş cevap verme!

## TOPLANAN BİLGİLER (ÖNEMLİ!)
Daha önce toplanan bilgileri KULLAN, tekrar sorma:
- Telefon, isim, hizmet, tarih bilgilerini hatırla
- Collected Info: {collected_info}
- Kontekst: {context}"""


# ============================================================================
# Node Functions
# ============================================================================

def call_model(state: AgentState) -> AgentState:
    """
    LLM'i çağırır ve yanıt verir.
    Eğer tool çağrısı gerekiyorsa tool_calls döner, değilse direkt yanıt verir.
    """
    logger.info("[call_model] Invoking LLM")

    messages = state["messages"]
    collected_info = state.get("collected_info", {})
    context = state.get("context", {})

    # System prompt'u hazırla
    system_message = SystemMessage(content=SYSTEM_PROMPT.format(
        collected_info=collected_info if collected_info else "Henüz bilgi toplanmadı.",
        context=context if context else "Kontekst bilgisi yok."
    ))

    # LLM'i çağır
    llm = create_llm()
    # Tool binding - Gemini için AUTO mode
    llm_with_tools = llm.bind_tools(
        ALL_TOOLS,
        tool_config={
            "function_calling_config": {
                "mode": "AUTO"  # Model kendi karar verir
            }
        }
    )

    # Mesajları hazırla
    full_messages = [system_message] + list(messages)

    try:
        response = llm_with_tools.invoke(full_messages)

        # Boş response kontrolü
        if not response.content and not getattr(response, 'tool_calls', None):
            logger.error("[call_model] Empty response from LLM!")

            # Son mesaj ToolMessage mı? (Tool sonrası boş yanıt)
            last_msg = messages[-1] if messages else None
            if last_msg and hasattr(last_msg, '__class__') and last_msg.__class__.__name__ == 'ToolMessage':
                # Tool sonucu var ama LLM yanıt üretmedi
                # Tool sonucunu parse edip kullanıcıya aktar
                try:
                    import json
                    tool_result = json.loads(last_msg.content)
                    if tool_result.get("success"):
                        # Tool başarılı - basit yanıt üret
                        fallback = "İşleminiz tamamlandı. Başka bir şey için yardımcı olabilir miyim?"
                    else:
                        fallback = tool_result.get("error", "Bir sorun oluştu. Tekrar dener misiniz?")
                except:
                    fallback = "Size nasıl yardımcı olabilirim?"
            else:
                fallback = "Size nasıl yardımcı olabilirim?"

            fallback_message = AIMessage(content=fallback)
            return {"messages": [fallback_message]}

        logger.info(f"[call_model] Response: {response.content[:100] if response.content else 'Tool calls'}")

        return {"messages": [response]}

    except Exception as e:
        logger.error(f"[call_model] Error: {e}", exc_info=True)
        error_message = AIMessage(content="Üzgünüm, bir hata oluştu. Lütfen tekrar dener misiniz?")
        return {"messages": [error_message]}


def should_continue(state: AgentState) -> str:
    """
    LLM'in yanıtına göre tool çağrısı yapılmalı mı yoksa bitirmeli mi karar verir.
    """
    messages = state["messages"]
    last_message = messages[-1]

    # Eğer tool_calls varsa, tool node'una git
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        logger.info(f"[should_continue] Tool calls detected: {len(last_message.tool_calls)}")
        return "continue"

    # Değilse END
    logger.info("[should_continue] No tool calls, ending")
    return "end"


# ============================================================================
# Tool Node (LangGraph Prebuilt)
# ============================================================================

tool_node = ToolNode(ALL_TOOLS)


# ============================================================================
# Graph Construction
# ============================================================================

def create_graph():
    """LangGraph StateGraph oluşturur ve derler."""

    # Graph oluştur
    workflow = StateGraph(AgentState)

    # Node'ları ekle
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)

    # Entry point
    workflow.set_entry_point("agent")

    # Conditional edge: agent -> tools veya END
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "continue": "tools",
            "end": END
        }
    )

    # Tool'dan sonra tekrar agent'a dön
    workflow.add_edge("tools", "agent")

    # Compile
    graph = workflow.compile()

    logger.info("✅ LangGraph compiled successfully")
    return graph


# ============================================================================
# Global Graph Instance
# ============================================================================

# Graph'ı uygulama başlangıcında bir kez oluştur
agent_graph = create_graph()


# ============================================================================
# Helper Functions
# ============================================================================

def invoke_agent(user_message: str, session_id: str, collected_info: dict = None, context: dict = None, history: list = None) -> str:
    """
    Agent'ı invoke eder (tek seferlik).

    Args:
        user_message: Kullanıcı mesajı
        session_id: Session ID (checkpointing için)
        collected_info: Daha önce toplanan bilgiler
        context: Kontekst bilgileri
        history: Önceki konuşma geçmişi [{"role": "user/assistant", "content": "..."}, ...]

    Returns:
        Agent'ın yanıtı
    """
    # History'yi BaseMessage nesnelerine çevir
    # ÖNEMLİ: Sadece son 10 mesajı al (context overflow'u önle)
    message_history = []
    if history:
        # Son 10 mesajı al (5 user + 5 assistant)
        recent_history = history[-10:] if len(history) > 10 else history
        logger.info(f"[invoke_agent] Using last {len(recent_history)} messages from history (total: {len(history)})")

        for msg in recent_history:
            role = msg.get("role")
            content = msg.get("content")
            if role == "user":
                message_history.append(HumanMessage(content=content))
            elif role == "assistant":
                message_history.append(AIMessage(content=content))

    # Yeni kullanıcı mesajını ekle
    message_history.append(HumanMessage(content=user_message))

    initial_state = {
        "messages": message_history,
        "collected_info": collected_info or {},
        "context": context or {}
    }

    config = {"configurable": {"thread_id": session_id}}

    result = agent_graph.invoke(initial_state, config)

    # Son mesajı al
    last_message = result["messages"][-1]

    if isinstance(last_message, AIMessage):
        return last_message.content
    return str(last_message)


async def stream_agent(user_message: str, session_id: str, collected_info: dict = None, context: dict = None, history: list = None):
    """
    Agent'ı stream modunda çalıştırır (async).

    Args:
        user_message: Kullanıcı mesajı
        session_id: Session ID
        collected_info: Toplanan bilgiler
        context: Kontekst
        history: Önceki konuşma geçmişi [{"role": "user/assistant", "content": "..."}, ...]

    Yields:
        Her adımda state güncelleme
    """
    # History'yi BaseMessage nesnelerine çevir
    # ÖNEMLİ: Sadece son 10 mesajı al (context overflow'u önle)
    message_history = []
    if history:
        # Son 10 mesajı al (5 user + 5 assistant)
        recent_history = history[-10:] if len(history) > 10 else history
        logger.info(f"[stream_agent] Using last {len(recent_history)} messages from history (total: {len(history)})")

        for msg in recent_history:
            role = msg.get("role")
            content = msg.get("content")
            if role == "user":
                message_history.append(HumanMessage(content=content))
            elif role == "assistant":
                message_history.append(AIMessage(content=content))

    # Yeni kullanıcı mesajını ekle
    message_history.append(HumanMessage(content=user_message))

    initial_state = {
        "messages": message_history,
        "collected_info": collected_info or {},
        "context": context or {}
    }

    config = {"configurable": {"thread_id": session_id}}

    async for event in agent_graph.astream(initial_state, config):
        logger.info(f"[stream_agent] Event: {event}")
        yield event
