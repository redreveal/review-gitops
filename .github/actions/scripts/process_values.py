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
    os.makedirs(output_dir, exist_ok=True)

    default_values = {'services': {}, 'versions': {}}
    """
    Process default versions for each component, a component is a group of services. I.e review, reveal_ai, processing.
    """
    for component, component_data in versions_data.get('defaults', {}).items():
        default_version = component_data.get('default', 'default_version')
        default_values['versions'][f"default_{component}"] = default_version

        if 'services' in component_data:
            for service, version in component_data['services'].items():
                default_values['services'][service] = {'tag': version}
    """
    default_values.yaml is the file that will be symlinked to by all MSAs that do not have any overridden values.
    """
    default_values_path = os.path.join(output_dir, 'default_values.yaml')
    write_yaml(default_values, default_values_path)
    print(f"Generated {default_values_path}")

    """
    This iteration handles MSA override values. It starts with the default values and applies MSA-specific overrides.
    """
    for msa, msa_data in versions_data.get('msas', {}).items():
        print(f"Processing MSA: {msa}")
        msa_values = {
            'services': dict(default_values['services']),
            'versions': dict(default_values['versions'])
        }

        for component, component_data in msa_data.items():
            component_key = f"default_{component}"

            if 'services' in component_data:
                for service, version in component_data['services'].items():
                    msa_values['services'][service] = {'tag': version}
            if 'default' in component_data:
                msa_values['versions'][component_key] = component_data['default']

        """
        Generated {msa}.yaml files will be overriding the symlinks, which means these MSAs have overrides and different values from default_values.yaml
        """
        msa_file_path = os.path.join(output_dir, f"{msa}.yaml")
        write_yaml(msa_values, msa_file_path)
        print(f"Generated {msa_file_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python process_values.py <version_file.yaml> <output_directory>")
        sys.exit(1)

    version_file_path = sys.argv[1]
    output_dir = sys.argv[2]
    process_versions(version_file_path, output_dir)
