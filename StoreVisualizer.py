from geopy.geocoders import Nominatim
from traffic_visibility import TrafficVisibility
from sidewalk_visibility import SidewalkVisibility
from shapely.geometry import Point


def coordinates(address):
    print(f"Finding coordinates for: {address}")
    geolocator = Nominatim(user_agent="store_visualizer", timeout=10)
    location = geolocator.geocode(address)
    if location:
        return location.latitude, location.longitude
    else:
        raise ValueError("Address not found")


def main():
    address = "190 Bowery, New York, NY 10012"
    radius = 200
    pedestrian_radius = 50

    lat, lon = coordinates(address)

    # Process traffic visibility
    tv = TrafficVisibility(lat, lon)
    tv.read_data("traffic_data_sample.csv")
    roads = tv.nearby_data(radius=radius)
    tv.fetch_obstacles(search_radius=radius)
    tv.generate_map(roads, "traffic_map.html")

    if roads is not None and not roads.empty:
        visible = tv.filter_visible_segments(
            roads,
            Point(tv.store_longitude, tv.store_latitude),
            tv.obstacles
        )
        tv.generate_map(visible, "visible_traffic_map.html")
        print(f"Found {len(visible)} visible segments")
        
    else:
        print("No nearby roads found")

    # **Sidewalk Visibility Processing**
    print("\n--- Processing Sidewalk Visibility ---")
    sv = SidewalkVisibility(lat, lon, radius=pedestrian_radius)
    visibility_score = sv.calculate_visibility_score()

    print(f"Storefront Visibility Score (Sidewalk): {visibility_score}")
    

if __name__ == "__main__":
    main()
