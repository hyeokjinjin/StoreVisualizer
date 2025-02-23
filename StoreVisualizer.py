from geopy.geocoders import Nominatim
from traffic_visibility import TrafficVisibility
# from SidewalkVisibility import SidewalkVisibility
from shapely.geometry import Point


def coordinates(address):
    print(f"Finding coordinates for: \"{address}\"")
    geolocator = Nominatim(user_agent="store_visualizer", timeout=10)
    location = geolocator.geocode(address)
    if location:
        print(f"Coordinates: ({location.latitude}, {location.longitude}).\n")
        return location.latitude, location.longitude
    else:
        raise ValueError("Address not found")


def main():
    address = "190 Bowery, New York, NY 10012"
    radius = 200
    
    lat, lon = coordinates(address)
    
    # Process traffic visibility
    tv = TrafficVisibility(lat, lon)
    tv.read_data("traffic_data_sample.csv")
    roads = tv.nearby_data(radius=radius)
    tv.fetch_obstacles(search_radius=radius)
    tv.generate_map(roads, "traffic_map.html")
    
    if roads is not None and not roads.empty:
        print("Truncating for segments with visible storefront...")
        visible = tv.filter_visible_segments(
            roads,
            Point(tv.store_longitude, tv.store_latitude),
            tv.obstacles
        )
        tv.generate_map(visible, "visible_traffic_map.html")
        print(f"Found {len(visible)} visible segments.")
    else:
        print("No nearby roads found")
    


if __name__ == "__main__":
    main()