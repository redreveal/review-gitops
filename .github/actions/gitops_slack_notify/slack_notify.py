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

def summarize_review_versions(data, file_path):
    lines = []
    lines.append(f":bell: *Review-GitOps Update for* `{file_path}`")
    lines.append("```")

    defaults = data.get('defaults', {})
    msas = data.get('msas', {})

    lines.append("Defaults:")
    for component, comp_data in defaults.items():
        default_ver = comp_data.get('default', 'N/A')
        lines.append(f" - {component} default = {default_ver}")

        for svc, svc_ver in comp_data.get('services', {}).items():
            lines.append(f"   - service {svc} = {svc_ver}")

    if msas:
        lines.append("\nMSA Overrides:")
        for msa, override_data in msas.items():
            lines.append(f" - MSA {msa}:")
            for comp_name, comp_values in override_data.items():
                lines.append(f"   - Component: {comp_name}")
                if 'default' in comp_values:
                    lines.append(f"     - default override = {comp_values['default']}")
                for svc, svc_ver in comp_values.get('services', {}).items():
                    lines.append(f"     - service {svc} = {svc_ver}")
    else:
        lines.append("\nNo MSA overrides found.")

    lines.append("```")
    return "\n".join(lines)

def summarize_helm_values(data, file_path):
    """
    Existing single-file helm summarization (non-aggregated).
    Searches recursively for "image" and "tag" entries.
    """
    lines = []
    lines.append(f":bell: *Helm Values Update for* `{file_path}`")
    lines.append("```")

    found_images = []

    def find_images_recursively(obj, path=""):
        if isinstance(obj, dict):
            if "image" in obj and "tag" in obj:
                found_images.append({
                    "path": path.strip("/") or "root",
                    "full_image": obj["image"],
                    "tag": obj["tag"]
                })
            for k, v in obj.items():
                new_path = f"{path}/{k}"
                find_images_recursively(v, new_path)
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                new_path = f"{path}/{idx}"
                find_images_recursively(item, new_path)

    find_images_recursively(data)

    def short_image_name(full_image):
        splitted = full_image.split('/', 1)
        if len(splitted) == 2:
            return splitted[1]  # e.g. "dev/automation/reveal-ai-automation"
        return full_image

    if found_images:
        for item in found_images:
            short_name = short_image_name(item["full_image"])
            lines.append(f" - {short_name}: {item['tag']}")
    else:
        lines.append("No `image` + `tag` references found in the Helm values.")

    lines.append("```")
    return "\n".join(lines)

### New functions for aggregated helm mode

def aggregate_helm_values(file_paths):
    """
    Aggregate version data from multiple helm values files.
    We search each file for image and tag references and group by chart.
    """
    aggregated = defaultdict(dict)  # chart -> { region: tag }
    for file_path in file_paths:
        # Extract environment and region from file path.
        # Adjust these indices based on your repo structure.
        parts = file_path.split(os.sep)
        if len(parts) >= 3:
            if len(parts) == 3:
                env = parts[0]
                region = parts[1]
            else:
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

        found_images = []

        def find_images_recursively(obj, path=""):
            if isinstance(obj, dict):
                if "image" in obj and "tag" in obj:
                    found_images.append({
                        "path": path.strip("/") or "root",
                        "full_image": obj["image"],
                        "tag": obj["tag"]
                    })
                for k, v in obj.items():
                    new_path = f"{path}/{k}"
                    find_images_recursively(v, new_path)
            elif isinstance(obj, list):
                for idx, item in enumerate(obj):
                    new_path = f"{path}/{idx}"
                    find_images_recursively(item, new_path)

        find_images_recursively(data)

        def short_image_name(full_image):
            splitted = full_image.split('/', 1)
            if len(splitted) == 2:
                return splitted[1]
            return full_image

        for item in found_images:
            chart = short_image_name(item["full_image"])
            # Record the tag for this region
            aggregated[chart][region] = item["tag"]

    return aggregated

def format_aggregated_helm_message(aggregated, base_file, environment, region, argocd_url):
    lines = []
    lines.append(f":bell: *Helm Values Aggregated Update for* `{base_file}`")
    lines.append("```")
    for chart, region_versions in aggregated.items():
        lines.append(f" - {chart}:")
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
    # Aggregated mode: first argument is "helm" and exactly two arguments provided.
    if len(sys.argv) == 3 and sys.argv[1] == "helm":
        aggregated_list_file = sys.argv[2]
        try:
            with open(aggregated_list_file, 'r') as f:
                file_paths = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"Error reading aggregated file list: {e}")
            sys.exit(1)
        if not file_paths:
            print("No files to process in aggregated file list.")
            sys.exit(0)

        # For display purposes, create a base file by stripping GITHUB_WORKSPACE from the first file path.
        workspace = os.environ.get("GITHUB_WORKSPACE", "")
        base_file = file_paths[0]
        if workspace and base_file.startswith(workspace):
            base_file = base_file.replace(workspace + os.sep, "")
        aggregated = aggregate_helm_values(file_paths)

        # Determine environment and region from the first file path.
        parts = file_paths[0].split(os.sep)
        if len(parts) >= 3:
            if len(parts) == 3:
                environment = parts[0]
                region = parts[1]
            else:
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
        # Single-file mode.
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