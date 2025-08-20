import asyncio
import os

from dotenv import load_dotenv
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
from semantic_kernel.contents.utils.author_role import AuthorRole
from semantic_kernel.kernel import Kernel
from azure.core.credentials import AzureKeyCredential

import PatchNotesAgent
import TDTAgent

# Load environment variables
load_dotenv()

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
        service_id=service_id, 
        deployment_name=deployment_name, 
        endpoint=endpoint, 
        api_key=api_key)
    
    kernel.add_service(chat_completion_service)
    kernel.add_plugin(PatchNotesAgent.PatchNotesAgent(), plugin_name="PatchNotesAgent")
    kernel.add_plugin(TDTAgent.TDTAgent(), plugin_name="TDTAgent")

    settings = kernel.get_prompt_execution_settings_from_service_id(service_id=service_id)
    # Configure the function choice behavior to automatically invoke kernel functions
    settings.function_choice_behavior = FunctionChoiceBehavior.Auto()

    # Create the Orchestrator Agent that will call the PatchNotes and TDT agents
    agent = ChatCompletionAgent(
        kernel=kernel, # The Kernel that contains the services and plugins
        name="OrchestratorAgent",
        instructions=f"""
            You are the central coordinator for a suite of TFT analysis agents. Your role is to interpret user queries and delegate tasks to specialized agents: >

            - Patch Notes Agent for analyzing balance changes in upcoming patches to the game.
            - TDT or Tactics Dot Tools Agent for retrieving stats about items, units, traits, and more. >

            Based on the user's intent, you decide which agent(s) to call and how to synthesize their outputs into a strategic, data-driven response. You are responsible for: >

            - Understanding the user's query.
            - Calling the appropriate agent(s).
            - Combining their outputs into a clear, actionable answer.
            - Providing strategic insights and predictions based on the data.

            Only call downstream agents if you need to, not all queries will need a call to a different agent.
            Do not guess any information about units (like their cost or traits), traits (like what they do), or items (their specific stats) if you aren't sure.
            """
    )

    # Start the conversation with the user
    history = ChatHistory()

    # Start the logging
    print("Orchestrator Agent is starting...")

    is_complete = False
    while not is_complete:
        # The user will provide the query
        user_input = input("Hello! Feel free to ask me anything about the current meta in TFT or any future patch notes: ")
        if not user_input:
            continue
        
        # The user can type 'exit' to end the conversation
        if user_input.lower() == "exit":
            is_complete = True
            break

        # Add the user's message to the chat history
        history.add_message(ChatMessageContent(role=AuthorRole.USER, content=user_input))

        # Invoke the Orchestrator Agent to process the user's query
        async for response in agent.invoke(messages=str(history)):
            print(response)

asyncio.run(main())