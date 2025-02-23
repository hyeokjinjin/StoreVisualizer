from geopy.geocoders import Nominatim
import datetime
import requests
import time
import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
from shapely.geometry import Point, LineString
import folium
import osmnx as ox

# Replace with your actual API key
VISUAL_CROSSING_API_KEY = "EQ5E8X5XN29VP4NBFNMPYHZSP"

def get_season(date):
    """Determine the season based on the month."""
    month = date.month
    if 3 <= month < 6:
        return "Spring"
    elif 6 <= month < 9:
        return "Summer"
    elif 9 <= month < 12:
        return "Fall"
    else:
        return "Winter"


def fetch_historical_visibility(lat, lon, years=3):
    """Fetch historical visibility data and calculate seasonal averages."""
    end_year = datetime.datetime.now().year
    start_year = end_year - years
    visibility_data = []

    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/last{years}years?unitGroup=metric&include=days&key={VISUAL_CROSSING_API_KEY}&contentType=json"
    response = requests.get(url)

    if response.status_code == 429:
        print("Rate limit exceeded. Waiting 60 seconds before retrying...")
        time.sleep(60)  # Wait before retrying
        response = requests.get(url)

    if response.status_code != 200:
        print(f"Error fetching visibility data: {response.status_code}. Returning default values.")
        return {"Spring": None, "Summer": None, "Fall": None, "Winter": None}

    data = response.json()
    if "days" not in data:
        print(f"Unexpected API response structure: {data}")
        return {}

    for day in data["days"]:
        try:
            date = datetime.datetime.strptime(day["datetime"], "%Y-%m-%d")
            season = get_season(date)
            visibility = day.get("visibility", None)

            if visibility is not None:
                visibility_data.append({"season": season, "visibility": visibility})
        except Exception as e:
            print(f"Error processing data for {day}: {e}")
            continue

    df = pd.DataFrame(visibility_data)

    if df.empty or "season" not in df.columns:
        print("No valid visibility data collected.")
        return {}

    seasonal_avg = df.groupby("season")["visibility"].mean().to_dict()
    return seasonal_avg


