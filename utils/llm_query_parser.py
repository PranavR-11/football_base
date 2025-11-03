"""
LLM-based query parser for flexible natural language understanding.
Uses GPT to extract structured information from user queries.
"""

from typing import Dict, Optional
from dataclasses import dataclass
import json
import os
from openai import OpenAI

@dataclass
class ExtractedQuery:
    """Structured information extracted from user query."""
    action: Optional[str] = None  # compare, rank, top, profile, trends
    team_name: Optional[str] = None
    player_names: Optional[list] = None
    position: Optional[str] = None  # forward, midfielder, defender, goalkeeper
    competition: Optional[str] = None  # premier league, la liga, etc.
    metric: Optional[str] = None  # goals, assists, xG, etc.
    scope: Optional[str] = None  # top_n, season, specific_team, all
    scope_value: Optional[str] = None
    confidence: float = 0.0

class LLMQueryParser:
    """Use LLM to understand natural language queries and extract structured information."""

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

    def parse(self, query: str) -> ExtractedQuery:
        """
        Use LLM to extract structured information from natural language query.

        Examples:
        - "compare midfielders of barca" -> team_name="barcelona", position="midfielder", action="compare"
        - "top forwards in premier league" -> position="forward", competition="premier league", action="top"
        - "show me real madrid's defenders" -> team_name="real madrid", position="defender"
        """

        system_prompt = """You are a football analytics query parser. Extract structured information from user queries.

Your job is to identify:
1. **action**: What the user wants to do (compare, rank, top, profile, trends)
2. **team_name**: Any team/club mentioned (e.g., "barca", "barcelona", "real madrid", "man city")
3. **player_names**: Specific player names mentioned
4. **position**: Player position (forward, midfielder, defender, goalkeeper, or null for all)
5. **competition**: League mentioned (premier league, la liga, serie a, bundesliga, ligue 1)
6. **metric**: Statistic mentioned (goals, assists, xG, goals_per_90, etc.)
7. **scope**: Type of scope (team, top_n, season, all)
8. **scope_value**: The value for scope (team name, number for top_n, season year)

Respond ONLY with valid JSON. No explanation, just JSON.

Examples:
Query: "compare midfielders of barca"
{"action": "compare", "team_name": "barcelona", "position": "midfielder", "scope": "team", "scope_value": "barcelona"}

Query: "top 5 forwards in premier league"
{"action": "top", "position": "forward", "competition": "premier league", "scope": "top_n", "scope_value": "5"}

Query: "show me real madrid's defenders"
{"action": "rank", "team_name": "real madrid", "position": "defender", "scope": "team", "scope_value": "real madrid"}

Query: "compare de bruyne and pedri"
{"action": "compare", "player_names": ["de bruyne", "pedri"], "scope": "players"}

Query: "midfielders from barcelona"
{"action": "rank", "team_name": "barcelona", "position": "midfielder", "scope": "team", "scope_value": "barcelona"}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                temperature=0.0,
                max_tokens=200
            )

            result_text = response.choices[0].message.content.strip()

            # Parse JSON response
            result = json.loads(result_text)

            # Create ExtractedQuery object
            extracted = ExtractedQuery(
                action=result.get("action"),
                team_name=result.get("team_name"),
                player_names=result.get("player_names"),
                position=result.get("position"),
                competition=result.get("competition"),
                metric=result.get("metric"),
                scope=result.get("scope"),
                scope_value=result.get("scope_value"),
                confidence=0.9  # LLM-based extraction is typically high confidence
            )

            return extracted

        except Exception as e:
            print(f"LLM query parsing error: {e}")
            # Return empty result on error
            return ExtractedQuery(confidence=0.0)

    def to_query_slots(self, extracted: ExtractedQuery):
        """Convert ExtractedQuery to QuerySlots format for compatibility."""
        from utils.query_parser import QuerySlots, Action, Position, ScopeType, EntityType

        slots = QuerySlots()

        # Map action
        action_map = {
            "compare": Action.COMPARE,
            "rank": Action.RANK,
            "top": Action.TOP,
            "profile": Action.PROFILE,
            "trends": Action.TRENDS
        }
        slots.action = action_map.get(extracted.action)

        # Map position
        position_map = {
            "forward": Position.FORWARD,
            "midfielder": Position.MIDFIELDER,
            "defender": Position.DEFENDER,
            "goalkeeper": Position.GOALKEEPER
        }
        slots.position = position_map.get(extracted.position, Position.ALL)

        # Map scope
        scope_map = {
            "team": ScopeType.CLUB,
            "top_n": ScopeType.STANDINGS_TOP_N,
            "season": ScopeType.SEASON,
            "players": ScopeType.CUSTOM_LIST
        }
        slots.scope_type = scope_map.get(extracted.scope)
        slots.scope_value = extracted.scope_value

        # Set other fields
        slots.competition = extracted.competition
        slots.metric = extracted.metric
        slots.confidence = extracted.confidence
        slots.entity_type = EntityType.PLAYER

        return slots
