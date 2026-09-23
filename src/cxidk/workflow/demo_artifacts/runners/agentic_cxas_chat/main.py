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

"""Runner that generates the human to virtual agent conversations using Agent Studio."""

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
_CONFIG_FILES = ["projects.json", "demos.json"]
_PRODUCER_PROJECT = "insights-pipeline-producer"


def import_config():
    """Import config"""
    gcs = storage.Gcs(project_id=_PRODUCER_PROJECT, bucket_name=_CONFIG_PATH)
    configs = []
    for config_file in _CONFIG_FILES:
        configs.append(gcs.download_blob(config_file))
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
    time.sleep(random.uniform(3, 5))
    return generated_input


def _run_conversation(project_id, location, virtual_agent, generator, parameters):
    """Runs a single conversation with an Agent Studio agent."""
    context = [
        {
            "role": "system",
            "message": f"Remember that this agent can only help you with {virtual_agent['topics']}",
        },
        {
            "role": "system",
            "message": "Always start the conversations with greetings and stating what do you need help with",  # pylint: disable=C0301
        },
        {
            "role": "system",
            "message": "Conversations must have MULTIPLE turns (above 15 turns) and be about internet_down, moving_address, bill_too_high and upgrade_elegibility, you can also start in one topic and move to a different one, dont accept human help easily"
        },
    ]

    agent_studio = agents.AgentStudio(
        project_id=project_id,
        location=location,
        env=virtual_agent["environment"],
    )
    session = agent_studio.create_session(agent_id=virtual_agent["agent"])
    logging.info(session)

    while True:
        try:
            generated_input = _handle_conversation_turn(generator, parameters, context)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Exception during turn generation: %s", e)
            time.sleep(5)
            break

        user_msg = generated_input["message"].strip()

        if user_msg.lower() == "quit":
            logging.info("Customer ended conversation: QUIT")
            break

        logging.info("Customer Turn: %s", user_msg)

        try:
            response = agent_studio.send_message(
                session_id=session, text=user_msg.lower()
            )
            if not response or response == "session ended":
                logging.info("Agent Studio session ended")
                break
            logging.info("Agent Studio Turn: %s", response.strip())
            context.append({"message": response, "role": "AGENT"})
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.info("Exception during send_message: %s", e)
            break
    return 1


def _process_virtual_agent(project, virtual_agent, generator):
    """Processes a virtual agent to generate conversations."""
    conversations_generated = 0
    if virtual_agent["type"] not in ["next-gen", "agent-studio", "cxas"]:
        return conversations_generated

    project_id = project["project_id"]
    location = virtual_agent.get("location") if virtual_agent.get("location") else project.get("location", "us")
    logging.info(
        "------> Configuration found for %s project and %s virtual agent found",
        project_id,
        virtual_agent["agent"],
    )

    parameters = generator.create_parameters(
        generation_profile=project["generation_profile"]
    )
    ranger = random.randint(
        0, int(project["generation_profile"]["max_conversations_per_run"]["agentic"])
    )
    ranger = random.randint(5, 10)

    logging.info(
        "------> Generating %s conversations for agent %s with the %s type on %s",
        ranger,
        virtual_agent["agent"],
        virtual_agent["type"],
        project_id,
    )

    for index in range(ranger):
        logging.info(
            "------> Generating conversation %s of %s for agent %s %s %s",
            index + 1,
            ranger,
            project_id,
            project["environments"],
            virtual_agent["agent"],
        )
        conversations_generated += _run_conversation(
            project_id, location, virtual_agent, generator, parameters
        )
    return conversations_generated


# Args is reqd for the cloud function to properly run
def runner(args):  # pylint: disable=unused-argument
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

            if not _is_project_fully_configured(project):
                continue

            if len(project["virtual_agents"]) == 0:
                logging.info(
                    "No virtual agents found in the project %s configuration.",
                    project["project_id"],
                )
                continue

            for virtual_agent in project["virtual_agents"]:
                if virtual_agent["agent"] == '' or len(virtual_agent["agent"]) == 0:
                    logging.info(
                        "Virtual agent not valid for the project %s configuration.",
                        project["project_id"]
                    )
                    continue

                conversations_generated += _process_virtual_agent(
                    project, virtual_agent, generator
                )

    return f"{conversations_generated} conversations generated"
