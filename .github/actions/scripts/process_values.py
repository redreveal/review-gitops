import yaml
import os
import sys

def read_yaml(file_path):
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def write_yaml(data, file_path):
    with open(file_path, 'w') as file:
        yaml.dump(data, file, default_flow_style=False)

def process_versions(version_file_path, output_dir):
    versions_data = read_yaml(version_file_path)

    # Extract defaults
    defaults = versions_data.get('defaults', {})
    processing_default = defaults.get('processing', {}).get('default', 'default_version')
    review_default = defaults.get('review', {}).get('default', 'default_version')
    reveal_ai_default = defaults.get('reveal_ai', {}).get('default', 'default_version')
    review_services = defaults.get('review', {}).get('services', {})

    # Create default values
    default_values = {
        'services': {},
        'versions': {
            'default_review': review_default,
            'default_reveal_ai': reveal_ai_default,
            'default_processing': processing_default
        }
    }

    for service, version in review_services.items():
        default_values['services'][service] = {'tag': version}

    # Write the default values.yaml
    default_values_path = os.path.join(output_dir, 'default_values.yaml')
    write_yaml(default_values, default_values_path)
    print(f"Generated {default_values_path}")

    # Process each MSA
    msas = versions_data.get('msas', {})
    for msa, msa_data in msas.items():
        # Start with a deep copy of the default values
        values = {
            'services': {k: v.copy() for k, v in default_values['services'].items()},
            'versions': default_values['versions'].copy()
        }

        # Apply MSA-specific overrides
        for component, component_data in msa_data.items():
            if component == 'review':
                for service, version in component_data.items():
                    if service in values['services']:
                        values['services'][service]['tag'] = version

        # Output the MSA-specific file
        msa_str = str(msa)
        output_file_path = os.path.join(output_dir, f'{msa_str}.yaml')
        write_yaml(values, output_file_path)
        print(f"Generated {output_file_path}")

if __name__ == "__main__":
    for i in range(1, len(sys.argv), 2):
        version_file_path = sys.argv[i]
        output_dir = sys.argv[i + 1]
        process_versions(version_file_path, output_dir)
