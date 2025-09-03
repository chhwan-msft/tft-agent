# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import os
import requests
import time

from bs4 import BeautifulSoup
from azure.ai.agents.models import AsyncFunctionTool, MessageRole
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from semantic_kernel.functions import kernel_function

from utils.rag_tool import ground_text_and_add_to_history

system_prompt = """
You are an expert in parsing and analyzing Teamfight Tactics patch notes. Your job is:

- Extract and summarize buffs, nerfs, reworks, and system changes.
- Highlight the most impactful changes.
- Identify potential meta shifts based on balance adjustments.

Guidelines and available tools:

- get_patch_notes: MUST be called first to obtain the authoritative, full-text patch notes for the latest patch. Only analyze patch notes returned by this tool; do not fetch or assume additional patch content from other sources.

- Always call `get_patch_notes` before producing any analysis.
- Keep outputs concise, structured, and focused on competitive implications.
"""

user_prompt = "The following is the user's query. If you can't figure it out, respond with 'I don't know' instead of trying to guess or taking too long. "


class PatchNotesAgent:
    """
    A class to represent the Patch Notes Agent.
    """

    # class-level cache shared across instances in this process
    _cached_patch_notes: str | None = None

    @classmethod
    def get_patch_notes(cls):
        """Fetch patch notes once per process and cache result for the session."""
        # Return cached copy if present
        if cls._cached_patch_notes:
            print("[PatchNotesAgent] Returning cached patch notes")
            return cls._cached_patch_notes

        base_url = "https://www.leagueoflegends.com"
        tag_url = f"{base_url}/en-us/news/tags/teamfight-tactics-patch-notes/"

        # Fetch the tag page
        response = requests.get(tag_url)
        soup = BeautifulSoup(response.text, "html.parser")

        # Find the first article link
        first_link_tag = soup.select_one('a[data-testid="articlefeaturedcard-component"]')
        if not first_link_tag:
            cls._cached_patch_notes = "No article link found."
            return cls._cached_patch_notes

        article_url = first_link_tag["href"]

        # Fetch the article content
        article_response = requests.get(article_url)
        article_soup = BeautifulSoup(article_response.text, "html.parser")

        # Extract main content
        patch_notes_div = article_soup.find("div", id="patch-notes-container")
        if patch_notes_div:
            notes = patch_notes_div.get_text(separator="\n", strip=True)
            cls._cached_patch_notes = notes
            return notes
        else:
            cls._cached_patch_notes = "Patch notes not found."
            return cls._cached_patch_notes

    @staticmethod
    async def ground_facts(query):
        print(f"Received query from PatchNotesAgent to ground: {query}")
        return (await ground_text_and_add_to_history(query))[1] or ""

    @kernel_function(
        description="An agent that pulls latest patch notes and makes predictions based on balance changes."
    )
    async def process_patch_notes(self, query: str) -> str:
        """
        Creates an Azure AI Agent that pulls latest patch notes and makes predictions based on balance changes.

        Returns:
        last_msg (json): The last message from the agent, which contains information based on the latest patch notes.

        """
        print("Calling PatchNotesAgent...")

        # Connecting to our Azure AI Foundry project, which will allow us to use the deployed gpt-4o model for our agent
        project_client = AIProjectClient(os.environ["AIPROJECT_ENDPOINT"], DefaultAzureCredential())

        # Add tools (agent methods `get_patch_notes` and `ground_facts`)
        functions = AsyncFunctionTool({self.get_patch_notes})
        _ = functions.definitions

        # Get existing agent from Foundry project
        patch_notes_agent = project_client.agents.get_agent(os.environ["PATCH_NOTES_RESEARCHER_AGENT_ID"])

        # # Create or get an agent in the Foundry project
        # patch_notes_agent = project_client.agents.create_agent(
        #     model="gpt-4o",
        #     name="patch-notes-agent",
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
        run = project_client.agents.runs.create(thread_id=thread.id, agent_id=patch_notes_agent.id)

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
                    if tool_call.function.name == "get_patch_notes":
                        output = self.get_patch_notes()
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

        print("Patch notes agent completed successfully!")
        return str(last_msg)
