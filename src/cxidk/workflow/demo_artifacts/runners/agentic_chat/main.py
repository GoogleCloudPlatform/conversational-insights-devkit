# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Runner that generates the human to va conversations"""

import json
import logging
import time
import random
import datetime

from cxidk.wrapper import storage
from cxidk.workflow import content_generator
from cxidk.wrapper import agents

logging.basicConfig(level=logging.INFO)

_CONFIG_PATH = "insights-pipeline-producer-configs"
_CONFIG_FILES = ["projects.json","demos.json"]
_PRODUCER_PROJECT = "insights-pipeline-producer"

def import_config():
    """Import config"""
    gcs = storage.Gcs(project_id=_PRODUCER_PROJECT, bucket_name=_CONFIG_PATH)
    configs = []
    for config_file in _CONFIG_FILES:
        configs.append(
            gcs.download_blob(config_file).decode("utf-8")
        )
    return configs

def file_name_generator():
    """Generates a file name based on the current time.
    The format is YYMMDDHHMM.
    Returns:
        str: The formatted file name string.
    """
    return datetime.datetime.now().strftime("%y%m%d%H%M%S%f")


def _is_project_fully_configured(project):
    """Checks if a project has a theme and max conversations configured."""
    if (
        not project["generation_profile"]["theme"]
        or not project["generation_profile"]["max_conversations_per_run"]["agentic"]
    ):
        logging.error("Project (%s) not fully configured", project["project_id"])
        return False
    return True


def _handle_conversation_turn(generator, parameters, context):
    """Handles a single turn in a conversation."""
    conversation_history = "\n".join(
        [f"{turn['role']}: {turn['message']}" for turn in context]
    )
    generated_input = json.loads(
        generator.create_turn(
            parameters=parameters,
            conversation_history=conversation_history,
        )
    )
    generated_input["role"] = "customer"
    context.append(generated_input)
    time.sleep(random.uniform(3, 40))
    return generated_input


def _run_conversation(project_id, virtual_agent, generator, parameters):
    """Runs a single conversation with a virtual agent."""
    context = [
        {
            "role": "system",
            "message": f"Remember: this agent can only help you with {virtual_agent['topics']}",
        },
        {
            "role": "system",
            "message": "Always start the conversations with greetings and the help that you need",
        },
    ]

    dfcx = agents.Dialogflow(
        project_id=project_id,
        location=virtual_agent["location"],
        conversation_profile=virtual_agent["conversation_profile"],
    )
    dfcx.create_conversation()
    dfcx.create_participant()

    turn_count = 0
    while True:
        turn_count += 1
        generated_input = _handle_conversation_turn(generator, parameters, context)

        if generated_input["message"].lower() == "quit":
            dfcx.complete_conversation()
            logging.info("closing conversation due quit parameter")
            break
        if len(context) > 50:
            dfcx.complete_conversation()
            logging.info("closing lengthy conversation")
            break

        try:
            response = dfcx.send_message(text=generated_input["message"].lower())
            context.append({"message": response, "role": "AGENT"})
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error(e)
            dfcx.complete_conversation()
            logging.info("closing error conversation")
            break
    return turn_count


def _process_project(project, generator):
    """Processes a single project's configuration to generate conversations."""
    conversations_generated = 0
    if not _is_project_fully_configured(project) or not project.get("virtual_agents"):
        if not project.get("virtual_agents"):
            logging.info("No virtual agents found in the project %s configuration.", project["project_id"]) # pylint: disable=C0301
        return 0

    for virtual_agent in project["virtual_agents"]:
        conversations_generated += _process_virtual_agent(project, virtual_agent, generator)
    return conversations_generated

#Args is reqd for the cloud function to properly run
def runner(args): # pylint: disable=unused-argument
    """Runner: The code that will run in the cloud function"""

    conversations_generated = 0
    configs = import_config()

    for config_str in configs:
        config = json.loads(config_str)

        for project in config["projects"]:
            generator = content_generator.Generator(
                project_id=_PRODUCER_PROJECT,
                location="us-central1",
            )
            conversations_generated += _process_project(project, generator)

    logging.info("All conversations generated")
    return f"{conversations_generated} conversations generated"

def _process_virtual_agent(project, virtual_agent, generator):
    """Processes a virtual agent to generate conversations."""
    project_id = project["project_id"]
    logging.info(
        "------> Configuration found for %s project and %s virtual agent",
        project_id,
        virtual_agent["agent"],
    )

    parameters = generator.create_parameters(generation_profile=project["generation_profile"])
    conversations_generated = 0

    if virtual_agent["type"] != "next-gen":
        ranger = random.randint(0, int(project['generation_profile']['max_conversations_per_run']['agentic'])) # pylint: disable=C0301
        logging.info(
            "------> Generating %s conversations for %s %s",
            ranger, project_id, virtual_agent["environment"]
        )
        for index in range(ranger):
            logging.info(
                "------> Generating conversation %s of %s for %s %s",
                index + 1, ranger, project_id, virtual_agent["environment"]
            )
            conversations_generated += _run_conversation(project_id, virtual_agent, generator, parameters) # pylint: disable=C0301
    return conversations_generated
