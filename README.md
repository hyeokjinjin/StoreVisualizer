# Storefront Visibility and Impressions Estimator

## Overview
Hacklytics 2025 Entry for GrowthFactorAI Challenge

[DevPost Submission](https://devpost.com/software/storeview)

This project estimates the **total impressions** a storefront receives based on its visibility from nearby road segments and associated traffic data. Using provided traffic volume data and spatial analysis techniques, this solution generates a visibility score that can guide commercial realtors in evaluating prime storefront locations.

## Key Features
- Estimates **visibility scores** using spatial data and road geometry.
- Integrates traffic volume, direction of travel, and road classifications to improve accuracy.
- Computes **total impressions** by combining visibility scores with traffic data.
- Provides scalable functionality with OpenStreetMap (OSM) and Google Maps API integration.

## Methodology
The solution follows these steps:

1. **Data Preparation:**  
   - Load and preprocess the provided traffic dataset.  
   - Extract key features like `trips_volume`, `match_dir`, `segment_length_m`, and `geom`.

2. **Visibility Estimation:**  
   - Identify road segments within a defined visibility radius (e.g., 50-100 meters).  
   - Use spatial analysis tools (e.g., GeoPandas, Shapely) to calculate visibility scores.  
   - Account for factors like distance, angle of view, and potential obstructions.

3. **Impressions Calculation:**  
   - For each store location, combine visibility scores with corresponding traffic volume.  
   - Sum impressions from all relevant segments to compute the total score.

4. **Evaluation & Tuning:**  
   - Adjust parameters for optimal results.  
   - Validate against sample storefront locations.

## Data Sources
- **Traffic Data:** Provided dataset with road segments, traffic volume, and directional details.
- **Geospatial Data:** OpenStreetMap (OSM) API for road geometry and storefront locations.
- **Satellite Imagery:** (Optional) Google Maps API for enhanced visibility estimation.

## Dependencies
- Python 3.x
- Geopandas
- Shapely
- Folium (for visualization)
- Requests (for API integration)
- Pandas

## Results
The solution outputs a visibility score for each storefront, which reflects its estimated total impressions based on nearby traffic patterns and visibility conditions.

## Future Enhancements
- Integrate pedestrian traffic data for improved accuracy.
- Incorporate seasonal and time-of-day effects to refine impressions estimates.
- Develop a user interface for intuitive data visualization.

## Contributors
- Hyeokjin Jin
- Lucas Chen
- Krystal Wu


