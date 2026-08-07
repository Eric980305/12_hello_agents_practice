import unittest
from typing import Any, cast

from hello_agents_framework.core.agent import Agent
from hello_agents_framework.core.config import Config
from hello_agents_framework.core.llm import HelloAgentsLLM
from hello_agents_framework.core.message import Message


class FakeLLM:
    provider = "auto"


class EchoAgent(Agent):
    def run(self, input_text: str, **kwargs: Any) -> str:
        self.add_message(Message(content=input_text, role="user"))
        response = f"echo: {input_text}"
        self.add_message(Message(content=response, role="assistant"))
        return response


def fake_llm() -> HelloAgentsLLM:
    return cast(HelloAgentsLLM, FakeLLM())


class AgentTest(unittest.TestCase):
    def test_abstract_agent_cannot_be_instantiated(self) -> None:
        with self.assertRaises(TypeError):
            Agent(name="base", llm=fake_llm())  # type: ignore[abstract]

    def test_concrete_agent_has_one_run_entry_point(self) -> None:
        agent = EchoAgent(name=" Echo ", llm=fake_llm())

        result = agent.run("hello")

        self.assertEqual(result, "echo: hello")
        self.assertEqual(agent.name, "Echo")
        self.assertEqual(
            [message.role for message in agent.get_history()],
            ["user", "assistant"],
        )
        self.assertEqual(str(agent), "Agent(name=Echo, provider=auto)")

    def test_history_is_bounded_and_returned_as_a_copy(self) -> None:
        agent = EchoAgent(
            name="bounded",
            llm=fake_llm(),
            config=Config(max_history_length=2),
        )
        for index in range(3):
            agent.add_message(Message(content=str(index), role="user"))

        snapshot = agent.get_history()
        snapshot.clear()

        self.assertEqual(
            [message.content for message in agent.get_history()],
            ["1", "2"],
        )

    def test_clear_validation_and_default_config(self) -> None:
        agent = EchoAgent(name="test", llm=fake_llm())
        agent.add_message(Message(content="hello", role="user"))

        with self.assertRaises(TypeError):
            agent.add_message("not a message")  # type: ignore[arg-type]
        agent.clear_history()

        self.assertEqual(agent.get_history(), [])
        self.assertEqual(agent.config.provider, "auto")
        with self.assertRaises(ValueError):
            EchoAgent(name="   ", llm=fake_llm())


if __name__ == "__main__":
    unittest.main()
