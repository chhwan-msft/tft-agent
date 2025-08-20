# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import os
import requests
import time
import json

from bs4 import BeautifulSoup
from azure.ai.agents.models import FunctionTool, MessageRole
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from semantic_kernel.functions import kernel_function

load_dotenv()

system_prompt = """
You are an intelligent agent in a multiagent system designed for Teamfight Tactics (TFT). You have access to two specialized tools:

get_general_stats: Retrieves general statistics about TFT units, items, and traits.
get_comp_stats: Retrieves statistics about high-performing TFT team compositions.

When you receive a query from the orchestration agent, your responsibilities are to:

Analyze the query intent to determine what kind of statistical data is needed.
Select the appropriate tool(s) to fulfill the query:

Use get_general_stats only
Use get_comp_stats only
Use both tools
Use neither tool if the query does not require gameplay statistics


Return a clean, summarized response that directly addresses the query and is easy for the orchestration agent to parse and route.

Tool Selection Guidelines:

Use get_general_stats if the query involves:

Specific champions, items, or traits
Questions about individual unit strength, item effectiveness, or trait synergies
General meta information or patch-specific changes


Use get_comp_stats if the query involves:

Optimal team compositions or meta builds
Win rates, top 4 rates, or performance metrics of team comps
Strategy recommendations based on ranked performance


Use both tools if the query requires:

A comprehensive analysis combining unit/item/trait data with team comp performance
Evaluations of how specific units or traits contribute to top-performing comps
Meta evolution or synergy effectiveness across multiple dimensions


Use neither tool if the query is:

Focused on lore, cosmetics, UI, or non-performance aspects of TFT
Speculative or philosophical in nature (e.g., game design theory)


Response Requirements:

Keep the output concise, relevant, and structured.
Your response should be data-rich, accurate, and formatted for easy interpretation by the main agent.
"""

user_prompt = "Never call the tool get_comp_stats, it is not ready for use yet. The following is the user's query: "

class TDTAgent:

    """
    A class to represent the Tactis Dot Tools Agent.
    """
    @kernel_function(description='An agent that pulls latest patch notes and makes predictions based on balance changes.')
    def process_patch_notes(self, query: str) -> str:
        """
        Creates an Azure AI Agent that pulls stats from tactics.tools.

        Returns:
        last_msg (json): The last message from the agent, which contains information based on stats.

        """
        print("Calling TDTAgent...")

        # Connecting to our Azure AI Foundry project, which will allow us to use the deployed gpt-4o model for our agent
        project_client = AIProjectClient(
            os.environ["AIPROJECT_ENDPOINT"],
            DefaultAzureCredential()
            )
        
        # General stats on units, items, traits
        def get_general_stats():
            url = f"https://d3.tft.tools/stats2/general/1100/15151/1"
            response = requests.get(url)
            return json.dumps(response.json())
            
        # Stats on high performing comps
        def get_comp_stats():
            url = f"https://api.tft.tools/team-compositions/1/15151"
            response = requests.get(url)
            return json.dumps(response.json())

        functions = FunctionTool({get_general_stats, get_comp_stats})

        # Get existing agent from Foundry project
        tdt_agent = project_client.agents.get_agent(os.environ["TACTICS_DOT_TOOLS_AGENT_ID"])
        # tdt_agent = project_client.agents.create_agent(
        #     model="gpt-4o",
        #     name="tdt-agent",
        #     instructions=system_prompt, # System prompt for the agent
        #     tools=functions.definitions
        # )

        # Create a thread which is a conversation session between an agent and a user. 
        thread = project_client.agents.threads.create()

        # Create a message in the thread with the user asking for information about the patch notes
        message = project_client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=f"{user_prompt}{query}", # The user's message
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
                        output = get_general_stats()
                        tool_outputs.append({"tool_call_id": tool_call.id, "output": output})
                    elif tool_call.function.name == "get_comp_stats":
                        output = get_comp_stats()
                        tool_outputs.append({"tool_call_id": tool_call.id, "output": output})
                project_client.agents.runs.submit_tool_outputs(thread_id=thread.id, run_id=run.id, tool_outputs=tool_outputs)

        # Check if the run was successful
        if run.status == "failed":
            print(f"Run failed: {run.last_error}")

        # Delete the agent when it's done running
        # project_client.agents.delete_agent(patch_notes_agent.id)

        # Get the last message from the thread
        last_msg = project_client.agents.messages.get_last_message_text_by_role(thread_id=thread.id,role=MessageRole.AGENT)
      
        print("TDT agent completed successfully!")

        return str(last_msg)