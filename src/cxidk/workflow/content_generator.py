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

"""Module to generate content for the ingestion pipeline"""

import json
import pathlib
import random
import datetime
from typing import List, Optional

from strenum import StrEnum

from cxidk.core import base
from cxidk.wrapper import vertex

_DEFAULT_SENTIMENT_DISTRIBUTION = {
    "positive": "70%",
    "neutral": "20%",
    "negative": "10%",
}

_DEFAULT_TRAITS = [
    "amiable",
    "cordial",
    "gracious",
    "approachable",
    "sincere",
    "candid",
    "trustworthy",
    "articulate",
    "expressive",
    "considerate",
    "supportive",
    "cooperative",
    "reserved",
    "quiet",
    "introspective",
    "analytical",
    "practical",
    "stoic",
    "formal",
    "unassuming",
    "individualistic",
    "skeptical",
]

class AgentTeamDistribution(StrEnum):
    """Enumeration of agent team distribution strategies."""

    EVENLY = "evenly"
    RANDOM = "random"
    UNBALANCED = "unbalanced"

class Themes(StrEnum):
    """Enumeration of industry themes for conversation generation."""

    TELCO = "Telecommunications"
    ENTERTAINMENT = "Entertainment"
    RETAIL = "Retail"
    HEALTHCARE = "Healthcare"

class SentimentJourneys(StrEnum):
    """Enumeration of sentiment progression patterns in a conversation."""

    HIGH_TO_LOW = "High to Low"
    LOW_TO_HIGH = "Low to High"
    NEUTRAL_TO_LOW = "Neutral to Low"
    NEUTRAL_TO_HIGH = "Neutral to High"
    HIGH_TO_NEUTRAL = "High to Neutral"
    LOW_TO_NEUTRAL = "Low to Neutral"
    STABLE = "Stable with no change"

