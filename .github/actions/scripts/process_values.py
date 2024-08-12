import yaml
import os
import sys

def read_yaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return yaml.safe_load(file)

def write_yaml(data, file_path):
    with open(file_path, 'w', encoding='utf-8') as file:
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
        values = {
            'services': dict(default_values['services']),
            'versions': dict(default_values['versions'])
        }

        # Apply MSA-specific overrides
        for component, component_data in msa_data.items():
            if component == 'review':
                for service, version in component_data.items():
                    if service in values['services']:
                        values['services'][service]['tag'] = version
                        print(f"Overriding {service} for MSA {msa} with version {version}")

        # Output debug information before writing the file
        print(f"MSA {msa} values before writing to file: {values}")

        # Generate the MSA-specific YAML file
        msa_file_path = os.path.join(output_dir, f"{msa}.yaml")
        print(f"Writing to {msa_file_path}")
        write_yaml(values, msa_file_path)
        print(f"Generated {msa_file_path}")

if __name__ == "__main__":
    for i in range(1, len(sys.argv), 2):
        version_file_path = sys.argv[i]
        output_dir = sys.argv[i + 1]
        process_versions(version_file_path, output_dir)
