# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import json
import os
import time

from azure.ai.agents.models import AsyncFunctionTool, MessageRole
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from semantic_kernel.functions import kernel_function

from utils.dotenv_loader import load_nearest_dotenv
from utils.rag_tool import ground_text_and_add_to_history

# Load nearest .env (do not override existing process envs by default)
load_nearest_dotenv(start_path=__file__, override=False)

system_prompt = """
You are an expert in extracting units, items, and traits from other LLM outputs to retrieve factual information from indexes. Your context is set 15 in TFT (teamfight tactics).
Your job is to:

- Extract any units, items, or traits from initial query (the query will be another agent's output).
- Call `ground_facts` and pass a JSON payload with those keys and lists (for example: {"units": ["Yasuo","Garen"], "items": ["Infinity Edge"]}).
- The `ground_facts` tool will return factual context for each named entity; return these facts in structured format for the main agent to be able to process easily.

Available tools:

- ground_facts: Use this tool to ground statements about specific game entities (units, items, traits).
    - This tool will return at most 5 units, 5 items, and 5 traits per query.
    - If you cannot find information from the tool's output, you can call it again up to 3 times with entities you were not able to find information on from previous tool calls.

Examples of units, items, and traits from this set, to help with entity extraction (this is not an exhaustive list):
- Units: ["Yasuo", "Garen", "Ahri"]
- Items: ["Infinity Edge", "Bloodthirster", "Striker's Flail"]
- Traits: ["Sorcerer", "Mighty Mech", "Duelist"]

Notes:
- Always call `ground_facts` with the collected entity lists before finalizing your output.
- If you cannot identify any entities to ground, you may skip `ground_facts`, but explicitly state that no entities were found to ground.
- Keep outputs concise, structured, and consistent with the facts the tool returns. Do not add any analysis of your own, keep it to the facts.
- Do NOT fabricate information. If the tool cannot provide an answer, state that clearly.
"""

user_prompt = "The following is the input: "


class GroundingAgent:
    """
    A class to represent the Grounding Agent.
    """

    @staticmethod
    async def ground_facts(query):
        print(f"Received query from GroundingAgent to ground: {query}")
        return (await ground_text_and_add_to_history(query))[1] or ""

    @kernel_function(description="An agent that helps ground LLM generated responses on factual game entities.")
    async def process_patch_notes(self, query: str) -> str:
        """
        Creates an Azure AI Agent that helps ground LLM generated responses on factual game entities.

        Returns:
        last_msg (json): The last message from the agent, which returns a response grounded on factual game entities.

        """
        print("Calling GroundingAgent...")

        # Connecting to our Azure AI Foundry project, which will allow us to use the deployed gpt-4o model for our agent
        project_client = AIProjectClient(os.environ["AIPROJECT_ENDPOINT"], DefaultAzureCredential())

        # Add tools (`ground_facts`)
        async_functions = AsyncFunctionTool({self.ground_facts})
        _ = async_functions.definitions

        # Get existing agent from Foundry project
        grounding_agent = project_client.agents.get_agent(os.environ["GROUNDING_AGENT_ID"])

        # # Create or get an agent in the Foundry project
        # grounding_agent = project_client.agents.create_agent(
        #     model="gpt-4o",
        #     name="grounding-agent",
        #     instructions=system_prompt,  # System prompt for the agent
        #     tools=tools_defs,
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
        run = project_client.agents.runs.create(thread_id=thread.id, agent_id=grounding_agent.id)

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
                    if tool_call.function.name == "ground_facts":
                        model_args = json.loads(tool_call.function.arguments or "{}")
                        output = await self.ground_facts(model_args)
                        tool_outputs.append({"tool_call_id": tool_call.id, "output": output})

                project_client.agents.runs.submit_tool_outputs(
                    thread_id=thread.id, run_id=run.id, tool_outputs=tool_outputs
                )

        # Check if the run was successful
        if run.status == "failed":
            print(f"Run failed: {run.last_error}")

        # Delete the agent when it's done running (optional)
        # project_client.agents.delete_agent(patch_notes_agent.id)

        # Get the last message from the thread
        last_msg = project_client.agents.messages.get_last_message_text_by_role(
            thread_id=thread.id, role=MessageRole.AGENT
        )

        print("Grounding agent completed successfully!")
        return str(last_msg)