class Generator:
    """Generates synthetic conversational content using a large language model.

    This class provides methods to generate synthetic data such as conversation
    transcripts, agent personas, and metadata. It leverages a large language
    model to create varied content for developing and testing conversational AI
    systems.

    Attributes:
        project_id: The Google Cloud project ID.
        location: The location of the Vertex AI endpoint (e.g., 'us-central1').
        auth: An authentication object for Google Cloud.
        config: A configuration object for the API.
        generator: An instance of the `vertex.Generator` class for content creation.
    """

    def __init__(
        self,
        project_id: str,
        location: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ):
        """Initializes the Generator.

        Args:
            project_id: The Google Cloud project ID.
            location: The location of the Vertex AI endpoint (e.g., 'us-central1').
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """

        self.auth = auth or base.Auth()
        self.config = config or base.Config()

        self.project_id = project_id
        self.location = location

        self.generator = vertex.Generator(
            project_id=self.project_id,
            location=self.location,
        )

    def _assign_probabilities(
        self,
        range_long_convo: list,
        range_bad_sentiment: list,
        range_bad_performance: list,
    ):
        """Determines boolean flags based on probability ranges.

        This method uses random sampling against provided probability ranges to
        decide whether a conversation should be long, have bad sentiment, or
        exhibit poor agent performance.

        Args:
            range_long_convo: A list with two floats [min, max] for the
                probability of a long conversation.
            range_bad_sentiment: A list with two floats [min, max] for the
                probability of bad sentiment.
            range_bad_performance: A list with two floats [min, max] for the
                probability of bad agent performance.
        """
        long_conversation = False
        bad_sentiment = False
        bad_performance = False

        probability_long_convo = random.uniform(
            range_long_convo[0], range_long_convo[1]
        )
        probability_bad_sentiment = random.uniform(
            range_bad_sentiment[0],
            range_bad_sentiment[1]
        )
        probability_bad_performance = random.uniform(
            range_bad_performance[0],
            range_bad_performance[1]
        )

        if random.uniform(0, 1) < probability_long_convo:
            long_conversation = True

        if random.uniform(0, 1) < probability_bad_sentiment:
            bad_sentiment = True

        if random.uniform(0, 1) < probability_bad_performance:
            bad_performance = True

        return long_conversation, bad_sentiment, bad_performance

    def _set_llm_parameters(
        self,
        range_temperature: list,
        range_topp: list,
        range_topk: list,
    ):
        """Sets generative model parameters by sampling from specified ranges.

        This method randomizes the temperature, top-p, and top-k parameters for
        the large language model within the given min/max boundaries.

        Args:
            range_temperature: A list with two floats [min, max] for temperature.
            range_topp: A list with two floats [min, max] for top-p.
            range_topk: A list with two integers [min, max] for top-k.

        Returns:
            A tuple containing the randomly selected temperature (float),
            top-p (float), and top-k (int) values.
        """
        temperature = random.uniform(
            range_temperature[0],
            range_temperature[1]
        )
        topp = random.uniform(
            range_topp[0],
            range_topp[1]
        )
        topk = random.randint(
            int(range_topk[0]),
            int(range_topk[1])
        )
        return temperature, topp, topk

    def _set_prompt_parts(
        self,
        parameters: dict
    ) -> dict[str, str]:
        """Constructs a dictionary of prompt components based on input parameters.

        This method dynamically builds various sections of a prompt for the
        language model, such as context, instructions, and persona, based on
        the provided generation parameters.

        Args:
            parameters: A dictionary containing generation settings like 'theme',
                'topics', 'long_conversation', etc.

        Returns:
            A dictionary where keys are prompt section names (e.g., 'context',
            'instructions') and values are the corresponding formatted strings.
        """
        prompt_parts = {}
        today = datetime.date.today().strftime("%A, %B %d, %Y")

        prompt_parts['language'] = "".join((
            "\n--- LANGUAGE ---"
            "Make sure that the conversation is in ANY of"
            f"the following languages {parameters['language']}"
        ))
        prompt_parts['turn_conclusion'] = "".join((
            "\n--- CONCLUSION ---"
            "If you believe the conversation has completed. just output: QUIT"
        ))
        prompt_parts['turn_sentiment'] = "".join((
            "\n--- SENTIMENT ---"
            f"The conversation's sentiment should follow a {parameters['sentiment_journeys']}"
        ))
        prompt_parts['turn_persona'] = "".join((
            "\n--- PERSONA ---"
            "Always have in mind that you are a CUSTOMER, answering a virtual agent,"
            "so you need to always have customer behaviors"
            "Never repeat something from the context, always generate"
            "a new answer from the CUSTOMER perspective"
            "Always remember, you are a CUSTOMER"
        ))
        prompt_parts['turn_start'] =  "".join((
            f"You are a customer at {parameters['company_name']} and"
            f"you're contact about {parameters['topics']}"
            "Start the conversation with a custom welcome message,"
            "introduce yourself and your problem/issue which has to be"
            f" related to {parameters['topics']} or reason"
            f" to contact {parameters['company_name']}"
        ))
        prompt_parts['context'] = "".join((
            "\n--- CONTEXT ---"
            f"The contact center is in the {parameters['theme']} industry."
            f"The company name is {parameters['company_name']}."
            f"The conversation topic is: {parameters['topics']}."
        ))
        prompt_parts['instructions'] = "".join((
            "\n--- INSTRUCTIONS ---"
            "Make sure that the timestamps are from today's date,"
            f"month and specially YEAR: {today}"
            "Ensure the dialogue is natural and plausible, with realistic phrasing and flow."
        ))
        prompt_parts['output_format'] = "".join((
             "\n--- OUTPUT FORMAT ---"
             "The final output must be a JSON object that strictly conforms"
             "to the provided schema. Do not include any text or explanations"
             "outside of the JSON object."
        ))
        prompt_parts['additional_context'] = "".join((
            "\n--- ADDITIONAL CONTEXT---"
            f"{parameters['hint']}"
        ))
        prompt_parts['bad_performance'] = ""
        prompt_parts['turn_long_conversation'] = ""
        prompt_parts['turn_bad_sentiment'] = ""

        prompt_parts['bad_sentiment'] = "".join((
            f"The conversation's sentiment should follow a {parameters['sentiment_journeys']}"
            "sentiment journey."
        ))
        prompt_parts['long_conversation'] = "".join((
            "The conversation should be of average length,"
            "around 15-25 turns."
        ))
        if parameters['long_conversation']:
            prompt_parts['long_conversation'] = "".join(
                "The conversation must be long, consisting of at least 40 turns."
            )
            prompt_parts['turn_long_conversation'] = "".join(
                "The CUSTOMER must prolong the conversation"
                "with additional questions"
            )
        if parameters['bad_sentiment']:
            prompt_parts['bad_sentiment'] = "".join(
                "The CUSTOMER must display negative sentiment. They should exhibit traits"
                "like frustration, impatience, or confusion."
            )
            prompt_parts['turn_bad_sentiment'] = "".join(
                "The CUSTOMER must display negative sentiment. They should"
                "exhibit traits like frustration, impatience, or confusion."
            )
        if parameters['bad_performance']:
            prompt_parts['bad_performance'] = "".join(
                "The AGENT must perform poorly. They should demonstrate"
                "a lack of knowledge, empathy, or efficiency"
                "(e.g., giving incorrect information, being dismissive, or taking long pauses)."
            )
        return prompt_parts

    def create_parameters(
        self,
        generation_profile: Optional[dict] = None,
        randomize_select: Optional[List] = None,
    ) -> dict:
        """Create a set of random parameters for generating conversations.

        This method generates a dictionary of parameters used to guide the
        language model in creating a conversation. It uses a generation profile
        to define the boundaries for randomization.

        Args:
            generation_profile: A dictionary defining the ranges and options for
                various parameters (e.g., theme, topics, probabilities).
            randomize_select: An optional list of items to randomly select from.

        Returns:
            A dictionary of parameters for conversation generation.
        """
        ## Creates default generation profile for non-ui users
        if generation_profile is None:
            generation_profile = {
                "theme": ["Entertainment"],
                "model": "gemini-2.5-pro",
                "language": ["en-US"],
                "topics": [],
                "probabilities": {
                    "long_conversation": [0.2, 0.4],
                    "bad_sentiment": [0.2, 0.4],
                    "bad_performance": [0.2, 0.4],
                },
                "sentiment_journeys": ["Neutral to High"],
                "temperature": [0.8, 1], 
                "topk": [30, 40], 
                "topp": [0.9, 1], 
                "prompt_hint": [""]
            }


        randomized_item = random.choice(randomize_select) if randomize_select else None
        conversation_theme = Themes(random.choice(generation_profile['theme']))
        sentiment_journeys = SentimentJourneys(
            random.choice(generation_profile['sentiment_journeys'])
        )
        topic = "Generic"
        if len(generation_profile['topics']) != 0:
            topic = random.choice(generation_profile['topics'])
        company_name = generation_profile.get("company_name", f"Cymbal {conversation_theme}")

        long_conversation , bad_sentiment, bad_performance = self._assign_probabilities(
            generation_profile['probabilities']['long_conversation'],
            generation_profile['probabilities']['bad_sentiment'],
            generation_profile['probabilities']['bad_performance']
        )
        temperature, topp, topk = self._set_llm_parameters(
            generation_profile['temperature'],
            generation_profile['topp'],
            generation_profile['topk']
        )

        return {
            "sentiment_journeys": sentiment_journeys,
            "company_name": company_name,
            "bad_performance": bad_performance,
            "long_conversation": long_conversation,
            "bad_sentiment": bad_sentiment,
            "randomize_select": randomized_item,
            "theme": conversation_theme,
            "topics": topic,
            "topp": topp,
            "topk": topk,
            "language": generation_profile['language'],
            "temperature": temperature,
            "model": generation_profile['model'], 
            "hint": generation_profile['prompt_hint']
        }

    def create_conversation(
        self,
        parameters: Optional[dict] = None,
    ) -> str:
        """Creates a complete conversation transcript based on a set of parameters.

        Args:
            parameters: A dictionary of parameters to guide conversation generation.
                If None, a default set of parameters will be created.

        Returns:
            A JSON string representing the generated conversation transcript.
        """
        if parameters is None:
            parameters = self.create_parameters()

        prompt_parts: list[str] = []
        schema_path = pathlib.Path(__file__).parent / "utils/schemas/conversation.json"
        with open(schema_path, "r", encoding="utf-8") as f:
            conversation_schema = json.load(f)

        # Construct prompt parts
        parts = self._set_prompt_parts(parameters=parameters)
        prompt_parts.append(parts['context'])
        prompt_parts.append(parts['instructions'])
        prompt_parts.append(parts['language'])
        prompt_parts.append(parts['long_conversation'])
        prompt_parts.append(parts['bad_sentiment'])
        prompt_parts.append(parts['bad_performance'])
        prompt_parts.append(parts['output_format'])
        prompt_parts.append(parts['additional_context'])

        # Construct the prompt
        prompt = "\n".join(prompt_parts)
        self.generator.version = vertex.GeminiModels(parameters['model'])

        return self.generator.content(
            prompt=prompt,
            output_schema=conversation_schema,
            output_mime_type=vertex.MimeTypes.APPLICATION_JSON,
            temperature=parameters['temperature'],
            top_p=parameters['topp'],
            top_k=parameters['topk']
        )

    def create_turn(
        self,
        parameters: Optional[dict] = None,
        conversation_history: Optional[list] = None,
    ) -> str:
        """Generates the next customer turn in a conversation.

        Based on the provided history and parameters, this method generates the
        next utterance from the customer's perspective.

        Args:
            parameters: A dictionary of parameters to guide turn generation.
                If None, a default set will be created.
            conversation_history: A list of previous turns in the conversation.

        Returns:
            A JSON string representing the newly generated customer turn.
        """
        if parameters is None:
            parameters = self.create_parameters()

        prompt_parts: list[str] = []
        parts = self._set_prompt_parts(parameters=parameters)

        schema_path = pathlib.Path(__file__).parent / "utils/schemas/turn.json"
        with open(schema_path, "r", encoding="utf-8") as f:
            turn_schema = json.load(f)

        prompt_parts.append(parts['language'])
        if conversation_history is None or len(conversation_history) == 0:
            prompt_parts.append(parts['turn_start'])

        else:
            prompt_parts.append(
                "based on the context below"
                "\n--- CONTEXT ---"
                f"{conversation_history}"
            )
            prompt_parts.append(parts['turn_persona'])
            prompt_parts.append(parts['turn_sentiment'])
            prompt_parts.append(parts['turn_conclusion'])

        prompt_parts.append(parts['turn_bad_sentiment'])
        prompt_parts.append(parts['turn_long_conversation'])
        prompt_parts.append(parts['output_format'])

        prompt = "\n".join(prompt_parts)

        return self.generator.content(
            prompt=prompt,
            output_schema=turn_schema,
            output_mime_type=vertex.MimeTypes.APPLICATION_JSON,
            temperature=parameters['temperature'],
            top_p=parameters['topp'],
            top_k=parameters['topk']
        )

    def create_agents(
        self,
        number_of_agents: Optional[int] = 80,
        number_of_teams: Optional[int] = 8,
        agent_team_distribution: Optional[AgentTeamDistribution] = None,
        sentiment_distribution: Optional[dict] = None,
        traits: Optional[list] = None,
    ) -> dict:
        """Generates a list of synthetic agent profiles.

        This method creates a list of agent profiles, including details like
        agent ID, name, team, and personality traits, based on the specified
        parameters.

        Args:
            number_of_agents: The number of agents to generate.
            number_of_teams: The number of teams to distribute the agents into.
            agent_team_distribution: The distribution strategy for agents among teams.
            sentiment_distribution: A dictionary defining the sentiment distribution.
            traits: A list of possible personality traits for the agents.

        Returns:
            A dictionary containing a list of generated agent profiles.
        """
        if agent_team_distribution is None:
            agent_team_distribution = AgentTeamDistribution(AgentTeamDistribution.EVENLY)

        if traits is None:
            traits = _DEFAULT_TRAITS
        if sentiment_distribution is None:
            sentiment_distribution = _DEFAULT_SENTIMENT_DISTRIBUTION

        schema_path = pathlib.Path(__file__).parent / "utils/schemas/agent.json"
        with open(schema_path, "r", encoding="utf-8") as f:
            agent_schema = json.load(f)

        prompt = f"""
            Generate a list of {number_of_agents} agents.
            Distribute them into {number_of_teams} teams with a distribution of
            '{agent_team_distribution}'. Make sure that agent names are realistcs
            and the team names are creative (for a contact center).
            The agents should have a sentiment distribution of {sentiment_distribution}.
            The possible traits for the agents are: {traits}, note that each agent should
            have at least four traits. Please provide the output in JSON format conforming
            to the provided schema.
        """
        content_str = self.generator.content(
            prompt=prompt,
            output_schema=agent_schema,
            output_mime_type=vertex.MimeTypes.APPLICATION_JSON,
        )
        data = json.loads(content_str)

        if "agents" in data and isinstance(data.get("agents"), list):
            for agent in data["agents"]:
                agent["agent_id"] = str(random.randint(100000, 999999))

        return data

    def create_metadata(
        self,
        parameters: Optional[dict] = None,
        agents: Optional[dict] = None,
    ) -> dict:
        """Generates metadata for a conversation.

        This method creates a metadata dictionary for a conversation, including
        a customer satisfaction score and information about the agent involved,
        which can be used for ingestion into Contact Center AI Insights.

        Args:
            parameters: A dictionary of parameters to guide metadata generation.
            agents: A dictionary containing a list of available agent profiles.

        Returns:
            A dictionary containing the generated conversation metadata.
        """
        agents_list = agents
        theme = None
        if agents_list is None:
            schema_path = pathlib.Path(__file__).parent / "utils/defaults/agents.json"
            with open(schema_path, "r", encoding="utf-8") as f:
                agents_list = json.load(f)

        if parameters:
            if "theme" in parameters:
                theme = parameters["theme"]

        if agents_list is None:
            raise RuntimeError("Agent list doesn't exist")

        number_of_agents = len(agents_list["agents"])
        agent_to_chose = random.randint(0, number_of_agents - 1)
        score = random.randint(1, 5)

        return {
            "customer_satisfaction_rating": score,
            "agent_info": [agents_list["agents"][agent_to_chose]],
            "labels": {"theme": theme, "type":"Synthetic"}
        }
