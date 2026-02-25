from flask import Flask, request, jsonify
import requests
import json
import base64
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


app = Flask(__name__)

def get_repo_name_description(url, token):
    headers = {}
    if token:
        headers['Authorization'] = f"Bearer {token}"
        
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        repositories = response.json()
        print("INFO LOG: able to fetch repo name: " + repositories["name"])
        print("INFO LOG: able to fetch repo description: " + repositories["description"])
        return { "name": repositories["name"], "description": repositories["description"] }
    else:
        print(f"Failed to retrieve repositories. Status code: {response.status_code}")


def get_repo_readme(url, token):
    readme_url = url + '/readme'

    headers = {}
    if token:
        headers['Authorization'] = f"Bearer {token}"

    response = requests.get(readme_url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        # README content is base64-encoded by the GitHub API
        readme_content = base64.b64decode(data['content']).decode('utf-8')
        print("INFO LOG: successfully fetched README content")
        return readme_content
    else:
        print(f"Failed to retrieve README. Status code: {response.status_code}")
        return None

def get_repo_file_structure(url, token):
    url = url + '/git/trees/master?recursive=1'
    headers = {}
    if token:
        headers['Authorization'] = f"Bearer {token}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        tree_data = response.json()
        print("INFO LOG TREE DATA: " + str(tree_data))
        files = [item['path'] for item in tree_data['tree'] if item['type'] == 'blob']
        folders = [item['path'] for item in tree_data['tree'] if item['type'] == 'tree']
        print(f"INFO LOG: Found {len(files)} files and {len(folders)} folders")
        return {"files": files, "folders": folders, "full_tree": tree_data['tree']}
    else:
        print(f"Failed to retrieve file structure. Status code: {response.status_code}")
        return None


@app.route('/summarize', methods=['POST'])
def summarize():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return jsonify({"ERROR": "GITHUB_TOKEN environment variable is not set"}), 500

    data = request.get_json()
    if not data:
        return jsonify({"ERROR": "No JSON payload provided"}), 400
    
    github_url = data.get('github_url')
    if not github_url:
        return jsonify({"ERROR": "Missing 'github_url' field"}), 400

    # fetch repo name & description
    repo_content = get_repo_name_description(github_url, token)
    if not repo_content:
        return jsonify({"ERROR": "Failed to retrieve repo info"}), 500

    # fetch README content
    readme = get_repo_readme(github_url, token)
    if not readme:
        return jsonify({"ERROR": "Failed to retrieve README content"}), 500

    file_structure = get_repo_file_structure(github_url, token)
    if not file_structure:
        return jsonify({"ERROR": "Failed to retrieve file structure"}), 500

    # create prompt
    prompt = f"""
    You are an expert software engineer and technical writer.
    Analyze the GitHub repository details below and respond with ONLY a valid JSON object — no markdown, no code fences, no extra text.

    The JSON must have exactly these three keys:
    {{
      "summary": "A concise 2-3 sentence overview of what the repository does.",
      "technologies_used": ["list", "of", "languages", "frameworks", "tools"],
      "repo_structure": "A brief human-readable description of the key folders/files and their purpose."
    }}

    Repo name: {repo_content["name"]}
    Repo description: {repo_content["description"]}
    Repo readme: {readme}
    Repo file structure (files): {file_structure["files"]}
    Repo file structure (folders): {file_structure["folders"]}
    """

    # connect with gemini
    response = client.models.generate_content(
        model="gemini-3-flash-preview", contents=prompt
    )
    raw_text = response.text.strip()
    print("INFO LOG - Raw model response: " + raw_text)

    # Parse JSON response from the model
    try:
        parsed = json.loads(raw_text)
        summary = parsed.get("summary", "")
        technologies_used = parsed.get("technologies_used", [])
        repo_structure = parsed.get("repo_structure", "")
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse model JSON response: {e}")
        return jsonify({"ERROR": "Model returned invalid JSON", "raw_response": raw_text}), 500
    

    return jsonify({
        "summary": summary,
        "technologies": technologies_used,
        "structure": repo_structure
    }), 200

if __name__ == '__main__':
    app.run(debug=True)