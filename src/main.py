import asyncio
import os

from azure.core.credentials import AzureKeyCredential
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole
from semantic_kernel.kernel import Kernel
from utils.dotenv_loader import load_nearest_dotenv

from agents import GroundingAgent, PatchNotesAgent, TDTAgent

# Load environment variables
load_nearest_dotenv(start_path=__file__, override=False)

# AppInsights_connection_string = os.environ["AZURE_INSIGHTS_CONNECTION_STRING"]

# The envionrment variables needed to connect to the gpt-4o model in Azure AI Foundry
deployment_name = os.environ["CHAT_MODEL"]
endpoint = os.environ["CHAT_MODEL_ENDPOINT"]
api_key = os.environ["CHAT_MODEL_API_KEY"]
azure_key_credential = AzureKeyCredential(api_key)


async def main():
    # The Kernel is the main entry point for the Semantic Kernel. It will be used to add services and plugins to the Kernel.
    kernel = Kernel()

    # Add the necessary services and plugins to the Kernel
    # Adding the PatchNotesAgent and TDTAgent plugins will allow the OrchestratorAgent to call the functions in these plugins

    service_id = "orchestrator_agent"

    chat_completion_service = AzureChatCompletion(
        service_id=service_id, deployment_name=deployment_name, endpoint=endpoint, api_key=api_key
    )

    kernel.add_service(chat_completion_service)
    kernel.add_plugin(GroundingAgent.GroundingAgent(), plugin_name="GroundingAgent")
    kernel.add_plugin(PatchNotesAgent.PatchNotesAgent(), plugin_name="PatchNotesAgent")
    kernel.add_plugin(TDTAgent.TDTAgent(), plugin_name="TDTAgent")

    settings = kernel.get_prompt_execution_settings_from_service_id(service_id=service_id)
    # Configure the function choice behavior to automatically invoke kernel functions
    settings.function_choice_behavior = FunctionChoiceBehavior.Auto()

    # Create the Orchestrator Agent that will call the PatchNotes and TDT agents
    agent = ChatCompletionAgent(
        kernel=kernel,  # The Kernel that contains the services and plugins
        name="OrchestratorAgent",
        instructions="""
            You are the central coordinator for a suite of Set 15 TFT (Teamfight Tactics) analysis agents. Your role is to interpret user queries and delegate tasks to specialized agents:

            - Patch Notes Agent: analyze balance changes, patch wording, and systemic changes in official patch notes.
            - TDT (Tactics Dot Tools) Agent: retrieve in-game stats, unit/item/trait data, and composition statistics from live data sources.
            - Grounding Agent: retrieves factual information on game entities found in other agents' outputs. YOU should pass the most relevant entities found from other agents' outputs (items, units, traits) to the grounding agent.

            Be conservative about calling downstream agents:
            - Call downstream agents at most once per user turn unless new evidence appears that requires an additional call.
            - Prefer batching: if you need facts from multiple agents, form a single, minimal set of calls in one invocation rather than repeated sequential calls.
            - Before calling any agent, decide which specific facts you need (fields/filters) and request only those to reduce load and noise.
            - Use cached facts from the conversation history when available; ask a clarifying question instead of calling an agent if the user's intent is ambiguous.

            Decide which downstream agent(s) to call based on the user's intent and the evidence required. Examples:
            - Call Patch Notes Agent: user asks "What changed in the patch notes for Yasuo?" (text/wording analysis specific to patch notes).
            - Call TDT Agent: user asks "What is Lux's typical win rate?" (data/stat lookup only).
            - Call both agents in a single combined step: user asks "Did the recent patch change Lux's damage, and how did that affect her win rate?" (need patch wording + live stats to evaluate impact) — prefer a single coordinated call pattern that gathers both patch facts and the minimal stats required.
            - Call Grounding Agent: user asks about facts without requiring stats (e.g., "What's Lux's cost?" or "What does the Sorcerer trait do?").

            Strict grounding & call discipline:
            - Never invent or guess factual information about the set, units, items, traits, or index data. If you don't have a verified fact, say you don't know or ask to fetch the relevant data.
            - You should not use any information regarding League of Legends - only information from TFT (Teamfight Tactics) should be used.
            - How to use the Grounding Agent:
                1) Try to extract specific game entities (units, items, traits) from the initial user query. If you can extract any (even low confidence terms), you should call the Grounding Agent with those entities first to pass on facts to the other downstream agents.
                2) The Grounding Agent should also always be the last agent called for all user queries.
                3) Incorporate any new facts or clarifications provided by the Grounding Agent into your final response.
                4) If the Grounding Agent's response contradicts previous agent outputs, you can call a downstream agent (PatchNotesAgent or TDTAgent) at most one more time, with the new facts returned by the Grounding Agent.
                5) If previous agent outputs indicate a need for more information on specific entities, you can call the Grounding Agent again with those specific queries.
                6) If there are any contradictions left in your final response, prefer the Grounding Agent's facts over others.

            When merging outputs from multiple agents, prefer explicit facts (name, numeric stat, source URL) over inferences. Always cite the source of a fact (which agent) when making data-driven claims.

            Your responsibilities:
            - Understand the user's query.
            - Call only the agent(s) necessary to answer the question, and do so conservatively.
            - Combine their outputs into a clear, actionable answer.
            - Always re-ground your final answer using the Grounding Agent.
            - Provide strategic insights and predictions based only on grounded facts.

            If you are unable to verify a fact using retrieved data, reply with "I don't know" or ask to run a retrieval step; do not fabricate values or pretend certainty.
            """,
    )

    # Start the conversation with the user
    history = ChatHistory()

    # Start the logging
    print("Orchestrator Agent is starting...")

    is_complete = False
    while not is_complete:
        # The user will provide the query
        user_input = input(
            "Hello! Feel free to ask me anything about the current meta in TFT or any future patch notes: "
        )
        if not user_input:
            continue

        # The user can type 'exit' to end the conversation
        if user_input.lower() == "exit":
            is_complete = True
            break

        # Add the user's message to the chat history
        history.add_message(ChatMessageContent(role=AuthorRole.USER, content=user_input))

        # Invoke the Orchestrator Agent
        result = agent.invoke(messages=str(history))

        chunks: list[str] = []
        async for chunk in result:
            chunks.append(chunk.message.content)

        response_text = "".join(chunks)

        print(response_text)
        history.add_message(ChatMessageContent(role=AuthorRole.SYSTEM, content=response_text))


asyncio.run(main())
