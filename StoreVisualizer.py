from geopy.geocoders import Nominatim
import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
from shapely.geometry import Point
from shapely.geometry import LineString
import folium

class StoreVisibility:
    def __init__(self):
        self.store_latitude, self.store_longitude = None, None
        self.gdf = None


    # Grab address's coordinate given the address
    # Utilizes OSM Nominatim API
    def get_coordinates(self, address):
        geolocator = Nominatim(user_agent="plsno", timeout=10)
        location = geolocator.geocode(address)
        if location:
            self.store_latitude, self.store_longitude = location.latitude, location.longitude
            return self.store_latitude, self.store_longitude
        else:
            print("Address not found")
            return None


    # Convert data to coordinates and create a column "geom"
    def read_data(self, csv):
        df = pd.read_csv(csv)
        df["geometry"] = df["geom"].apply(loads)
        self.gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")
        self.gdf = self.gdf.drop(columns=["geom"])
        print("Geom", self.gdf.geometry.head())


    # Find all nearby segments given a point and radius
    def nearby_data(self, radius):
        if self.store_latitude is None or self.store_longitude is None or self.gdf is None:
            print("Ensure prior data is retrieved")
            return None
        
        # Create a store location point and convert into 
        store_location = Point(self.store_longitude, self.store_latitude)
        store_location = gpd.GeoSeries([store_location], crs="EPSG:4326").to_crs(epsg=3857).iloc[0]
        
        # Convert GDF and find nearby segments
        gdf_3857 = self.gdf.to_crs(epsg=3857)
        nearby_segments = gdf_3857[gdf_3857.geometry.distance(store_location) <= radius]
        print(f"Found {len(nearby_segments)} nearby road segments within {radius}m.")
        return nearby_segments.to_crs(epsg=4326)  # Convert back to WGS84


    # Visualize Coordinates and Line Segments   
    def show_map(self, nearby_segments):
        # Check if store coordinates exist
        if self.store_latitude is None or self.store_longitude is None:
            print("Error: Store coordinates not set. Run get_coordinates() first.")
            return

        if nearby_segments is None or nearby_segments.empty:
            print("No nearby segments found.")
            return

        # Create a map centered at the store's coordinates
        store_map = folium.Map(location=[self.store_latitude, self.store_longitude], zoom_start=14)

        # Add store marker
        folium.Marker(
            [self.store_latitude, self.store_longitude], 
            popup="Store Location", 
            icon=folium.Icon(color="red")
        ).add_to(store_map)

        # Add nearby road segments
        for i, row in nearby_segments.iterrows():
            if not isinstance(row["geometry"], LineString):
                print(f"Skipping invalid geometry at index {i}: {row['geometry']}")
                continue

            # Extract line coordinates
            line_coords = [(lat, lon) for lon, lat in row["geometry"].coords]  # Reverse to match folium format

            # Debugging print
            print(f"Adding segment {i}: {line_coords}")

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

        # Save and show the map
        store_map.save("map.html")
        import webbrowser
        webbrowser.open("map.html")


# Example usage
geo = StoreVisibility()
coordinates = geo.get_coordinates("500 Broadway, New York, NY 10012")
print("Coordinates:", coordinates)

geo.read_data("traffic_data_sample.csv")
nearby_roads = geo.nearby_data(radius=200)
print("Nearby Roads:\n", nearby_roads)

geo.show_map(nearby_roads)