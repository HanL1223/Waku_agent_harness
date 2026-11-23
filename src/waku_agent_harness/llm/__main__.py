import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from waku_agent_harness.llm import SYSTEM_PROMPT
from waku_agent_harness.tools.bash import BASH_TOOL, run_bash
from waku_agent_harness.tools.read_file import READ_FILE_TOOL, read_file



def main():
    load_dotenv()
    client = OpenAI(base_url=os.environ["OPENAI_BASE_URL"], api_key=os.environ["OPENAI_API_KEY"])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": input("<Enter your prompt> ")},
    ]

    while True:
        response = client.chat.completions.create(
            model=os.environ["OPENAI_MODEL"], messages=messages, tools=[BASH_TOOL, READ_FILE_TOOL]
        )
        message = response.choices[0].message
        if not message.tool_calls:
            print("\nAgent:", message.content)
            return

        messages.append(message.model_dump(exclude_unset=True))
        for call in message.tool_calls:
            try:
                if call.type != "function":
                    raise ValueError("Unknown tool")
                arguments = json.loads(call.function.arguments)
                if not isinstance(arguments, dict):
                    raise ValueError("Expected an object of arguments")
                if call.function.name == "bash":
                    if not isinstance(arguments.get("command"), str):
                        raise ValueError("Expected a string command")
                    result = run_bash(arguments["command"])
                elif call.function.name == "read_file":
                    if not isinstance(arguments.get("path"), str):
                        raise ValueError("Expected a string path")
                    result = read_file(arguments["path"])
                else:
                    raise ValueError("Unknown tool")
            except (ValueError, TypeError) as error:
                result = f"Invalid tool request: {error}"
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})


if __name__ == "__main__":
    main()
