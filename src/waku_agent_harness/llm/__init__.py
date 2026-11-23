"""LLM integration for the agent harness."""

import os
from functools import cache

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageFunctionToolCall
from openai.types.chat.chat_completion_message_function_tool_call import Function

SYSTEM_PROMPT = """You are a coding agent. Answer clearly and concisely.
Use read_file to inspect text files and bash when you need shell commands. Report your findings to the user.
Before each tool call, briefly say what you are about to do and why, so the user can follow your steps.
If a command is denied, respect the decision and do not retry it without a new request.
"""
# The list of skills is appended per conversation by agent.new_conversation() (see skills/skills.py).


@cache
def _client() -> OpenAI:
    load_dotenv()
    return OpenAI(base_url=os.environ["OPENAI_BASE_URL"], api_key=os.environ["OPENAI_API_KEY"])


def call_llm(messages: list, tools: list, on_text=None, on_reasoning=None) -> ChatCompletionMessage:
    """Stream a reply from the model and return the assembled assistant message.

    on_text / on_reasoning are called with each text / reasoning chunk as it arrives.
    """
    stream = _client().chat.completions.create(
        model=os.environ["OPENAI_MODEL"], messages=messages, tools=tools, stream=True
    )
    content, reasoning, calls = [], [], {}
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        # Reasoning isn't part of the OpenAI schema; providers like DeepSeek/OpenRouter add it.
        extra = delta.model_extra or {}
        thought = extra.get("reasoning_content") or extra.get("reasoning")
        if isinstance(thought, str) and thought:
            reasoning.append(thought)
            if on_reasoning:
                on_reasoning(thought)
        if delta.content:
            content.append(delta.content)
            if on_text:
                on_text(delta.content)
        # Tool calls arrive in fragments keyed by index: id and name first, then argument pieces.
        for fragment in delta.tool_calls or []:
            call = calls.setdefault(fragment.index, {"id": "", "name": "", "arguments": ""})
            if fragment.id:
                call["id"] = fragment.id
            if fragment.function:
                call["name"] += fragment.function.name or ""
                call["arguments"] += fragment.function.arguments or ""

    tool_calls = [
        ChatCompletionMessageFunctionToolCall(
            id=c["id"], type="function", function=Function(name=c["name"], arguments=c["arguments"])
        )
        for c in calls.values()
    ]
    extra_fields = {"reasoning_content": "".join(reasoning)} if reasoning else {}
    return ChatCompletionMessage(
        role="assistant", content="".join(content) or None, tool_calls=tool_calls or None, **extra_fields
    )
