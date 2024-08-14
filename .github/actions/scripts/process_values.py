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

    # Extract defaults in ordder to generate the default versions for each components
    defaults = versions_data.get('defaults', {})
    default_values = {'services': {}, 'versions': {}}

    # Add defaults for components, this needs to be as dynamic as possible, because currently we have 3 components (review, processing, reveal_ai) but in the future we want this to be dynamacally generated
    for component, component_data in defaults.items():
        default_version = component_data.get('default', 'default_version')
        default_values['versions'][f"default_{component}"] = default_version
        services = component_data.get('services', {})
        for service, version in services.items():
            default_values['services'][service] = {'tag': version}

    # Write the default values.yaml which all non-overriden MSA's will be symmlinked to
    default_values_path = os.path.join(output_dir, 'default_values.yaml')
    write_yaml(default_values, default_values_path)
    print(f"Generated {default_values_path}")

    # Process each MSA that have some overriden vallues
    msas = versions_data.get('msas', {})
    for msa, msa_data in msas.items():
        values = {
            'services': dict(default_values['services']),
            'versions': dict(default_values['versions'])
        }

        # Get MSA-specific overrides for all components, this is supposed to be in MSA level
        for component, component_data in msa_data.items():
            for key, version in component_data.get('versions', {}).items():
                if key in values['versions']:
                    values['versions'][key] = version
                    print(f"Overriding {key} for MSA {msa} with version {version}")

            # Update services
            for service, version in component_data.get('services', {}).items():
                if service in values['services']:
                    values['services'][service]['tag'] = version
                    print(f"Overriding {service} for MSA {msa} with version {version}")

        # Random Redon Debug
        print(f"MSA {msa} values before writing to file: {values}")

        # Random Redon Debug
        msa_file_path = os.path.join(output_dir, f"{msa}.yaml")
        print(f"Writing to {msa_file_path}")
        write_yaml(values, msa_file_path)
        print(f"Generated {msa_file_path}")


if __name__ == "__main__":
    for i in range(1, len(sys.argv), 2):
        version_file_path = sys.argv[i]
        output_dir = sys.argv[i + 1]
        process_versions(version_file_path, output_dir)
