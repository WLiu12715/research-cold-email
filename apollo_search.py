import requests
import yaml

# Load config
with open("config.yaml") as f:
    config = yaml.safe_load(f)
API_KEY = config['apollo']['api_key']

# Prompt user for search criteria
print("Enter your Apollo lead search criteria:")
job_title = input("Job Title (e.g. Marketing Manager): ").strip()
location = input("Location (e.g. San Francisco): ").strip()
industry = input("Industry (e.g. SaaS): ").strip()
company_size = input("Company Size (e.g. 51-200): ").strip()

# Build payload for Apollo API
payload = {
    "person_titles": [job_title] if job_title else [],
    "person_locations": [location] if location else [],
    "organization_industries": [industry] if industry else [],
    "organization_employee_count": [company_size] if company_size else []
}

headers = {
    "Cache-Control": "no-cache",
    "Content-Type": "application/json",
    "x-api-key": API_KEY
}

response = requests.post(
    "https://api.apollo.io/v1/people/search",
    json=payload,
    headers=headers
)

if response.status_code == 200:
    results = response.json()
    print(f"Found {results.get('pagination', {}).get('total', 0)} leads.")
    for person in results.get('people', []):
        print(f"{person.get('first_name')} {person.get('last_name')}, {person.get('title')} at {person.get('organization', {}).get('name')}")
else:
    print("[ERROR] Apollo API call failed:", response.status_code, response.text)
