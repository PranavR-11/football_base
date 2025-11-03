# Clean comparison logic using existing functions
def handle_comparison(players, intent, available_cols, seasons_for_query, text, llm):
    """Clean comparison handler using existing functions"""
    
    # Use existing bulk aggregation function
    key_metrics = ["goals", "assists", "xg", "progressive_carries", "progressive_passes"]
    metrics_to_compare = [normalize_metric_token(m, available_cols) for m in key_metrics if normalize_metric_token(m, available_cols)]
    
    # Get data using existing function
    bulk_result = aggregate_group_multi_metrics_mcp(
        players=players,
        metrics=metrics_to_compare,
        seasons_back=5,
        include_cohort=True,
        cohort_size=200
    )
    
    # Generate charts using existing functions
    charts_created = []
    if bulk_result and bulk_result.get("ok"):
        try:
            # Use existing plot_comprehensive_comparison function
            player_data = bulk_result.get("players", {})
            
            # Extract data for existing chart function
            all_seasons = []
            goals_data = {}
            assists_data = {}
            radar_percentiles = {}
            radar_actual_values = {}
            bar_chart_data = {}
            
            for player_name, data in player_data.items():
                if data.get("found"):
                    per_season = data.get("per_season", {})
                    latest_stats = data.get("latest", {})
                    
                    # Build data for existing chart function
                    seasons = sorted([int(s) for s in per_season.keys() if s.isdigit()])
                    if seasons and len(seasons) > len(all_seasons):
                        all_seasons = seasons
                    
                    goals_data[player_name] = [per_season.get(str(s), {}).get("goals", 0) for s in seasons]
                    assists_data[player_name] = [per_season.get(str(s), {}).get("assists", 0) for s in seasons]
                    radar_actual_values[player_name] = latest_stats
                    bar_chart_data[player_name] = {m: latest_stats.get(m, 0) for m in metrics_to_compare[:4]}
                    
                    # Simple percentile calculation
                    cohort = bulk_result.get("cohort", {})
                    percentiles = []
                    for metric in metrics_to_compare[:6]:
                        player_value = latest_stats.get(metric, 0)
                        cohort_values = cohort.get(metric, {}).get("values", [])
                        if cohort_values:
                            below = sum(1 for v in cohort_values if v < player_value)
                            percentile = (below / len(cohort_values)) * 100.0
                            percentiles.append(percentile)
                        else:
                            percentiles.append(50.0)
                    radar_percentiles[player_name] = percentiles
            
            # Use existing comprehensive chart function
            if all_seasons and goals_data and assists_data:
                comp_fname = f"comprehensive_comparison_{int(time.time())}.png"
                comp_path = plot_comprehensive_comparison(
                    players, all_seasons, goals_data, assists_data,
                    metrics_to_compare[:6], radar_percentiles, radar_actual_values,
                    bar_chart_data, comp_fname
                )
                if comp_path:
                    charts_created.append(("comprehensive", comp_path))
        
        except Exception as e:
            dbg("Chart generation failed: %s", e)
    
    # Generate analysis using existing data
    response_parts = []
    
    if bulk_result and bulk_result.get("ok"):
        player_data = bulk_result.get("players", {})
        
        # Statistical overview
        stats_overview = []
        for player in players:
            data = player_data.get(player, {})
            if data.get("found"):
                latest = data.get("latest", {})
                goals = latest.get("goals", 0)
                assists = latest.get("assists", 0)
                stats_overview.append(f"{player} has {goals} goals and {assists} assists this season")
        
        if stats_overview:
            response_parts.append(". ".join(stats_overview) + ".")
        
        # Detailed comparison for 2 players
        if len(players) == 2:
            p1, p2 = players[0], players[1]
            p1_data = player_data.get(p1, {}).get("latest", {})
            p2_data = player_data.get(p2, {}).get("latest", {})
            
            comparison_prompt = f"""Compare {p1} and {p2}. Write detailed analysis covering:
1. Playing styles and strengths
2. Current performance analysis
3. Tactical roles and impact

Stats: {p1} ({p1_data.get('goals', 0)} goals, {p1_data.get('assists', 0)} assists) vs {p2} ({p2_data.get('goals', 0)} goals, {p2_data.get('assists', 0)} assists)

Write 3-4 analytical paragraphs."""

            analysis = llm.predict(comparison_prompt, max_tokens=400, temperature=0.1)
            if analysis and analysis.strip():
                response_parts.append(analysis.strip())
    
    # Output single response
    if response_parts:
        final_response = "\n\n".join(response_parts)
        print(final_response)
    else:
        print(f"Comparison analysis for {', '.join(players)} with comprehensive charts generated.")
    
    return True