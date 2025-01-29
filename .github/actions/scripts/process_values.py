import yaml
import os
import sys
import requests
import json


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

            msa_default_version = component_data.get('default')
            if msa_default_version:
                msa_values['versions'][component_key] = msa_default_version
                for service in default_values['services'].keys():
                    if service.startswith(component):  # Override all services under the same component
                        msa_values['services'][service] = {'tag': msa_default_version}

            if 'services' in component_data:
                for service, version in component_data['services'].items():
                    msa_values['services'][service] = {'tag': version}

        """
        Generated {msa}.yaml files will be overriding the symlinks, which means these MSAs have overrides and different values from default_values.yaml
        """
        msa_file_path = os.path.join(output_dir, f"{msa}.yaml")
        write_yaml(msa_values, msa_file_path)
        print(f"Generated {msa_file_path}")
        return versions_data

def build_slack_message(versions_data, version_file_path):
    """
    Build a Slack-friendly text summary of what's in versions.yaml.
    """
    defaults = versions_data.get('defaults', {})
    msas = versions_data.get('msas', {})

    lines = []
    lines.append(f":bell: *Review-GitOps Update for* `{version_file_path}`")

    # Summarize defaults
    lines.append("\n*Defaults:*")
    for component, comp_data in defaults.items():
        default_ver = comp_data.get('default', 'N/A')
        lines.append(f" - *{component}* default = `{default_ver}`")

        # Show per-service versions if any
        for svc, svc_ver in comp_data.get('services', {}).items():
            lines.append(f"   - service `{svc}` = `{svc_ver}`")

    # Summarize MSA overrides
    if msas:
        lines.append("\n*MSA Overrides:*")
        for msa, override_data in msas.items():
            lines.append(f" - MSA `{msa}`:")
            for comp, comp_values in override_data.items():
                lines.append(f"   - Component: `{comp}`")
                if 'default' in comp_values:
                    lines.append(f"     - default override = `{comp_values['default']}`")
                for svc, svc_ver in comp_values.get('services', {}).items():
                    lines.append(f"     - service `{svc}` = `{svc_ver}`")
    else:
        lines.append("\nNo MSA overrides found.")

    return "\n".join(lines)

def post_to_slack(slack_webhook, message):
    """
    Posts the given message to Slack using the provided webhook.
    """
    payload = {"text": message}
    headers = {"Content-Type": "application/json"}

    try:
        resp = requests.post(slack_webhook, headers=headers, data=json.dumps(payload))
        resp.raise_for_status()
        print("Slack message posted successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Failed to post message to Slack: {e}")
        # Depending on your preference, you might want to exit non-zero
        # to fail the workflow if Slack fails.
        # sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python process_values.py <version_file.yaml> <output_directory>")
        sys.exit(1)

    version_file_path = sys.argv[1]
    output_dir = sys.argv[2]
    versions_data = process_versions(version_file_path, output_dir)
    slack_message = build_slack_message(versions_data, version_file_path)

    slack_webhook = os.getenv("SLACK_WEBHOOK", None)
    if slack_webhook:
        post_to_slack(slack_webhook, slack_message)
    else:
        print("SLACK_WEBHOOK env var not found. Skipping Slack post.")
        # Or exit(1) if you consider it mandatory
