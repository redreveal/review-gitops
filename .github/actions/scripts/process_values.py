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

    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Initialize the default values structure
    default_values = {'services': {}, 'versions': {}}

    # Process defaults for each component
    for component, component_data in versions_data.get('defaults', {}).items():
        default_version = component_data.get('default', 'default_version')
        default_values['versions'][f"default_{component}"] = default_version

        for service, version in component_data.get('services', {}).items():
            default_values['services'][service] = {'tag': version}

    # Write the default values.yaml which all non-overridden MSAs will be symlinked to
    default_values_path = os.path.join(output_dir, 'default_values.yaml')
    write_yaml(default_values, default_values_path)
    print(f"Generated {default_values_path}")

    # Process each MSA that has some overridden values
    for msa, msa_data in versions_data.get('msas', {}).items():
        # Start with the defaults
        msa_values = {
            'services': dict(default_values['services']),
            'versions': dict(default_values['versions'])
        }

        # Apply MSA-specific overrides for each component
        for component, component_data in msa_data.items():
            # Override component version if specified at the MSA level
            component_key = f"default_{component}"
            if 'default' in component_data:
                msa_values['versions'][component_key] = component_data['default']
                print(f"Overriding {component_key} for MSA {msa} with version {component_data['default']}")

            # Override specific service versions if specified at the MSA level
            for service, version in component_data.get('services', {}).items():
                if service in msa_values['services']:
                    msa_values['services'][service]['tag'] = version
                    print(f"Overriding {service} for MSA {msa} with version {version}")

        # Write MSA-specific YAML file
        msa_file_path = os.path.join(output_dir, f"{msa}.yaml")
        write_yaml(msa_values, msa_file_path)
        print(f"Generated {msa_file_path}")

if __name__ == "__main__":
    for i in range(1, len(sys.argv), 2):
        version_file_path = sys.argv[i]
        output_dir = sys.argv[i + 1]
        process_versions(version_file_path, output_dir)
