#!/usr/bin/env python3
import os
import sys
import yaml
import json
import requests
from collections import defaultdict

ARGO_URLS = {
    "dev": {
        "us-east-1": "https://argocd.us-east-1.dev.revealglobal.cloud/"
    },
    "uat": {
        "eu-west-1": "https://argocd.eu-west-1.dev.revealglobal.cloud/"
    },
    "prod": {
        "us-east-1": "https://argocd.us-east-1.revealglobal.cloud/",
        "ap-south-1": "https://argocd.eu-west-1.revealglobal.cloud/",
        "ap-southeast-2": "https://argocd.ap-southeast-2.revealglobal.cloud/",
        "ca-central-1": "https://argocd.ca-central-1.revealglobal.cloud/",
        "eu-central-1": "https://argocd.eu-central-1.revealglobal.cloud/",
        "eu-west-1": "https://argocd.eu-west-1.revealglobal.cloud/",
        "eu-west-2": "https://argocd.eu-west-2.revealglobal.cloud/",
        "me-central-1": "https://argocd.me-central-1.revealglobal.cloud/"
    }
}


def load_yaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def post_to_slack(slack_webhook, message):
    if not slack_webhook:
        print("No slack_webhook provided; skipping Slack post.")
        return

    payload = {"text": message}
    headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(slack_webhook, headers=headers, data=json.dumps(payload))
        resp.raise_for_status()
        print("Slack message posted successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Failed to post message to Slack: {e}")


# (Existing summarize_review_versions and summarize_helm_values functions remain unchanged.)

### NEW: Functions for Aggregated Helm Mode

def aggregate_helm_values(file_paths):
    """
    Aggregate version data from multiple helm values files.
    This version expects that each helm values file is a YAML mapping whose
    top-level keys include service groups (for example: serviceWatcher,
    automation, etc.) and that each such service value is a dict containing
    "image" and "tag". It extracts the short image name (by stripping off the
    registry portion) and aggregates the tag by region.

    The returned structure is:
      {
        serviceGroup1: {
           short_image_name1: { region: tag, ... },
           short_image_name2: { region: tag, ... }
        },
        serviceGroup2: {
           short_image_name3: { region: tag, ... },
           ...
        },
        ...
      }
    """
    from collections import defaultdict
    aggregated = {}  # Use a normal dict for easier formatting later.

    for file_path in file_paths:
        # Extract environment and region from the file path.
        # For example, a file path like:
        #   revealai-gitops/RAI/prod/eu-west-1/values.yaml
        # We assume:
        #   parts[0]: checkout folder (e.g. "revealai-gitops")
        #   parts[1]: extra prefix (e.g. "RAI") – optional
        #   parts[2]: environment (e.g. "prod")
        #   parts[3]: region (e.g. "eu-west-1")
        parts = file_path.split(os.sep)
        if len(parts) >= 4 and parts[1] in ["RAI", "RAI-bootstrap"]:
            env = parts[2]
            region = parts[3]
        elif len(parts) >= 3:
            env = parts[1]
            region = parts[2]
        else:
            env = "unknown"
            region = "unknown"

        try:
            data = load_yaml(file_path)
        except Exception as e:
            print(f"Error loading YAML from {file_path}: {e}")
            continue

        # Iterate over top-level keys that we consider as service groups.
        for service_group, service_data in data.items():
            # Check that this is a dict and that it contains "image" and "tag".
            if not (isinstance(service_data, dict) and "image" in service_data and "tag" in service_data):
                continue

            # Use the top-level key as the service group.
            # Get the image and tag.
            image_value = service_data["image"]
            tag_value = service_data["tag"]

            # Derive a short image name by removing the registry portion.
            # For example, split on '/' and take everything from the second element.
            parts_img = image_value.split('/')
            if len(parts_img) >= 2:
                short_image = '/'.join(parts_img[1:])  # e.g. "prod/reveal_ai/servicewatcher"
            else:
                short_image = image_value

            # Initialize nested dictionaries.
            if service_group not in aggregated:
                aggregated[service_group] = {}
            if short_image not in aggregated[service_group]:
                aggregated[service_group][short_image] = {}
            # Record the tag under the detected region.
            aggregated[service_group][short_image][region] = tag_value

    return aggregated


