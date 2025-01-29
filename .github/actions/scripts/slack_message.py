#!/usr/bin/env python

import os
import sys
import yaml
import json
import requests

ARGO_URLS = {
    "dev": {
        "us-east-1": "https://argocd.us-east-1.dev.revealglobal.cloud/"
    },
    "uat": {
        "eu-west-1": "https://argocd.eu-west-1.dev.revealglobal.cloud/"
    },
    "prod": {
        "us-east-1": "https://argocd.us-east-1.revealglobal.cloud/",
        "eu-west-1": "https://argocd.eu-west-1.revealglobal.cloud/"
    }
}

def load_yaml(file_path):
    """Load a YAML file safely."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def post_to_slack(slack_webhook, message):
    """Post the given message to Slack using requests."""
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
        # Optionally: sys.exit(1)

###############################################################################
# Summaries
###############################################################################
def summarize_review_versions(data, file_path):
    """
    Summarize a `versions.yaml` file that has 'defaults' and 'msas'.
    """
    lines = []
    lines.append(f":bell: *Review-GitOps Update for* `{file_path}`")

    defaults = data.get('defaults', {})
    msas = data.get('msas', {})

    lines.append("\n*Defaults:*")
    for component, comp_data in defaults.items():
        default_ver = comp_data.get('default', 'N/A')
        lines.append(f" - *{component}* default = `{default_ver}`")

        for svc, svc_ver in comp_data.get('services', {}).items():
            lines.append(f"   - service `{svc}` = `{svc_ver}`")

    if msas:
        lines.append("\n*MSA Overrides:*")
        for msa, override_data in msas.items():
            lines.append(f" - MSA `{msa}`:")
            for comp_name, comp_values in override_data.items():
                lines.append(f"   - Component: `{comp_name}`")
                if 'default' in comp_values:
                    lines.append(f"     - default override = `{comp_values['default']}`")
                for svc, svc_ver in comp_values.get('services', {}).items():
                    lines.append(f"     - service `{svc}` = `{svc_ver}`")
    else:
        lines.append("\nNo MSA overrides found.")

    return "\n".join(lines)


def summarize_helm_values(data, file_path):
    """
    Summarize a Helm values YAML, scanning for {image, tag} pairs.
    """
    lines = []
    lines.append(f":helm: *Helm Values Update for* `{file_path}`")

    found_images = []

    def find_images_recursively(obj, path=""):
        """Recursively walk the YAML dict for 'image'/'tag'."""
        if isinstance(obj, dict):
            if "image" in obj and "tag" in obj:
                found_images.append({
                    "path": path.strip("/"),
                    "image": obj["image"],
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

    if found_images:
        lines.append("\n*Found these image:tag references:*")
        for item in found_images:
            p = item['path'] or 'root'
            lines.append(f" - Path: `{p}`, image: `{item['image']}`, tag: `{item['tag']}`")
    else:
        lines.append("\nNo `image` + `tag` references found in the Helm values.")

    return "\n".join(lines)

###############################################################################
# Main logic: parse arguments, pick style, generate Slack message
###############################################################################
def main():
    """
    Usage:
      python unified_process_values.py <file.yaml> <env> <region> [style]

    Examples:
      python unified_process_values.py review-gitops/prod/us-east-1/versions.yaml prod us-east-1 review
      python unified_process_values.py some/helm/values.yaml dev us-east-1 helm
      python unified_process_values.py some/path/file.yaml dev us-east-1 auto
    """
    if len(sys.argv) < 4:
        print("Usage: python unified_process_values.py <file.yaml> <env> <region> [style]")
        sys.exit(1)

    file_path = sys.argv[1]
    environment = sys.argv[2]
    region = sys.argv[3]

    # If no style is provided, default to "auto"
    style = sys.argv[4] if len(sys.argv) >= 5 else "auto"

    # 1) Load YAML
    data = load_yaml(file_path)
    if not data:
        print(f"WARNING: YAML file {file_path} appears empty.")
        data = {}

    # 2) Determine summarization approach:
    if style == "auto":
        # Example "auto" detection:
        if "defaults" in data or "msas" in data:
            style = "review"
        else:
            style = "helm"

    # 3) Summarize
    if style == "review":
        slack_message = summarize_review_versions(data, file_path)
    elif style == "helm":
        slack_message = summarize_helm_values(data, file_path)
    else:
        print(f"ERROR: Unknown style '{style}'. Use 'review', 'helm', or 'auto'.")
        sys.exit(1)

    # 4) Append ArgoCD URL
    argocd_url = ARGO_URLS.get(environment, {}).get(region, "Unknown ArgoCD URL")
    slack_message += f"\n\n:point_right: *ArgoCD URL:* <{argocd_url}>"

    # 5) (Optional) Post to Slack
    slack_webhook = os.getenv("SLACK_WEBHOOK", None)
    post_to_slack(slack_webhook, slack_message)

    print("\nDone.\n")

if __name__ == "__main__":
    main()
