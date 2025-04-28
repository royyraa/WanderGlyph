import logging
import folium
import htmlmin
import os
import pandas as pd
from folium import Element
from folium.plugins import MarkerCluster

def add_heatmap_safely(m, point_coords):
    """Add heatmap layer, handling potential float key errors."""
    try:
        # Import here to catch import errors
        from folium.plugins import HeatMap
        
        # Use only string keys in gradient to avoid camelize errors
        HeatMap(
            point_coords,
            name='Heat Map',
            radius=10,
            blur=15,
            gradient={'0.4': 'blue', '0.65': 'lime', '1.0': 'red'}
        ).add_to(m)
        logging.info("Added heatmap layer successfully")
    except (ImportError, AttributeError) as e:
        logging.warning(f"Could not add heatmap: {e}")
        pass

def generate_map(counties, matched, states, points, point_gdf, output_path, add_markers, state_names):
    """Generate an interactive map with matched counties and point locations with toggleable layers."""
    # Set map center and zoom based on data
    center = [37.0902, -95.7129]  # Default US center
    zoom = 4
    
    if not matched.empty:
        bounds = matched.total_bounds
        center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
        # Adjust zoom based on bounds size
        lat_range = bounds[3] - bounds[1]
        lon_range = bounds[2] - bounds[0]
        if max(lat_range, lon_range) < 1:
            zoom = 8
        elif max(lat_range, lon_range) < 5:
            zoom = 6
        else:
            zoom = 4
    
    # Create map with OpenStreetMap as the default
    m = folium.Map(
        location=center, 
        zoom_start=zoom, 
        control_scale=True,
        tiles='OpenStreetMap'
    )
    
    # Create feature groups for better layer organization
    county_layer = folium.FeatureGroup(name='🏙️ Counties with Points')
    state_layer = folium.FeatureGroup(name='🗺️ State Boundaries')
    points_cluster_layer = folium.FeatureGroup(name='📍 Point Clusters')
    points_heatmap_layer = folium.FeatureGroup(name='🔥 Point Heatmap')
    recent_path_layer = folium.FeatureGroup(name='📱 Recent Path')
    county_info_layer = folium.FeatureGroup(name='ℹ️ County Information')
    
    # Add matched counties with color gradient based on point count
    if not matched.empty:
        # Important change: Add Choropleth directly to the map first, then add to layer
        choropleth = folium.Choropleth(
            geo_data=matched,
            name='Counties',
            data=matched,
            columns=['GEOID', 'point_count'],
            key_on='feature.properties.GEOID',
            fill_color='YlOrRd',
            fill_opacity=0.5,
            line_opacity=0.2,
            legend_name='Point Count',
            highlight=True
        )
        choropleth.add_to(m)  # First add to map
        county_layer = choropleth  # Use the choropleth as the county layer
        
        # Add tooltips as a separate GeoJson layer
        folium.GeoJson(
            matched,
            name='County Info',
            tooltip=folium.GeoJsonTooltip(
                fields=['NAME', 'point_count'],
                aliases=['County:', 'Points:'],
                localize=True
            ),
            style_function=lambda x: {'fillOpacity': 0, 'weight': 0}
        ).add_to(county_info_layer)
    
    # Add state borders
    folium.GeoJson(
        states.geometry,
        name='State Borders',
        style_function=lambda x: {
            'fillColor': 'transparent',
            'color': 'blue',
            'weight': 1.5,
            'opacity': 0.5
        }
    ).add_to(state_layer)
    
    # Always add point visualization (different methods depending on number of points)
    if points:
        # Create coordinates list for potential heatmap
        point_coords = [[p.y, p.x] for p in points]
        
        # Try to add heatmap if many points
        if len(points) > 100:
            try:
                # Import here to catch import errors
                from folium.plugins import HeatMap
                
                # Use only string keys in gradient to avoid camelize errors
                HeatMap(
                    point_coords,
                    radius=10,
                    blur=15,
                    gradient={'0.4': 'blue', '0.65': 'lime', '1.0': 'red'}
                ).add_to(points_heatmap_layer)
                logging.info("Added heatmap layer successfully")
            except (ImportError, AttributeError) as e:
                logging.warning(f"Could not add heatmap: {e}")
        
        # Add individual markers with clustering
        marker_cluster = MarkerCluster().add_to(points_cluster_layer)
        
        # Limit number of individual markers for performance
        max_markers = min(2000, len(points))
        step = max(1, len(points) // max_markers)
        
        for i in range(0, len(points), step):
            pt = points[i]
            folium.CircleMarker(
                location=[pt.y, pt.x],
                radius=3,
                color='blue',
                fill=True,
                fill_color='blue',
                fill_opacity=0.7,
                tooltip=f"Point {i}: {pt.y:.6f}, {pt.x:.6f}"
            ).add_to(marker_cluster)
        
        # If point_gdf has timestamp, add a time-based trail with the most recent 100 points
        if not point_gdf.empty and 'timestamp' in point_gdf.columns and len(point_gdf) > 10:
            try:
                # Convert timestamps to datetime if they're strings
                if point_gdf['timestamp'].dtype == 'object':
                    point_gdf['timestamp'] = pd.to_datetime(
                        point_gdf['timestamp'], 
                        errors='coerce'
                    )
                
                # Sort by timestamp and get the most recent points
                recent_points = point_gdf.sort_values('timestamp').tail(100)
                
                # Create a path line
                if len(recent_points) > 1:
                    path_coords = [[row.geometry.y, row.geometry.x] for _, row in recent_points.iterrows()]
                    folium.PolyLine(
                        path_coords,
                        color='green',
                        weight=4,
                        opacity=0.7,
                    ).add_to(recent_path_layer)
                    
                    # Add start and end markers
                    start_point = recent_points.iloc[0]
                    end_point = recent_points.iloc[-1]
                    
                    folium.Marker(
                        [start_point.geometry.y, start_point.geometry.x],
                        icon=folium.Icon(color='green', icon='play', prefix='fa'),
                        tooltip='Start'
                    ).add_to(recent_path_layer)
                    
                    folium.Marker(
                        [end_point.geometry.y, end_point.geometry.x],
                        icon=folium.Icon(color='red', icon='stop', prefix='fa'),
                        tooltip='End'
                    ).add_to(recent_path_layer)
            except Exception as e:
                logging.warning(f"Failed to create time-based path: {e}")
    
    # Add raw point layer if there aren't too many points (less than 1000)
    if points and len(points) < 1000:
        raw_points_layer = folium.FeatureGroup(name='🔍 Individual Points')
        for i, pt in enumerate(points):
            folium.CircleMarker(
                location=[pt.y, pt.x],
                radius=2,
                color='purple',
                fill=True,
                fill_color='purple',
                fill_opacity=0.7,
                tooltip=f"Point {i}: {pt.y:.6f}, {pt.x:.6f}"
            ).add_to(raw_points_layer)
        raw_points_layer.add_to(m)
    
    # Create a base layers group for the map types with proper attributions
    folium.TileLayer(
        'CartoDB positron',
        name='Light Map',
        attr='© OpenStreetMap contributors © CartoDB'
    ).add_to(m)
    
    folium.TileLayer(
        'CartoDB dark_matter',
        name='Dark Map',
        attr='© OpenStreetMap contributors © CartoDB'
    ).add_to(m)
    
    folium.TileLayer(
        'Stamen Terrain',
        name='Terrain',
        attr='Map tiles by Stamen Design, under CC BY 3.0. Data by OpenStreetMap, under ODbL.'
    ).add_to(m)
    
    # Add all feature groups to the map
    # Note: county_layer is now the choropleth itself and already added to the map
    county_info_layer.add_to(m)
    state_layer.add_to(m)
    points_cluster_layer.add_to(m)
    points_heatmap_layer.add_to(m)
    recent_path_layer.add_to(m)
    
    # Add coverage statistics layer
    stats_layer = folium.FeatureGroup(name='📊 Coverage Statistics')
    
    # Calculate statistics
    point_density = len(points) / len(matched) if not matched.empty and len(matched) > 0 else 0
    counties_covered_pct = len(matched) / len(counties) * 100 if not counties.empty else 0
    
    # Default values for bounds
    lat_range = 10
    lon_range = 10
    if not matched.empty:
        bounds = matched.total_bounds
        lat_range = bounds[3] - bounds[1]
        lon_range = bounds[2] - bounds[0]
    
    # Create a statistics box
    stats_html = f"""
    <div style="
        background-color: white;
        padding: 10px;
        border: 2px solid #444;
        border-radius: 10px;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
        font-family: Arial, sans-serif;
        font-size: 14px;
        max-width: 300px;
    ">
        <h4 style="margin-top:0;">📊 Coverage Statistics</h4>
        <table style="width:100%;">
            <tr><td>📍 Total Points:</td><td><b>{len(points)}</b></td></tr>
            <tr><td>🗺️ Counties Matched:</td><td><b>{len(matched)}</b> ({counties_covered_pct:.1f}%)</td></tr>
            <tr><td>🏛️ States Covered:</td><td><b>{len(state_names)}</b></td></tr>
            <tr><td>📊 Avg Points/County:</td><td><b>{point_density:.1f}</b></td></tr>
        </table>
        <hr style="margin: 5px 0;">
        <div style="font-size: 12px; color: #555;">
            States: {', '.join(state_names[:5]) + ('...' if len(state_names) > 5 else '')}
        </div>
    </div>
    """
    
    # Add the stats box as a custom marker with fixed position
    folium.Marker(
        location=[center[0] - lat_range/4, center[1] - lon_range/4],
        icon=folium.DivIcon(html=stats_html),
    ).add_to(stats_layer)
    
    stats_layer.add_to(m)
    
    # Add the layer control with separated overlays and base layers
    folium.LayerControl(
        position='topright',
        collapsed=False,
        autoZIndex=True
    ).add_to(m)
    
    # Add legend and instructions
    legend_html = """
    <div style="
        position: fixed;
        bottom: 10px;
        left: 10px;
        z-index: 9000;
        background-color: white;
        padding: 8px;
        border: 1px solid #888;
        border-radius: 5px;
        font-size: 12px;
    ">
        <b>Map Controls:</b><br>
        • Use layer control (top right) to toggle layers<br>
        • Click counties for details<br>
        • Scroll to zoom, drag to pan<br>
        • Toggle between different base maps
    </div>
    """
    m.get_root().html.add_child(Element(legend_html))
    
    # Save and minify HTML
    try:
        m.save(output_path)
        logging.info(f"Map saved to: {output_path}")
        
        # Attempt to minify the HTML
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                minified = htmlmin.minify(
                    f.read(),
                    remove_empty_space=True,
                    remove_all_empty_space=False,  # Complete removal can break some JS
                    remove_optional_attribute_quotes=False  # Can cause issues with some HTML
                )
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(minified)
            
            file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            logging.info(f"Minified map size: {file_size_mb:.2f} MB")
        except Exception as e:
            logging.warning(f"HTML minification failed: {e}")
    except Exception as e:
        logging.error(f"Failed to save map: {e}")
        raise
