from geopy.geocoders import Nominatim
import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
from shapely.geometry import Point, LineString
import folium
import osmnx as ox

def is_point_visible(storefront_proj, sample_point_proj, obstacles_proj):
    """Check visibility with buffer tolerance and simplified intersection."""
    los = LineString([storefront_proj, sample_point_proj])
    return not any(los.intersects(obs.buffer(0.1)) for obs in obstacles_proj.geometry)  # 10cm buffer for tolerance

def filter_visible_segments(nearby_segments, storefront, obstacles, num_samples=50):
    """Improved visibility check with increased sampling and obstacle exclusion."""
    projected_crs = "EPSG:3857"
    
    # Convert to projected CRS
    storefront_proj = gpd.GeoSeries([storefront], crs="EPSG:4326").to_crs(projected_crs).iloc[0]
    obstacles_proj = obstacles.to_crs(projected_crs)
    nearby_segments_proj = nearby_segments.to_crs(projected_crs)

    visible_segments = []
    for seg in nearby_segments_proj.geometry:
        # Check segment endpoints first
        for point in [seg.coords[0], seg.coords[-1]]:
            if is_point_visible(storefront_proj, Point(point), obstacles_proj):
                visible_segments.append(seg)
                break
        else:  # Only check interior points if endpoints aren't visible
            for i in range(num_samples):
                sample_point = seg.interpolate(i / (num_samples - 1), normalized=True)
                if is_point_visible(storefront_proj, sample_point, obstacles_proj):
                    visible_segments.append(seg)
                    break
    
    return gpd.GeoDataFrame(geometry=visible_segments, crs=projected_crs).to_crs("EPSG:4326")

class StoreVisibility:
    def __init__(self):
        self.store_latitude, self.store_longitude = None, None
        self.gdf = None
        self.obstacles = gpd.GeoDataFrame()

    def get_coordinates(self, address):
        geolocator = Nominatim(user_agent="store_visualizer", timeout=10)
        location = geolocator.geocode(address)
        if location:
            self.store_latitude, self.store_longitude = location.latitude, location.longitude
            return self.store_latitude, self.store_longitude
        else:
            raise ValueError("Address not found")

    def fetch_obstacles(self, search_radius=200):
        """Fetch obstacles while excluding the store's own building."""
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

    def read_data(self, csv):
        """Load and validate road data."""
        df = pd.read_csv(csv)
        if "geom" not in df.columns:
            raise ValueError("CSV missing 'geom' column with WKT geometries")
        
        df["geometry"] = df["geom"].apply(loads)
        self.gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326").drop(columns=["geom"])

    def nearby_data(self, radius):
        """Get nearby roads with accurate buffer calculation."""
        store_point = Point(self.store_longitude, self.store_latitude)
        buffered = gpd.GeoSeries([store_point], crs="EPSG:4326").to_crs("EPSG:3857").buffer(radius)
        roads_proj = self.gdf.to_crs("EPSG:3857")
        nearby = roads_proj[roads_proj.intersects(buffered[0])]
        return nearby.to_crs("EPSG:4326")

    def generate_map(self, segments, filename):
        """Create map with layers for debugging."""
        m = folium.Map(location=[self.store_latitude, self.store_longitude], zoom_start=17)
        
        # Add store location
        folium.Marker(
            [self.store_latitude, self.store_longitude],
            icon=folium.Icon(color="red", icon="home")
        ).add_to(m)
        
        # Add obstacles
        if not self.obstacles.empty:
            folium.GeoJson(
                self.obstacles,
                style_function=lambda x: {'color': 'orange', 'fillOpacity': 0.3}
            ).add_to(m)
        
        # Add road segments
        if segments is not None and not segments.empty:
            folium.GeoJson(
                segments,
                style_function=lambda x: {'color': 'blue', 'weight': 2}
            ).add_to(m)
        
        m.save(filename)
        print(f"Debug map saved to {filename}")

# Usage example
if __name__ == "__main__":
    sv = StoreVisibility()
    sv.get_coordinates("190 Bowery, New York, NY 10012")
    
    # Create debug map before filtering
    sv.fetch_obstacles(search_radius=200)
    sv.read_data("traffic_data_sample.csv")
    roads = sv.nearby_data(radius=200)
    sv.generate_map(roads, "map.html")
    
    if roads is not None and not roads.empty:
        visible = filter_visible_segments(
            roads,
            Point(sv.store_longitude, sv.store_latitude),
            sv.obstacles
        )
        sv.generate_map(visible, "visible_map.html")
        print(f"Found {len(visible)} visible segments")
    else:
        print("No nearby roads found")