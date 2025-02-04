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

def main():
    """
    Usage:
      python slack_notify.py <file.yaml> <env> <region> [style]

    Examples:
      python slack_notify.py review-gitops/prod/us-east-1/versions.yaml prod us-east-1 review
      python slack_notify.py revealai-gitops/helm/values.yaml dev us-east-1 helm
      python slack_notify.py some/path/file.yaml dev us-east-1 auto
    """
    if len(sys.argv) < 4:
        print("Usage: python slack_notify.py <file.yaml> <env> <region> [style]")
        sys.exit(1)

    file_path = sys.argv[1]
    environment = sys.argv[2]
    region = sys.argv[3]

    """ 
    If no style is provided, default to "auto" 
    """
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