def format_aggregated_helm_message(aggregated, base_file, environment, region, argocd_url):
    """
    Format the aggregated version data into a Slack message.

    The output will look like:

    serviceWatcher:
      prod/reveal_ai/servicewatcher:
          us-east-1 : 2024.11.4
          eu-west-1 : 2024.11.4
    automation:
      prod/automation/reveal-ai-automation:
          us-east-1 : 2024.11.1
          eu-west-1 : 2024.11.1
    ...

    Then the ArgoCD URL line is appended.
    """
    lines = []
    lines.append(f":bell: *Helm Values Aggregated Update for* `{base_file}`")
    lines.append("```")
    for service_group, service_dict in aggregated.items():
        lines.append(f"{service_group}:")
        for short_image, region_versions in service_dict.items():
            lines.append(f"  {short_image}:")
            for reg, version in region_versions.items():
                lines.append(f"    {reg} : {version}")
    lines.append("```")
    lines.append(f":point_right: *ArgoCD:* <{argocd_url}|ArgoCD URL for {environment}/{region}>")
    lines.append("\n---\n")
    return "\n".join(lines)


def main():
    """
    Usage:
      Single-file mode:
        python slack_notify.py <file.yaml> <env> <region> [style]
      Aggregated helm mode:
        python slack_notify.py helm <aggregated_file_list.txt>
    """
    # Check for Aggregated mode:
    if len(sys.argv) == 3 and sys.argv[1] == "helm":
        aggregated_list_file = sys.argv[2]
        try:
            with open(aggregated_list_file, 'r') as f:
                file_paths = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"Error reading aggregated file list: {e}")
            sys.exit(1)
        # Remove duplicate file paths if any.
        file_paths = list(set(file_paths))
        if not file_paths:
            print("No files to process in aggregated file list.")
            sys.exit(0)

        # For display purposes, create a base file by stripping GITHUB_WORKSPACE from the first file path.
        workspace = os.environ.get("GITHUB_WORKSPACE", "")
        base_file = file_paths[0]
        if workspace and base_file.startswith(workspace):
            base_file = base_file.replace(workspace + os.sep, "")

        # Aggregate the version data.
        aggregated = aggregate_helm_values(file_paths)

        # Determine environment and region from the first file path using the new logic.
        parts = file_paths[0].split(os.sep)
        if len(parts) >= 4 and parts[1] in ["RAI", "RAI-bootstrap"]:
            environment = parts[2]
            region = parts[3]
        elif len(parts) >= 3:
            environment = parts[1]
            region = parts[2]
        else:
            environment = "unknown"
            region = "unknown"

        base_argocd_url = ARGO_URLS.get(environment, {}).get(region, "Unknown ArgoCD URL")
        slack_message = format_aggregated_helm_message(aggregated, base_file, environment, region, base_argocd_url)
        slack_webhook = os.getenv("SLACK_WEBHOOK", None)
        post_to_slack(slack_webhook, slack_message)
        sys.exit(0)
    else:
        # Single-file mode remains as before.
        if len(sys.argv) < 4:
            print("Usage: python slack_notify.py <file.yaml> <env> <region> [style]")
            sys.exit(1)

        file_path = sys.argv[1]
        environment = sys.argv[2]
        region = sys.argv[3]
        style = sys.argv[4] if len(sys.argv) >= 5 else "auto"

        data = load_yaml(file_path)
        if not data:
            print(f"WARNING: YAML file {file_path} appears empty.")
            data = {}

        if style == "auto":
            if "defaults" in data or "msas" in data:
                style = "review"
            else:
                style = "helm"

        if style == "review":
            slack_message = summarize_review_versions(data, file_path)
        elif style == "helm":
            slack_message = summarize_helm_values(data, file_path)
        else:
            print(f"ERROR: Unknown style '{style}'. Use 'review', 'helm', or 'auto'.")
            sys.exit(1)

        base_argocd_url = ARGO_URLS.get(environment, {}).get(region, "Unknown ArgoCD URL")
        if style == "review":
            filtered_url = f"{base_argocd_url}/applications?search=review-&view=list&showFavorites=false&proj=&sync=&autoSync=&health=&namespace=&cluster=&labels="
            slack_message += f"\n\n:point_right: *ArgoCD:* <{filtered_url}|ArgoCD URL for ({environment}/{region})>\n"
        else:
            slack_message += f"\n\n:point_right: *ArgoCD:* <{base_argocd_url}|ArgoCD URL for {environment}/{region}>\n"
        slack_message += "\n---\n"
        slack_webhook = os.getenv("SLACK_WEBHOOK", None)
        post_to_slack(slack_webhook, slack_message)


if __name__ == "__main__":
    main()
