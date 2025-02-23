from geopy.geocoders import Nominatim
from traffic_visibility import TrafficVisibility
from sidewalk_visibility import SidewalkVisibility
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


def extract_state(address):
    parts = address.split()
    for part in parts:
        if len(part) == 2 and part.isupper():
            state = part
            break
    return state


def main():
    address = input("Enter the store address: ").strip()
    if not address:
        print("Error: No address provided.")
        return

    radius = 200
    pedestrian_radius = 50

    try:
        print("--- Address Conversion ---")
        lat, lon = coordinates(address)

        state = extract_state(address)

        print("\n--- Processing Traffic Visibility ---")
        tv = TrafficVisibility(lat, lon)
        tv.read_data("traffic_data_sample.csv", state)
        roads = tv.nearby_data(radius=radius)
        tv.fetch_obstacles(search_radius=radius)

        tv.fetch_seasonal_visibility()

        tv.generate_map(roads, "traffic_map.html")

        if roads is not None and not roads.empty:
            print("Truncating for segments with visible storefront...")
            visible = tv.filter_visible_segments(
                roads,
                Point(tv.store_longitude, tv.store_latitude),
                tv.obstacles
            )
            tv.generate_map(visible, "visible_traffic_map.html")
            print(visible)

            print(f"Found {len(visible)} visible segments.")
            print("Car traffic value: ", tv.calculate_car_traffic(visible), "\n")
        else:
            print("No nearby roads found")    

        # **Sidewalk Visibility Processing**
        print("\n--- Processing Sidewalk Visibility ---")
        sv = SidewalkVisibility(lat, lon)
        visibility_score = sv.calculate_visibility_score(radius)

        print(f"Storefront Visibility Score (Sidewalk): {visibility_score}")

        print("\nTotal Visibility Score: {:.2f}".format(visibility_score + tv.calculate_car_traffic(visible)))

    except ValueError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
