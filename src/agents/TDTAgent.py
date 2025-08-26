# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import os
import requests
import time
import json

from azure.ai.agents.models import MessageRole, FunctionTool
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from utils.dotenv_loader import load_nearest_dotenv
from semantic_kernel.functions import kernel_function

# Load nearest .env (do not override existing process envs by default)
load_nearest_dotenv(start_path=__file__, override=False)

system_prompt = """
You are an intelligent agent in a multiagent system designed for Teamfight Tactics (TFT).

Tool availability:
- get_general_stats: AVAILABLE — retrieves general statistics about TFT units, items, and traits.
- get_comp_stats: DISABLED — do not call or rely on this tool (it is not functional right now).

When you receive a query from the orchestration agent, determine whether the available tools are sufficient.

Examples:
- Use get_general_stats only: "What are Lux's current cost and typical build components?"
- Do NOT call get_comp_stats: any request asking for team composition aggregator stats should be answered by either using get_general_stats (if possible) or by saying you don't have comp-level data and offering to fetch or enable it later.
- Use neither: questions about lore, cosmetics, or developer intent should not call tools (e.g., "What's Lux's backstory?").

Guidelines:
- Only call get_general_stats when the question requires factual unit/item/trait stats.
- Never call get_comp_stats — it is disabled by policy for this deployment.
- If a question requires comp-level analysis (win rates, meta comps) that you cannot derive from get_general_stats, say you don't have the required data and offer to fetch it once the comp tool is available.

Response requirements:
- Keep answers concise, data-driven, and clearly cite the source (e.g., "data from get_general_stats").
- Do not guess or invent statistics; if data is missing or ambiguous, explicitly state that and avoid asserting unverified facts.
"""

user_prompt = "Never call the tool get_comp_stats, it is not ready for use yet. The following is the user's query: "


class TDTAgent:
    """
    A class to represent the Tactis Dot Tools Agent.
    """

    # class-level cache shared across instances in this process
    _cached_general_stats: str | None = None

    @classmethod
    def get_general_stats(cls):
        """Fetch general stats once per session and cache the JSON string."""
        if cls._cached_general_stats:
            print("[TDTAgent] Returning cached general stats")
            return cls._cached_general_stats
        url = "https://d3.tft.tools/stats2/general/1100/15151/1"
        response = requests.get(url)
        cls._cached_general_stats = json.dumps(response.json())
        return cls._cached_general_stats

    @staticmethod
    def get_comp_stats():
        # This tool is intentionally disabled at the host level. Return a safe placeholder.
        print("[TDTAgent] get_comp_stats requested but disabled by host")
        return json.dumps({"error": "get_comp_stats is disabled by host"})

    @kernel_function(
        description="An agent that pulls latest patch notes and makes predictions based on balance changes."
    )
    async def process_patch_notes(self, query: str) -> str:
        """
        Creates an Azure AI Agent that pulls stats from tactics.tools.

        Returns:
        last_msg (json): The last message from the agent, which contains information based on stats.

        """
        print("Calling TDTAgent...")

        # Connecting to our Azure AI Foundry project, which will allow us to use the deployed gpt-4o model for our agent
        project_client = AIProjectClient(os.environ["AIPROJECT_ENDPOINT"], DefaultAzureCredential())

        # Register agent tools using bound methods
        # Register sync tools with FunctionTool and async tools with AsyncFunctionTool
        functions = FunctionTool({self.get_general_stats, self.get_comp_stats})
        _ = functions.definitions

        # Get existing agent from Foundry project
        tdt_agent = project_client.agents.get_agent(os.environ["TACTICS_DOT_TOOLS_AGENT_ID"])

        # tdt_agent = project_client.agents.create_agent(
        #     model="gpt-4o",
        #     name="tdt-agent",
        #     instructions=system_prompt, # System prompt for the agent
        #     tools=tools_defs
        # )

        # Create a thread which is a conversation session between an agent and a user.
        thread = project_client.agents.threads.create()

        # Create a message in the thread with the user asking for information about the patch notes
        _ = project_client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=f"{user_prompt}{query}",  # The user's message
        )
        # Run the agent to process the message in the thread
        run = project_client.agents.runs.create(thread_id=thread.id, agent_id=tdt_agent.id)

        # Poll the run status until it is completed or requires action
        while run.status in ["queued", "in_progress", "requires_action"]:
            time.sleep(3)
            run = project_client.agents.runs.get(thread_id=thread.id, run_id=run.id)

            print(run.status)

            if run.status == "requires_action":
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                tool_outputs = []
                for tool_call in tool_calls:
                    print(f"Processing tool call: {tool_call.function.name}")
                    if tool_call.function.name == "get_general_stats":
                        output = self.get_general_stats()
                        tool_outputs.append({"tool_call_id": tool_call.id, "output": output})
                    elif tool_call.function.name == "get_comp_stats":
                        # Do not execute the real get_comp_stats; return a disabled placeholder.
                        output = self.get_comp_stats()
                        tool_outputs.append({"tool_call_id": tool_call.id, "output": output})
                project_client.agents.runs.submit_tool_outputs(
                    thread_id=thread.id, run_id=run.id, tool_outputs=tool_outputs
                )

        # Check if the run was successful
        if run.status == "failed":
            print(f"Run failed: {run.last_error}")

        # Delete the agent when it's done running
        # project_client.agents.delete_agent(patch_notes_agent.id)

        # Get the last message from the thread
        last_msg = project_client.agents.messages.get_last_message_text_by_role(
            thread_id=thread.id, role=MessageRole.AGENT
        )

        print("TDT agent completed successfully!")
        return str(last_msg)
