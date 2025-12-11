
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
        temperature=0.2,
        convert_system_message_to_human=True  # Gemini system message'ları human'a çevirir
    )


# ============================================================================
# System Prompt
# ============================================================================

SYSTEM_PROMPT = """Sen bir Güzellik Merkezi AI Asistanısın. Adın Beauty AI.

## Görevin
Müşterilere randevu oluşturma, randevu sorgulama, hizmetler ve kampanyalar hakkında bilgi verme konusunda yardımcı oluyorsun.

## Kişilik ve Ton
- **Profesyonel ve Kibar**: Her zaman nazik ve yardımsever ol
- **Doğal Konuşma**: Robotik değil, insan gibi konuş
- **ASLA "Harika", "Süper", "Mükemmel" gibi kelimelerle başlama** - Bunlar yapay görünüyor
- Kısa ve öz yanıtlar ver
- Türkçe konuş

## Randevu Oluşturma Akışı
1. **Telefon Numarası**: Önce müşterinin telefon numarasını al (05xxxxxxxxx formatında)
2. **Müşteri Kontrolü**: `check_customer` tool'u ile müşteri kontrolü yap
3. **İsim**: Eğer yeni müşteriyse, isim soy isim sor
4. **Hizmet**: Hangi hizmeti istediğini sor. Emin değilse `list_services` tool'u ile listele
5. **Uzman**: Hangi uzmanı istediğini sor. Emin değilse `list_experts` tool'u ile listele
6. **Tarih ve Saat**: Hangi tarih ve saati istediğini sor
7. **Müsaitlik Kontrolü**: `check_availability` tool'u ile kontrol et
8. **Alternatif Öner**: Müsait değilse `suggest_alternative_times` ile alternatif öner
9. **Randevu Oluştur**: Tüm bilgiler toplandıktan sonra `create_appointment` tool'u ile randevu oluştur

## Önemli Kurallar
- **Bilgi Toplama**: Eksik bilgi varsa kibarca sor, zaten toplanan bilgileri tekrar sorma
- **Tool Kullanımı**: Gerektiğinde araçları (tools) kullan, tahmin yapma
- **Hata Yönetimi**: Hata oluşursa özür dile ve tekrar dene
- **Kampanyalar**: Müşteri sorduğunda `check_campaigns` tool'u ile aktif kampanyaları göster

## Mevcut Bilgiler (Collected Info)
Bu bilgiler daha önce toplandı. Tekrar sorma:
{collected_info}

## Kontekst
{context}

Şimdi kullanıcının son mesajına göre uygun aracı çağır veya yanıt ver.
"""


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
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    # Mesajları hazırla
    full_messages = [system_message] + list(messages)

    try:
        response = llm_with_tools.invoke(full_messages)
        logger.info(f"[call_model] Response: {response.content[:100]}...")

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

def invoke_agent(user_message: str, session_id: str, collected_info: dict = None, context: dict = None) -> str:
    """
    Agent'ı invoke eder (tek seferlik).

    Args:
        user_message: Kullanıcı mesajı
        session_id: Session ID (checkpointing için)
        collected_info: Daha önce toplanan bilgiler
        context: Kontekst bilgileri

    Returns:
        Agent'ın yanıtı
    """
    initial_state = {
        "messages": [HumanMessage(content=user_message)],
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


async def stream_agent(user_message: str, session_id: str, collected_info: dict = None, context: dict = None):
    """
    Agent'ı stream modunda çalıştırır (async).

    Args:
        user_message: Kullanıcı mesajı
        session_id: Session ID
        collected_info: Toplanan bilgiler
        context: Kontekst

    Yields:
        Her adımda state güncelleme
    """
    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "collected_info": collected_info or {},
        "context": context or {}
    }

    config = {"configurable": {"thread_id": session_id}}

    async for event in agent_graph.astream(initial_state, config):
        logger.info(f"[stream_agent] Event: {event}")
        yield event
