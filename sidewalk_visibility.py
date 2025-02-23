import requests
import geopandas as gpd
from shapely.geometry import Point, LineString
import osmnx as ox

class SidewalkVisibility:
    def __init__(self, lat, lon, radius=100):
        self.lat = lat
        self.lon = lon
        self.radius = radius
        self.obstacles = gpd.GeoDataFrame()

    def fetch_street_segments(self):
        """Fetch pedestrian and footway street segments dynamically from OpenStreetMap."""
        overpass_url = "http://overpass-api.de/api/interpreter"
        query = f"""
        [out:json];
        way["highway"~"footway|pedestrian"](around:{self.radius},{self.lat},{self.lon});
        out geom;
        """

        response = requests.get(overpass_url, params={"data": query})
        if response.status_code == 200:
            data = response.json()
            segments = []

            for element in data["elements"]:
                if "geometry" in element:
                    coords = [(node["lon"], node["lat"]) for node in element["geometry"]]
                    segments.append(LineString(coords))

            # print(f"DEBUG: Found {len(segments)} sidewalk segments from Overpass API.")
            return gpd.GeoDataFrame(geometry=segments, crs="EPSG:4326")

        # print("DEBUG: Overpass API request failed.")
        return gpd.GeoDataFrame()

    def fetch_obstacles(self):
        """Fetch obstacles (buildings) that might block visibility."""
        tags = {'building': True}
        store_point = Point(self.lon, self.lat)
        
        self.obstacles = ox.features_from_point(
            (self.lat, self.lon), tags=tags, dist=self.radius
        ).explode(index_parts=True).reset_index(drop=True)
        
        # Exclude the building that contains the store
        store_building_mask = self.obstacles.intersects(store_point)
        self.obstacles = self.obstacles[~store_building_mask].copy()

        # print(f"DEBUG: Found {len(self.obstacles)} obstacle buildings after removing store.")



    def is_segment_visible(self, segment, store_location):
        """Determine if a segment is visible if at least part of it is unobstructed."""
        projected_crs = "EPSG:3857"
        
        # Convert to projected coordinates
        store_proj = gpd.GeoSeries([store_location], crs="EPSG:4326").to_crs(projected_crs).iloc[0]
        obstacles_proj = self.obstacles.to_crs(projected_crs)

        # Convert segment to GeoSeries before transformation
        segment_gs = gpd.GeoSeries([segment], crs="EPSG:4326").to_crs(projected_crs)
        segment_proj = segment_gs.iloc[0]  # Extract transformed LineString

        num_samples = 50
        visible_points = []
        total_checked = 0
        total_blocked = 0

        for i in range(num_samples + 1):
            sample_point = segment_proj.interpolate(i / num_samples, normalized=True)
            line_of_sight = LineString([store_proj, sample_point])

            blocking_obstacles = [obs for obs in obstacles_proj.geometry if line_of_sight.intersects(obs.buffer(0.5))]

            if blocking_obstacles:
                total_blocked += 1
                # print(f"DEBUG: Point {i} is blocked by {len(blocking_obstacles)} obstacles.")
            else:
                visible_points.append(sample_point)

            total_checked += 1

        # Debug logging
        # print(f"DEBUG: Checked {total_checked} points on segment. Blocked: {total_blocked}, Unblocked: {len(visible_points)}")

        if len(visible_points) > 0:
            # print(f"DEBUG: Segment is partially visible! Keeping {len(visible_points)} points.")
            return LineString(visible_points)  # Return only the visible portion
        
        # print("DEBUG: Segment is completely blocked. Trying again with relaxed rules...")

        # SECOND PASS: If segment is fully blocked, try removing the buffer
        for i in range(num_samples + 1):
            sample_point = segment_proj.interpolate(i / num_samples, normalized=True)
            line_of_sight = LineString([store_proj, sample_point])

            if not any(line_of_sight.intersects(obs) for obs in obstacles_proj.geometry):  # No buffer this time
                visible_points.append(sample_point)

        if len(visible_points) > 0:
            # print(f"DEBUG: Segment was recoverable with relaxed filtering. Keeping {len(visible_points)} points.")
            return LineString(visible_points)

        # print("DEBUG: Segment remains fully blocked after relaxed check.")
        return None




    def fetch_pedestrian_density(self, lat, lon):
        """Fetch pedestrian density estimate based on nearby amenities."""
        overpass_url = "http://overpass-api.de/api/interpreter"
        query = f"""
        [out:json];
        (
            node["highway"="footway"](around:50,{lat},{lon});
            node["highway"="pedestrian"](around:50,{lat},{lon});
            node["amenity"~"bench|cafe|restaurant|fast_food|bus_stop"](around:50,{lat},{lon});
        );
        out body;
        """

        response = requests.get(overpass_url, params={"data": query})
        if response.status_code == 200:
            data = response.json()
            node_count = len(data["elements"]) if "elements" in data else 0
            # print(f"DEBUG: Found {node_count} pedestrian-related elements at ({lat}, {lon})")
            return node_count

        # print("DEBUG: Failed to fetch pedestrian density.")
        return 0

    def calculate_visibility_score(self):
        """Calculate visibility score by multiplying visible segment length with pedestrian density."""
        # print("\n--- Starting Visibility Calculation ---")
        self.fetch_obstacles()
        store_location = Point(self.lon, self.lat)
        street_segments = self.fetch_street_segments()

        if street_segments.empty:
            # print("DEBUG: No sidewalk segments found near store.")
            return 0  # No pedestrian streets nearby

        total_visibility_score = 0
        visible_segment_count = 0

        for segment in street_segments.geometry:
            visible_segment = self.is_segment_visible(segment, store_location)
            if visible_segment:  # Now, at least one point being visible counts the segment
                visible_segment_count += 1
                segment_length = visible_segment.length
                pedestrian_density = self.fetch_pedestrian_density(self.lat, self.lon)

                # print(f"DEBUG: Visible segment length: {segment_length}, Pedestrian density: {pedestrian_density}")

                total_visibility_score += (segment_length * pedestrian_density) / 10 # Normalize by 10 for scaling

        # print(f"DEBUG: Total visible segments: {visible_segment_count}")
        # print(f"DEBUG: Final visibility score: {total_visibility_score}")

        return round(total_visibility_score, 2)

