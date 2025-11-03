"""
Structured query parser for football analytics.
Converts free text into canonical slots for deterministic processing.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import re

class Action(Enum):
    COMPARE = "compare"
    PROFILE = "profile" 
    RANK = "rank"
    TOP = "top"
    TRENDS = "trends"

class EntityType(Enum):
    PLAYER = "player"
    TEAM = "team"
    COMPETITION = "competition"

class Position(Enum):
    FORWARD = "FW"
    MIDFIELDER = "MF"
    DEFENDER = "DF"
    GOALKEEPER = "GK"
    ALL = "ALL"

class ScopeType(Enum):
    STANDINGS_TOP_N = "standings_top_n"
    SEASON = "season"
    CLUB = "club"
    NATION = "nation"
    CUSTOM_LIST = "custom_list"
    ALL_TEAMS = "all_teams"

@dataclass
class QuerySlots:
    action: Optional[Action] = None
    entity_type: Optional[EntityType] = None
    scope_type: Optional[ScopeType] = None
    scope_value: Optional[str] = None  # e.g., "6" for top_n, "2024-25" for season
    position: Optional[Position] = None
    metric: Optional[str] = None
    competition: Optional[str] = None
    confidence: float = 0.0

class QueryParser:
    def __init__(self):
        # Synonym mappings for canonicalization
        self.action_synonyms = {
            "compare": ["compare", "vs", "versus", "against"],
            "profile": ["profile", "analyze", "breakdown", "stats"],
            "rank": ["rank", "ranking", "order", "sort"],
            "top": ["top", "best", "leading", "highest"],
            "trends": ["trends", "over time", "progression", "development"]
        }
        
        self.position_synonyms = {
            "FW": ["forward", "forwards", "striker", "strikers", "attacker", "attackers"],
            "MF": ["midfielder", "midfielders", "mid", "midfield"],
            "DF": ["defender", "defenders", "defence", "defense", "back"],
            "GK": ["goalkeeper", "goalkeepers", "keeper", "keepers", "gk"],
            "ALL": ["all", "any", "players", "everyone"]
        }
        
        self.competition_synonyms = {
            "eng Premier League": ["premier league", "epl", "pl", "english premier league"],
            "es La Liga": ["la liga", "laliga", "spanish league", "spain"],
            "it Serie A": ["serie a", "italian league", "italy"],
            "de Bundesliga": ["bundesliga", "german league", "germany"],
            "fr Ligue 1": ["ligue 1", "french league", "france"]
        }
        
        self.metric_synonyms = {
            "goals": ["goals", "goal", "scored"],
            "assists": ["assists", "assist", "assisted"],
            "xG": ["xg", "expected goals", "xgoals"],
            "goals_per_90": ["goals per 90", "goals/90", "goal rate"],
            "assists_per_90": ["assists per 90", "assists/90", "assist rate"]
        }

    def parse(self, query: str) -> QuerySlots:
        """Parse free text query into structured slots."""
        query_lower = query.lower()
        slots = QuerySlots()
        confidence_scores = []

        # Parse action
        action, action_conf = self._parse_action(query_lower)
        slots.action = action
        confidence_scores.append(action_conf)

        # Parse entity type (default to player for most queries)
        entity_type, entity_conf = self._parse_entity_type(query_lower)
        slots.entity_type = entity_type or EntityType.PLAYER
        confidence_scores.append(entity_conf)

        # Parse position
        position, pos_conf = self._parse_position(query_lower)
        slots.position = position or Position.ALL
        confidence_scores.append(pos_conf)

        # Parse competition
        competition, comp_conf = self._parse_competition(query_lower)
        slots.competition = competition
        confidence_scores.append(comp_conf)

        # Parse scope (top N, season, etc.)
        scope_type, scope_value, scope_conf = self._parse_scope(query_lower)
        slots.scope_type = scope_type
        slots.scope_value = scope_value
        confidence_scores.append(scope_conf)

        # Parse metric
        metric, metric_conf = self._parse_metric(query_lower)
        slots.metric = metric or "goals_per_90"  # Default fallback
        confidence_scores.append(metric_conf)

        # Calculate overall confidence
        slots.confidence = sum(confidence_scores) / len(confidence_scores)

        return slots

    def _parse_action(self, query: str) -> Tuple[Optional[Action], float]:
        """Parse action from query text."""
        for action, synonyms in self.action_synonyms.items():
            for synonym in synonyms:
                if synonym in query:
                    return Action(action), 0.9
        
        # Default inference based on patterns
        if any(word in query for word in ["best", "top"]):
            return Action.TOP, 0.7
        if "vs" in query or " v " in query:
            return Action.COMPARE, 0.8
        
        # For conversational queries, return None with low confidence
        conversational_words = ["what", "who", "how", "can", "do", "help", "hello", "hi"]
        if any(word in query.lower() for word in conversational_words):
            return None, 0.2
            
        return Action.TOP, 0.3  # Lower default confidence

    def _parse_entity_type(self, query: str) -> Tuple[Optional[EntityType], float]:
        """Parse entity type from query text."""
        if any(word in query for word in ["team", "teams", "club", "clubs"]):
            return EntityType.TEAM, 0.9
        if any(word in query for word in ["player", "players"]):
            return EntityType.PLAYER, 0.9
        
        # Default to player for most queries
        return EntityType.PLAYER, 0.6

    def _parse_position(self, query: str) -> Tuple[Optional[Position], float]:
        """Parse position from query text."""
        for pos, synonyms in self.position_synonyms.items():
            for synonym in synonyms:
                if synonym in query:
                    return Position(pos), 0.9
        return None, 0.5

    def _parse_competition(self, query: str) -> Tuple[Optional[str], float]:
        """Parse competition from query text - use word boundaries to avoid false matches."""
        import re

        # First try exact synonym matches
        for comp, synonyms in self.competition_synonyms.items():
            for synonym in synonyms:
                # Use word boundaries to avoid matching "pl" in "players"
                pattern = r'\b' + re.escape(synonym) + r'\b'
                if re.search(pattern, query):
                    return comp, 0.9

        # If no exact match, try to extract competition-like words for fuzzy matching
        # Look for patterns like "seria a", "ligue 1", etc.
        comp_pattern = r'\b((?:serie|seria|la liga|ligue|bundesliga|premier league|epl|pl)\s*\w*)\b'
        match = re.search(comp_pattern, query, re.IGNORECASE)
        if match:
            # Return the matched text for fuzzy matching in validator
            return match.group(1), 0.4

        return None, 0.3

    def _parse_scope(self, query: str) -> Tuple[Optional[ScopeType], Optional[str], float]:
        """Parse scope type and value from query text."""
        # Look for "top N" patterns
        top_n_match = re.search(r'top\s+(\d+)', query)
        if top_n_match:
            n = top_n_match.group(1)
            return ScopeType.STANDINGS_TOP_N, n, 0.9

        # Look for "big 6", "top 6" etc.
        if "big 6" in query or "top 6" in query:
            return ScopeType.STANDINGS_TOP_N, "6", 0.8

        # Look for team/club names (common patterns: "of [team]", "from [team]", "at [team]")
        # Extract potential team name after prepositions
        team_pattern = r'(?:of|from|at|for)\s+([a-z\s]+?)(?:\s|$)'
        team_match = re.search(team_pattern, query, re.IGNORECASE)
        if team_match:
            potential_team = team_match.group(1).strip()
            # Filter out common words that aren't team names
            excluded_words = {'the', 'a', 'an', 'in', 'on', 'this', 'that', 'these', 'those'}
            if potential_team.lower() not in excluded_words and len(potential_team) > 2:
                return ScopeType.CLUB, potential_team, 0.8

        # Look for season patterns
        season_match = re.search(r'(20\d{2}[-/]?\d{2})', query)
        if season_match:
            season = season_match.group(1)
            return ScopeType.SEASON, season, 0.9

        # No explicit scope mentioned - return None to trigger aggregation across all seasons
        return None, None, 0.5

    def _parse_metric(self, query: str) -> Tuple[Optional[str], float]:
        """Parse metric from query text."""
        for metric, synonyms in self.metric_synonyms.items():
            for synonym in synonyms:
                if synonym in query:
                    return metric, 0.9
        return None, 0.3

    def get_clarifying_question(self, slots: QuerySlots) -> Optional[str]:
        """Generate a clarifying question only when truly necessary."""
        # Only ask for clarification if confidence is very low AND we're missing critical info
        if slots.confidence < 0.4:
            critical_missing = []
            
            # Only ask about competition if it's explicitly mentioned but unclear
            if "league" in slots.action.value.lower() if slots.action else False:
                if not slots.competition:
                    critical_missing.append("which competition")
            
            # Only ask about specific scope if user mentioned "top" but no number
            if slots.action and "top" in slots.action.value.lower():
                if not slots.scope_value:
                    critical_missing.append("how many players")
                    
            if critical_missing:
                return f"Could you clarify {' and '.join(critical_missing)}?"
        
        return None

    def format_inferred_scope(self, slots: QuerySlots) -> str:
        """Format the inferred scope as a readable string for UI display."""
        parts = []
        
        if slots.competition:
            parts.append(slots.competition)
        
        if slots.scope_type == ScopeType.STANDINGS_TOP_N and slots.scope_value:
            parts.append(f"top {slots.scope_value}")
        elif slots.scope_type == ScopeType.SEASON and slots.scope_value:
            parts.append(slots.scope_value)
            
        if slots.position and slots.position != Position.ALL:
            parts.append(slots.position.value.lower())
            
        if slots.metric:
            parts.append(f"by {slots.metric}")
            
        return " • ".join(parts) if parts else "All players"