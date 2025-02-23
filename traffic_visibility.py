from geopy.geocoders import Nominatim
import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
from shapely.geometry import Point, LineString
import folium
import osmnx as ox


class TrafficVisibility:
    def __init__(self, lat, lon):
        self.store_latitude, self.store_longitude = lat, lon
        self.gdf = None
        self.obstacles = gpd.GeoDataFrame()


    # Convert data to coordinates and create a column "geom"
    def read_data(self, csv):
        print("Reading data...")
        df = pd.read_csv(csv)
        
        if "geom" not in df.columns:
            raise ValueError("CSV missing 'geom'")
        
        df["geometry"] = df["geom"].apply(loads)
        self.gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")
        self.gdf = self.gdf.drop(columns=["geom"])
        print(f"Found {len(self.gdf)} line segments in the dataset.")


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

        truncated_segments = []
        for seg in nearby_segments_proj.geometry:
            visible_points = []
            
            # Sample points along the segment
            for i in range(num_samples + 1):
                sample_point = seg.interpolate(i / num_samples, normalized=True)
                if self.is_point_visible(storefront_proj, sample_point, obstacles_proj):
                    visible_points.append(sample_point)
            
            # If there are visible points, form a truncated segment
            if len(visible_points) > 1:
                truncated_segments.append(LineString(visible_points))
        
        return gpd.GeoDataFrame(geometry=truncated_segments, crs=projected_crs).to_crs("EPSG:4326")


    def generate_map(self, nearby_segments, filename):
        # Check if store coordinates exist
        if self.store_latitude is None or self.store_longitude is None:
            raise ValueError("Error: Store coordinates not set. Run get_coordinates() first.")
            
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
        if nearby_segments is not None and not nearby_segments.empty:
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