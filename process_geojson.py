import json
import os

def process_geojson(input_path, output_path):
    """
    Reads a GeoJSON file, filters feature properties to keep only those
    starting with 'PTN_', and writes the result to a new file.
    """
    print(f"Starting to process {input_path}...")
    
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            print("Loading GeoJSON data into memory. This might take a moment...")
            data = json.load(f)
        
        print("Data loaded. Processing features...")
        
        original_feature_count = len(data.get('features', []))
        
        # Filter the properties for each feature
        for feature in data.get('features', []):
            if 'properties' in feature and isinstance(feature['properties'], dict):
                original_properties = feature['properties']
                new_properties = {
                    key: value for key, value in original_properties.items()
                    if key.startswith('PTN_')
                }
                feature['properties'] = new_properties
        
        print(f"Processed {original_feature_count} features.")
        
        # Write the modified data to the output file
        print(f"Writing processed data to {output_path}...")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
            
        print("Processing complete!")
        print(f"New file created at: {output_path}")

    except FileNotFoundError:
        print(f"Error: Input file not found at {input_path}")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {input_path}. The file might be corrupted.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    # Using absolute paths to avoid ambiguity
    input_file = r'C:\Users\Owner\Desktop\workspace_new\proj_j_bus-timelapse-theater\data\国土数値情報_将来推計人口250m_mesh_2024_38_GEOJSON\250m_mesh_2024_38.geojson'
    output_file = r'C:\Users\Owner\Desktop\workspace_new\proj_j_bus-timelapse-theater\data\国土数値情報_将来推計人口250m_mesh_2024_38_GEOJSON\250m_mesh_2024_38_processed.geojson'
    
    process_geojson(input_file, output_file)
