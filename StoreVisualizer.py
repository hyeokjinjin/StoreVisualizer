from geopy.geocoders import Nominatim
import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
from shapely.geometry import Point, LineString
import folium
import osmnx as ox

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


    # Convert data to coordinates and create a column "geom"
    def read_data(self, csv):
        print("Reading Data...")
        df = pd.read_csv(csv)
        df["geometry"] = df["geom"].apply(loads)
        self.gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326").drop(columns=["geom"])
        print(f"Found {len(self.gdf)} line segments in dataset.")


    # Find all nearby segments given a point and radius
    def nearby_data(self, radius):
        if self.store_latitude is None or self.store_longitude is None or self.gdf is None:
            raise ValueError("Coordinates or GeoDataFrame not defined.")
        
        print("Finding all nearby line segments...")
        
        # Create a store location point and convert into 
        store_location = Point(self.store_longitude, self.store_latitude)
        store_location = gpd.GeoSeries([store_location], crs="EPSG:4326").to_crs(epsg=3857).iloc[0]
        
        # Convert GDF and find nearby segments
        gdf_3857 = self.gdf.to_crs(epsg=3857)
        nearby_segments = gdf_3857[gdf_3857.geometry.distance(store_location) <= radius]
        print(f"Found {len(nearby_segments)} nearby road segments within {radius}m.")
        return nearby_segments.to_crs(epsg=4326)  # Convert back to WGS84


    # Find all nearby obstacles given the store coordinates and radius
    def get_obstacles(self, search_radius):
        if not self.store_latitude or not self.store_longitude:
            raise ValueError("Coordinates not defined.")
        
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


    # Check visibility with buffer tolerance and simplified intersection
    def is_point_visible(self, storefront_proj, sample_point_proj, obstacles_proj):
        los = LineString([storefront_proj, sample_point_proj])
        
        # 10cm buffer for tolerance
        return not any(los.intersects(obs.buffer(0.1)) for obs in obstacles_proj.geometry)


    # Filtering visible segments given the store
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
            raise ValueError("Coordinates not defined.")
        
        if nearby_segments is None or nearby_segments.empty:
            raise ValueError("No nearby segments found.")
        
        store_map = folium.Map(location=[self.store_latitude, self.store_longitude], zoom_start=15)
        
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



if __name__ == "__main__":
    sv = StoreVisibility()
    print("Coordinates", sv.get_coordinates("190 Bowery, New York, NY 10012"))
    
    # Create debug map before filtering
    sv.read_data("traffic_data_sample.csv")
    roads = sv.nearby_data(radius=200)
    sv.get_obstacles(search_radius=200)
    sv.generate_map(roads, "map.html")
    
    if roads is not None and not roads.empty:
        visible = sv.filter_visible_segments(
            roads,
            Point(sv.store_longitude, sv.store_latitude),
            sv.obstacles
        )
        sv.generate_map(visible, "visible_map.html")
        print(f"Found {len(visible)} visible segments")
    else:
        print("No nearby roads found")