import asyncio
from typing import cast
from uuid import uuid4

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import MessagesState
from langgraph.graph.state import CompiledStateGraph

load_dotenv()

from agents import DEFAULT_AGENT, get_agent, load_agent  # noqa: E402
from memory import initialize_database, initialize_store  # noqa: E402


async def main() -> None:
    await load_agent(DEFAULT_AGENT)
    agent = cast(CompiledStateGraph, get_agent(DEFAULT_AGENT))
    inputs: MessagesState = {
        "messages": [HumanMessage("Find me a recipe for chocolate chip cookies")]
    }
    async with initialize_database() as saver, initialize_store() as store:
        if hasattr(saver, "setup"):
            await saver.setup()
        if hasattr(store, "setup"):
            await store.setup()
        agent.checkpointer = saver
        agent.store = store
        result = await agent.ainvoke(
            input=inputs,
            config=RunnableConfig(configurable={"thread_id": str(uuid4())}),
        )
    result["messages"][-1].pretty_print()

    # Draw the agent graph as png
    # requires:
    # brew install graphviz
    # export CFLAGS="-I $(brew --prefix graphviz)/include"
    # export LDFLAGS="-L $(brew --prefix graphviz)/lib"
    # pip install pygraphviz
    #
    # agent.get_graph().draw_png("agent_diagram.png")


if __name__ == "__main__":
    asyncio.run(main())
