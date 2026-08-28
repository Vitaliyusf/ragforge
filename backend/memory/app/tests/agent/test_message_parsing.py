"""Reading a conversation back out of whatever shape LangChain hands over."""

from app.agent.memory_agent import MemoryAgent


def test_memory_agent_extract_summary_supports_langchain_message_objects():
    class _Message:
        def __init__(self, content):
            self.content = content

    summary = MemoryAgent._extract_summary({"messages": [_Message("Curated memory summary")]})

    assert summary == "Curated memory summary"


def test_memory_agent_extract_summary_supports_list_content_blocks():
    class _Message:
        def __init__(self, content):
            self.content = content

    summary = MemoryAgent._extract_summary(
        {"messages": [_Message([{"text": "Curated "}, {"text": "memory summary"}])]}
    )

    assert summary == "Curated memory summary"