class StoreVisibility:
    def __init__(self):
        self.store_latitude, self.store_longitude = None, None
        self.gdf = None
        self.obstacles = gpd.GeoDataFrame()


    # Grab address's coordinate given the address
    # Utilizes OSM Nominatim API
    def get_coordinates(self, address):
        print(f"Finding coordinates for: {address}")
        geolocator = Nominatim(user_agent="store_visualizer", timeout=10)
        location = geolocator.geocode(address)
        if location:
            self.store_latitude, self.store_longitude = location.latitude, location.longitude
            return self.store_latitude, self.store_longitude
        else:
            raise ValueError("Address not found")


    def read_data(self, csv, target_state):
        """Read traffic data, filter by state, and convert geometry."""
        print(f"Reading data and filtering for state: {target_state}...")

        df = pd.read_csv(csv)

        # Ensure required columns exist
        if "state_code" not in df.columns or "geom" not in df.columns:
            raise ValueError("CSV must contain 'state_code' and 'geom' columns.")

        # Filter by state first
        df = df[df["state_code"] == target_state]

        if df.empty:
            print(f"No data found for state: {target_state}.")
            return

        # Convert 'geom' column to geometries
        df["geometry"] = df["geom"].apply(loads)

        # Create GeoDataFrame and remove original 'geom' column
        self.gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326").drop(columns=["geom"])

        print(f"Filtered dataset contains {len(self.gdf)} line segments in {target_state}.")
        return self.gdf 

    def extract_state(self, address):
        parts = address.split()
        for part in parts:
            if len(part) == 2 and part.isupper():
                state = part
                break

        return state


    # Find all nearby segments given a point and radius
    def nearby_data(self, radius):
        if self.store_latitude is None or self.store_longitude is None or self.gdf is None:
            raise ValueError("Ensure prior data is retrieved")
        
        print("Finding all nearby line segments...")
        
        # Create a store location point and convert into 
        store_location = Point(self.store_longitude, self.store_latitude)
        store_location = gpd.GeoSeries([store_location], crs="EPSG:4326").to_crs(epsg=3857).iloc[0]
        
        # Convert GDF and find nearby segments
        gdf_3857 = self.gdf.to_crs(epsg=3857)
        nearby_segments = gdf_3857[gdf_3857.geometry.distance(store_location) <= radius]
        print(f"Found {len(nearby_segments)} nearby road segments within {radius}m.")
        return nearby_segments.to_crs(epsg=4326)  # Convert back to WGS84


    def fetch_obstacles(self, search_radius):
        if not self.store_latitude or not self.store_longitude:
            raise ValueError("Store coordinates not set")
        
        # Get store building
        tags = {'building': True}
        store_point = Point(self.store_longitude, self.store_latitude)
        
        # Fetch obstacles and explode multipolygons
        self.obstacles = ox.features_from_point(
            (self.store_latitude, self.store_longitude),
            tags=tags,
            dist=search_radius
        ).explode(index_parts=True).reset_index(drop=True)
        
        # Identify and remove store's own building
        store_building_mask = self.obstacles.intersects(store_point)
        self.obstacles = self.obstacles[~store_building_mask].copy()
        print(f"Filtered {store_building_mask.sum()} store buildings from obstacles")

    def calculate_car_traffic(self, visible_segments):
        """Calculate car traffic value for each visible segment."""
        if visible_segments is None or visible_segments.empty:
            print("No visible road segments found.")
            return 0

        # Ensure required columns exist
        if "trips_volume" not in self.gdf.columns or "trips_sample_count" not in self.gdf.columns:
            raise ValueError("CSV must contain 'trips_volume' and 'trips_sample_count' columns.")

        # Perform spatial join to match visible road segments with the traffic dataset
        matched_segments = gpd.sjoin(self.gdf, visible_segments, predicate="intersects", how="inner")

        if matched_segments.empty:
            print("No matching traffic data found for visible road segments.")
            return 0

        # Replace 0 sample counts to prevent division by zero
        matched_segments["trips_sample_count"] = matched_segments["trips_sample_count"].replace(0, 1e-6)

        # Compute car traffic per segment safely
        matched_segments["car_traffic"] = (matched_segments["trips_volume"] / matched_segments["trips_sample_count"]) * 1.4

        # Sum up total traffic
        total_traffic = matched_segments["car_traffic"].sum()
        print(f"Total Car Traffic Value for Storefront: {total_traffic:.2f}")

        return total_traffic

    def fetch_seasonal_visibility(self):
        """Fetch and store seasonal visibility averages."""
        if self.store_latitude is None or self.store_longitude is None:
            raise ValueError("Store coordinates not set")

        self.seasonal_visibility = fetch_historical_visibility(self.store_latitude, self.store_longitude)
        print("Seasonal Visibility:", self.seasonal_visibility)

    # Check visibility with buffer and intersection
    def is_point_visible(self, storefront_proj, sample_point_proj, obstacles_proj):
        los = LineString([storefront_proj, sample_point_proj])
        return not any(los.intersects(obs.buffer(0.1)) for obs in obstacles_proj.geometry)  # 10cm buffer for tolerance


    # Filter only visible segments
    def filter_visible_segments(self, nearby_segments, storefront, obstacles, num_samples=50):
        projected_crs = "EPSG:3857"
        
        # Convert to projected CRS
        storefront_proj = gpd.GeoSeries([storefront], crs="EPSG:4326").to_crs(projected_crs).iloc[0]
        obstacles_proj = obstacles.to_crs(projected_crs)
        nearby_segments_proj = nearby_segments.to_crs(projected_crs)

        visible_segments = []
        for seg in nearby_segments_proj.geometry:
            # Check segment endpoints first
            for point in [seg.coords[0], seg.coords[-1]]:
                if self.is_point_visible(storefront_proj, Point(point), obstacles_proj):
                    visible_segments.append(seg)
                    break
            else:  # Only check interior points if endpoints aren't visible
                for i in range(num_samples):
                    sample_point = seg.interpolate(i / (num_samples - 1), normalized=True)
                    if self.is_point_visible(storefront_proj, sample_point, obstacles_proj):
                        visible_segments.append(seg)
                        break
        
        return gpd.GeoDataFrame(geometry=visible_segments, crs=projected_crs).to_crs("EPSG:4326")


    def generate_map(self, nearby_segments, filename):
        # Check if store coordinates exist
        if self.store_latitude is None or self.store_longitude is None:
            raise ValueError("Error: Store coordinates not set. Run get_coordinates() first.")
        
        if nearby_segments is None or nearby_segments.empty:
            raise ValueError("No nearby segments found.")
            
        # Create a map centered at the store's coordinates
        store_map = folium.Map(location=[self.store_latitude, self.store_longitude], zoom_start=14)
        
        # Add store location
        folium.Marker(
            [self.store_latitude, self.store_longitude],
            popup="Store Location",
            icon=folium.Icon(color="red", icon="home")
        ).add_to(store_map)
        
        # Add obstacles
        if not self.obstacles.empty:
            folium.GeoJson(
                self.obstacles,
                style_function=lambda x: {'color': 'orange', 'fillOpacity': 0.3}
            ).add_to(store_map)
        
        # Add nearby road segments
        for i, row in nearby_segments.iterrows():
            if not isinstance(row["geometry"], LineString):
                print(f"Skipping invalid geometry at index {i}: {row['geometry']}")
                continue
            
            # Extract line coordinates
            line_coords = [(lat, lon) for lon, lat in row["geometry"].coords]  # Reverse to match folium format
            
            # Debugging print
            # print(f"Adding segment {i}: {line_coords}")
            
            # Draw road segment
            folium.PolyLine(
                line_coords, 
                color="blue", 
                weight=5,
                popup=row.get("segment_name", f"Road Segment {i}")
            ).add_to(store_map)
            
            # Add markers at start and end of the road segment
            folium.Marker(
                line_coords[0],  # Start point
                icon=folium.Icon(color="green", icon="play"),
                popup=f"Start of segment {i}"
            ).add_to(store_map)
            
            folium.Marker(
                line_coords[-1],  # End point
                icon=folium.Icon(color="blue", icon="stop"),
                popup=f"End of segment {i}"
            ).add_to(store_map)
        
        store_map.save(filename)
        print(f"Debug map saved to {filename}")

# Usage example
if __name__ == "__main__":
    sv = StoreVisibility()
    address = "609 8th Ave, New York, NY 10018"
    state = sv.extract_state(address)
    coordinates = sv.get_coordinates(address)
    print("Coordinates:", coordinates)
    sv.fetch_seasonal_visibility()
    
    # Create debug map before filtering
    sv.read_data("traffic_data_sample.csv", state)
    roads = sv.nearby_data(radius=200)
    sv.fetch_obstacles(search_radius=200)
    sv.generate_map(roads, "map.html")
    
    if roads is not None and not roads.empty:
        visible = sv.filter_visible_segments(
            roads,
            Point(sv.store_longitude, sv.store_latitude),
            sv.obstacles
        )
        sv.generate_map(visible, "visible_map.html")
        print(f"Found {len(visible)} visible segments")
        traffic_value = sv.calculate_car_traffic(visible)
        print(traffic_value)
    else:
        print("No nearby roads found")