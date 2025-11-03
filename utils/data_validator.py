"""
Data validator for football analytics queries.
Validates parsed slots against real data and provides deterministic selection.
"""

import pandas as pd
from typing import List, Dict, Optional, Tuple
from utils.query_parser import QuerySlots, ScopeType, Position
from fuzzywuzzy import fuzz
import logging

logger = logging.getLogger(__name__)

class DataValidator:
    def __init__(self, data_path: str = "./data/FINAL_with_rag.csv"):
        import os
        # Ensure we use absolute path relative to the project root
        if not os.path.isabs(data_path):
            # Get the directory of this file and go up to project root
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            data_path = os.path.join(project_root, data_path.lstrip('./'))

        self.df = pd.read_csv(data_path)

        # Competition name mapping for user-friendly display
        self.comp_display_names = {
            'eng Premier League': 'Premier League',
            'es La Liga': 'La Liga',
            'it Serie A': 'Serie A',
            'de Bundesliga': 'Bundesliga',
            'fr Ligue 1': 'Ligue 1'
        }

        self._prepare_lookups()

    def _prepare_lookups(self):
        """Prepare lookup tables for fast validation."""
        # Get unique values for validation - using actual column names
        self.competitions = self.df['comp'].unique().tolist() if 'comp' in self.df.columns else []
        self.teams = self.df['squad'].unique().tolist() if 'squad' in self.df.columns else []
        self.players = self.df['player'].unique().tolist() if 'player' in self.df.columns else []
        self.seasons = self.df['season'].unique().tolist() if 'season' in self.df.columns else ['2024-25']

        # Position mapping
        self.position_mapping = {
            'FW': ['Forward', 'Striker', 'Winger'],
            'MF': ['Midfielder', 'Attacking Midfielder', 'Defensive Midfielder'],
            'DF': ['Defender', 'Centre-Back', 'Full-Back', 'Wing-Back'],
            'GK': ['Goalkeeper']
        }

        # Team alias mapping - matches common abbreviations to full names
        self.team_aliases = {
            'man city': 'manchester city',
            'man utd': 'manchester utd',
            'man united': 'manchester utd',
            'spurs': 'tottenham',
            'arsenal': 'arsenal',
            'chelsea': 'chelsea',
            'liverpool': 'liverpool',
            'newcastle': 'newcastle utd',
            'west ham': 'west ham',
            'brighton': 'brighton',
            'barca': 'barcelona',
            'real': 'real madrid',
            'atletico': 'atlético madrid',
            'bayern': 'bayern munich',
            'dortmund': 'dortmund',
            'psg': 'paris s-g',
            'inter': 'inter',
            'milan': 'milan',
            'ac milan': 'milan',
            'juve': 'juventus',
            'juventus': 'juventus'
        }

    def validate_and_resolve(self, slots: QuerySlots) -> Tuple[QuerySlots, List[str], float]:
        """
        Validate slots against real data and resolve to concrete values.
        Returns: (resolved_slots, validation_errors, confidence)
        """
        resolved_slots = QuerySlots(**slots.__dict__)
        errors = []
        confidence_scores = []

        # Validate competition
        if slots.competition:
            comp_match, comp_conf = self._fuzzy_match(slots.competition, self.competitions)
            if comp_match:
                resolved_slots.competition = comp_match
                confidence_scores.append(comp_conf)
            else:
                # Try to find the closest match for suggestion
                from difflib import get_close_matches
                suggestions = get_close_matches(slots.competition, self.competitions, n=1, cutoff=0.4)

                if suggestions:
                    # Auto-correct to the suggestion
                    resolved_slots.competition = suggestions[0]
                    display_name = self.comp_display_names.get(suggestions[0], suggestions[0])
                    # Show info message that we auto-corrected
                    info_msg = f"ℹ️ Using {display_name} (corrected from '{slots.competition}')"
                    errors.append(info_msg)
                    confidence_scores.append(0.7)  # Good enough confidence to proceed
                else:
                    error_msg = f"⚠️ I couldn't find competition '{slots.competition}'. Available: Premier League, La Liga, Serie A, Bundesliga, Ligue 1"
                    errors.append(error_msg)
                    # Don't continue processing - return error immediately
                    resolved_slots.competition = None
                    confidence_scores.append(0.0)

        # Validate and resolve scope
        if slots.scope_type == ScopeType.STANDINGS_TOP_N:
            teams, scope_conf = self._resolve_top_n_teams(
                int(slots.scope_value) if slots.scope_value else 6,
                resolved_slots.competition
            )
            if teams:
                resolved_slots.scope_value = str(len(teams))
                confidence_scores.append(scope_conf)
            else:
                errors.append("Could not resolve top teams for standings")
                confidence_scores.append(0.0)

        # Validate season
        if slots.scope_type == ScopeType.SEASON and slots.scope_value:
            season_match, season_conf = self._fuzzy_match(slots.scope_value, self.seasons)
            if season_match:
                resolved_slots.scope_value = season_match
                confidence_scores.append(season_conf)
            else:
                # Use default current season
                resolved_slots.scope_value = "2024-25"
                confidence_scores.append(0.5)

        # Calculate overall confidence
        overall_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.5

        return resolved_slots, errors, overall_confidence

    def _fuzzy_match(self, query: str, candidates: List[str], threshold: int = 80) -> Tuple[Optional[str], float]:
        """Fuzzy match query against candidates."""
        best_match = None
        best_score = 0
        
        for candidate in candidates:
            score = fuzz.ratio(query.lower(), candidate.lower())
            if score > best_score and score >= threshold:
                best_score = score
                best_match = candidate
                
        confidence = best_score / 100.0 if best_match else 0.0
        return best_match, confidence

    def _resolve_top_n_teams(self, n: int, competition: Optional[str] = None) -> Tuple[List[str], float]:
        """
        Resolve top N teams from standings.
        This is a deterministic lookup that should use real standings data.
        """
        # Filter by competition if specified
        df_filtered = self.df.copy()
        if competition:
            df_filtered = df_filtered[df_filtered['comp'] == competition]
        
        if df_filtered.empty:
            return [], 0.0

        # For now, use a simple heuristic based on team performance
        # In a real system, this would query actual standings
        team_stats = df_filtered.groupby('squad').agg({
            'goals': 'sum',
            'assists': 'sum',
            'playing_time_min': 'sum'
        }).reset_index()
        
        # Simple ranking by total goals (placeholder for real standings)
        top_teams = team_stats.nlargest(n, 'goals')['squad'].tolist()
        
        confidence = 0.8 if len(top_teams) == n else 0.6
        return top_teams[:n], confidence

    def get_players_for_scope(self, slots: QuerySlots, min_minutes: int = 900) -> pd.DataFrame:
        """
        Get players matching the validated scope with deterministic selection.
        Aggregates stats across seasons when no specific season is requested.
        """
        df_filtered = self.df.copy()

        # Apply filters based on slots
        if slots.competition:
            df_filtered = df_filtered[df_filtered['comp'] == slots.competition]

        # Filter by scope
        if slots.scope_type == ScopeType.STANDINGS_TOP_N and slots.scope_value:
            top_teams, _ = self._resolve_top_n_teams(int(slots.scope_value), slots.competition)
            df_filtered = df_filtered[df_filtered['squad'].isin(top_teams)]
        elif slots.scope_type == ScopeType.CLUB and slots.scope_value:
            # Filter by team/club name using alias matching first, then fuzzy matching
            from fuzzywuzzy import process
            if 'squad' in df_filtered.columns:
                available_teams = df_filtered['squad'].unique().tolist()

                # First check if the query matches a known alias
                query_lower = slots.scope_value.lower().strip()
                matched_team = None

                # Check exact alias match
                if query_lower in self.team_aliases:
                    alias_target = self.team_aliases[query_lower]
                    # Find the actual team name in available teams that matches the alias target
                    for team in available_teams:
                        if alias_target.lower() in team.lower() or team.lower() in alias_target.lower():
                            matched_team = team
                            logger.info(f"Matched team '{slots.scope_value}' via alias to '{matched_team}'")
                            break

                # If no alias match, use fuzzy matching
                if not matched_team:
                    best_match = process.extractOne(slots.scope_value, available_teams)
                    if best_match and best_match[1] >= 60:  # 60% similarity threshold
                        matched_team = best_match[0]
                        logger.info(f"Matched team '{slots.scope_value}' to '{matched_team}' (fuzzy score: {best_match[1]})")

                if matched_team:
                    df_filtered = df_filtered[df_filtered['squad'] == matched_team]
                else:
                    logger.warning(f"No team found matching '{slots.scope_value}'")

        # Filter by position
        if slots.position and slots.position != Position.ALL:
            # Map position abbreviations to match data (FW, MF, DF, GK)
            position_abbrev = slots.position.value  # This is already FW, MF, DF, or GK
            if 'pos' in df_filtered.columns:
                df_filtered = df_filtered[df_filtered['pos'] == position_abbrev]

        # AGGREGATE ACROSS SEASONS when no specific season is requested
        # This prevents duplicate players from appearing multiple times
        if slots.scope_type != ScopeType.SEASON or not slots.scope_value:
            # Get season range for display
            if 'season' in df_filtered.columns:
                seasons = sorted(df_filtered['season'].unique())
                season_range = f"{seasons[0]} to {seasons[-1]}" if len(seasons) > 1 else seasons[0]
            else:
                season_range = "All seasons"

            # Group by player and aggregate stats
            agg_dict = {
                'goals': 'sum',
                'assists': 'sum',
                'xg': 'sum',
                'playing_time_min': 'sum',
                'squad': 'last',  # Use most recent team
                'pos': 'first',   # Position should be consistent
            }

            # Add any other numeric columns (but skip per-90 metrics - will recalculate)
            per_90_columns = [col for col in df_filtered.columns if 'per_90' in col.lower() or 'per90' in col.lower()]
            for col in df_filtered.columns:
                if (col not in agg_dict and col != 'player' and
                    df_filtered[col].dtype in ['int64', 'float64'] and
                    col not in per_90_columns):
                    agg_dict[col] = 'sum'

            df_filtered = df_filtered.groupby('player', as_index=False).agg(agg_dict)

            # Recalculate per-90 metrics after aggregation (don't sum them!)
            if 'goals' in df_filtered.columns and 'playing_time_min' in df_filtered.columns:
                df_filtered['goals_per_90'] = (df_filtered['goals'] / df_filtered['playing_time_min']) * 90
            if 'assists' in df_filtered.columns and 'playing_time_min' in df_filtered.columns:
                df_filtered['assists_per_90'] = (df_filtered['assists'] / df_filtered['playing_time_min']) * 90
            if 'xg' in df_filtered.columns and 'playing_time_min' in df_filtered.columns:
                df_filtered['xg_per_90'] = (df_filtered['xg'] / df_filtered['playing_time_min']) * 90

            # Store season range for display in output
            df_filtered['_season_range'] = season_range

        # Apply minimum minutes filter (after aggregation if applicable)
        if 'playing_time_min' in df_filtered.columns:
            df_filtered = df_filtered[df_filtered['playing_time_min'] >= min_minutes]

        return df_filtered

    def select_top_players(self, slots: QuerySlots, top_n: int = 5) -> pd.DataFrame:
        """
        Deterministic player selection with intelligent ranking.
        Uses position-aware metrics for fair comparisons.
        """
        df_players = self.get_players_for_scope(slots)

        if df_players.empty:
            return df_players

        df_players = df_players.copy()

        # Position-aware metric selection (when default metric is used)
        if slots.position and (not slots.metric or slots.metric == 'goals_per_90'):
            if slots.position.value == 'MF':
                # Midfielders: prioritize assists per 90
                ranking_column = 'assists_per_90'
                slots.metric = 'assists_per_90'
            elif slots.position.value == 'FW':
                # Forwards: Goals + Assists combined
                df_players['_g_plus_a'] = (
                    df_players.get('goals', 0) +
                    df_players.get('assists', 0)
                )
                ranking_column = '_g_plus_a'
                slots.metric = '_g_plus_a'
            elif slots.position.value == 'DF':
                # Defenders: progressive passes if available
                if 'progressive_passes' in df_players.columns:
                    ranking_column = 'progressive_passes'
                    slots.metric = 'progressive_passes'
                else:
                    ranking_column = 'games'
                    slots.metric = 'games'
            else:
                ranking_column = self._get_ranking_column(slots.metric, df_players.columns)
        else:
            # Use specified metric or default
            ranking_column = self._get_ranking_column(slots.metric, df_players.columns)
        
        if ranking_column not in df_players.columns:
            logger.warning(f"Ranking column '{ranking_column}' not found, using 'Goals'")
            ranking_column = 'Goals'
        
        # Deterministic selection: top N by metric
        if ranking_column in df_players.columns:
            top_players = df_players.nlargest(top_n, ranking_column)
        else:
            logger.warning(f"Column '{ranking_column}' not found, using 'goals'")
            top_players = df_players.nlargest(top_n, 'goals')
        
        return top_players

    def _get_ranking_column(self, metric: Optional[str], available_columns: List[str]) -> str:
        """Map metric to actual column name."""
        metric_mapping = {
            'goals': 'goals',
            'assists': 'assists',
            'xG': 'xg',
            'goals_per_90': 'goals_per_90',
            'assists_per_90': 'assists_per_90',
            '_g_plus_a': '_g_plus_a',
            'progressive_passes': 'progressive_passes',
            'games': 'games'
        }

        if metric and metric in metric_mapping:
            return metric_mapping[metric]

        # Default fallback
        return 'goals'

    def get_selection_summary(self, slots: QuerySlots, selected_df: pd.DataFrame) -> Dict[str, str]:
        """Generate a summary of the selection logic used."""
        summary = {
            'scope': self._format_scope_summary(slots),
            'metric': slots.metric or 'goals',
            'filters': f"Min {900} minutes played",
            'count': str(len(selected_df)),
            'selection_rule': f"Top {len(selected_df)} by {slots.metric or 'goals'}"
        }
        return summary

    def _format_scope_summary(self, slots: QuerySlots) -> str:
        """Format scope for summary display."""
        if slots.scope_type == ScopeType.STANDINGS_TOP_N:
            comp_part = f" {slots.competition}" if slots.competition else ""
            return f"Top {slots.scope_value}{comp_part} teams"
        elif slots.scope_type == ScopeType.SEASON:
            return f"Season {slots.scope_value}"
        else:
            return "All teams"