import json
from flask import Flask, render_template, request, jsonify
import requests
import yaml

app = Flask(__name__)

# --- Load config and Perplexity API key ---
def load_config():
    with open('auto c&c /config.yaml', 'r') as f:
        return yaml.safe_load(f)

CONFIG = load_config()
PERPLEXITY_API_KEY = CONFIG.get('perplexity', {}).get('api_key', None)

# Semantic Scholar search function
SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

API_KEY = None  # Optionally load from config.yaml if you get one

import xml.etree.ElementTree as ET

from flask import current_app

# --- Perplexity API integration ---

@app.route('/ask_perplexity', methods=['POST'])
def ask_perplexity():
    if not PERPLEXITY_API_KEY:
        return jsonify({'error': 'Perplexity API key not configured.'}), 500
    data = request.get_json()
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'error': 'Query is required.'}), 400
    headers = {
        'Authorization': f'Bearer {PERPLEXITY_API_KEY}',
        'Content-Type': 'application/json'
    }
    filtering_instructions = (
        "Only include faculty who are research-qualified (Assistant, Associate, or Full Professors) "
        "and who have research publications. For each faculty member, list all available research publications. "
        "Exclude lecturers, adjuncts, and administrative staff."
    )
    full_query = f"{filtering_instructions}\n\nUser query: {query}"
    payload = {
        'model': 'sonar-pro',
        'messages': [
            {"role": "system", "content": "You are an academic research assistant."},
            {"role": "user", "content": full_query}
        ],
        'stream': False
    }
    resp = requests.post('https://api.perplexity.ai/chat/completions', headers=headers, data=json.dumps(payload))
    if resp.status_code == 200:
        result = resp.json()
        answer = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        citations = result.get('choices', [{}])[0].get('message', {}).get('citations', [])
        return jsonify({'answer': answer, 'citations': citations, 'query': query})
    else:
        return jsonify({'error': f'Perplexity API error: {resp.status_code}', 'details': resp.text}), 500

import re

def load_faculty_by_department(dept_keywords):
    # Load all faculty from the JSON file and filter by department keywords
    try:
        with open('ga_tech_faculty.json', 'r', encoding='utf-8') as f:
            all_faculty = json.load(f)
        filtered = []
        for prof in all_faculty:
            dept = (prof.get('department') or '').lower()
            if any(kw.lower() in dept for kw in dept_keywords):
                filtered.append(prof)
        return filtered
    except Exception as e:
        return []

@app.route('/ask_and_enrich_perplexity', methods=['POST'])
def ask_and_enrich_perplexity():
    if not PERPLEXITY_API_KEY:
        return jsonify({'error': 'Perplexity API key not configured.'}), 500
    data = request.get_json()
    query = data.get('query', '').strip()
    school_name = data.get('school_name', 'Georgia Tech')
    if not query:
        return jsonify({'error': 'Query is required.'}), 400
    headers = {
        'Authorization': f'Bearer {PERPLEXITY_API_KEY}',
        'Content-Type': 'application/json'
    }
    filtering_instructions = (
        "Only include faculty who are research-qualified (Assistant, Associate, or Full Professors) "
        "and who have research publications. For each faculty member, list all available research publications. "
        "Exclude lecturers, adjuncts, and administrative staff."
    )
    full_query = f"{filtering_instructions}\n\nUser query: {query}"
    payload = {
        'model': 'sonar-pro',
        'messages': [
            {"role": "system", "content": "You are an academic research assistant."},
            {"role": "user", "content": full_query}
        ],
        'stream': False
    }
    resp = requests.post('https://api.perplexity.ai/chat/completions', headers=headers, data=json.dumps(payload))
    if resp.status_code == 200:
        result = resp.json()
        answer = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        # Extract professor names: only lines that look like real people (Dr. or Professor or two capitalized words)
        lines = answer.split('\n')
        person_names = []
        for line in lines:
            line = line.strip()
            # Markdown bold name: **Dr. Name** or **Professor Name** or **Firstname Lastname**
            if line.startswith('**') and line.endswith('**'):
                core = line.strip('*').strip()
                if re.match(r'^(Dr\.|Professor)\s+[A-Z][a-zA-Z\-]+(\s+[A-Z][a-zA-Z\-]+)+$', core) or re.match(r'^[A-Z][a-zA-Z\-]+\s+[A-Z][a-zA-Z\-]+$', core):
                    person_names.append(re.sub(r'^(Dr\.|Professor)\s+', '', core))
            # Or lines starting with Dr./Professor
            elif re.match(r'^(Dr\.|Professor)\s+[A-Z][a-zA-Z\-]+(\s+[A-Z][a-zA-Z\-]+)+', line):
                person_names.append(re.sub(r'^(Dr\.|Professor)\s+', '', line))
        # Remove duplicates and empty
        clean_names = list({n.strip() for n in person_names if n.strip()})
        results = []
        if clean_names:
            for name in clean_names:
                try:
                    prof_info = extract_professor_info(None, name, '', school_name)
                    results.append(prof_info)
                except Exception as e:
                    results.append({'name': name, 'error': str(e)})
        else:
            # Fallback: find department keyword from query or answer
            dept_keywords = []
            dept_map = {
                'bme': 'biomedical',
                'biomedical': 'biomedical',
                'ece': 'electrical',
                'electrical': 'electrical',
                'mechanical': 'mechanical',
                'aerospace': 'aerospace',
                'civil': 'civil',
                'chemical': 'chemical',
                'industrial': 'industrial',
                'materials': 'materials',
                'nuclear': 'nuclear',
            }
            ql = query.lower() + ' ' + answer.lower()
            for k, v in dept_map.items():
                if k in ql:
                    dept_keywords.append(v)
            if not dept_keywords:
                dept_keywords = ['biomedical']  # default fallback
            results = load_faculty_by_department(dept_keywords)
        # Shorten the Perplexity answer (first paragraph or up to 400 chars)
        short_answer = ''
        paras = [p.strip() for p in answer.split('\n') if p.strip()]
        if paras:
            short_answer = paras[0][:400]
        else:
            short_answer = answer[:400]
        # --- Improved fuzzy matching for enrichment ---
        import difflib
        import re
        def normalize_name(name):
            # Remove titles, punctuation, extra whitespace, and lowercase
            if not name:
                return ''
            name = re.sub(r"^(Dr\.|Professor)\s+", "", name)
            name = re.sub(r"[^a-zA-Z\s]", "", name)  # Remove punctuation
            name = re.sub(r"\s+", " ", name)  # Collapse whitespace
            return ''.join(name.lower().split())
        # Load all faculty data for matching
        with open('ga_tech_faculty.json', 'r') as f:
            all_faculty = json.load(f)
        # Filter out non-faculty entries
        NON_FACULTY_NAMES = set([
            'home', 'directory', 'visitor parking information', 'main directory', 'day', 'welcome',
            'undergraduate handbook', 'professional education', 'financial aid', 'faculty', 'staff', 'office', 'about', 'contact', 'events', 'graduate handbook', 'student', 'advising', 'administration', 'resources', 'faq', 'news', 'alumni', 'forms', 'information', 'handbook', 'overview'
        ])
        faculty_by_norm = {}
        for fac in all_faculty:
            norm = normalize_name(fac['name'])
            if not norm or norm in NON_FACULTY_NAMES:
                continue
            faculty_by_norm[norm] = fac
        # For each result, try fuzzy match
        enriched_results = []
        for prof in results:
            name = prof.get('name', '')
            norm_name = normalize_name(name)
            # Try exact match
            fac = faculty_by_norm.get(norm_name)
            # Try fuzzy match if not found
            if not fac:
                close_matches = difflib.get_close_matches(norm_name, faculty_by_norm.keys(), n=1, cutoff=0.85)
                if close_matches:
                    fac = faculty_by_norm[close_matches[0]]
            if fac:
                # Only use profile_url if it looks like a real faculty profile (not a directory or info page)
                profile_url = fac.get('profile_url', '')
                if (not profile_url or
                    any(x in profile_url.lower() for x in [
                        '/directory', '/main', '/home', '/visitor', '/about', '/faq', '/resources', '/forms', '/news', '/events', '/advising', '/student', '/staff', '/alumni', '/office', '/overview', '/information', '/handbook', '/contact', '/graduate', '/undergraduate', '/professional-education', '/financial-aid', '/calendar', '/specialevents', '/study-abroad', '/lifetimelearning', '/tickets', '/tech-lingo', '/undergraduate', '/directory1', 'signup.e2ma.net', 'parkmobile', 'gtalumni', 'ramblinwreck', 'oie.gatech.edu', 'pe.gatech.edu', 'gnpec.georgia.gov', 'calendar.gatech.edu', 'specialevents.gatech.edu', 'lifetimelearning.gatech.edu', 'forms', 'faq', 'resources', 'news', 'events', 'advising', 'student', 'staff', 'alumni', 'office', 'overview', 'information', 'handbook', 'contact', 'graduate', 'undergraduate', 'professional-education', 'financial-aid', 'calendar', 'specialevents', 'study-abroad', 'lifetimelearning', 'tickets', 'tech-lingo', 'directory1'])):
                    profile_url = 'N/A'
                prof.update({
                    'email': fac.get('email', 'N/A'),
                    'department': fac.get('department', 'N/A'),
                    'school': fac.get('school', 'N/A'),
                    'research_interests': fac.get('research_interests', 'N/A'),
                    'lab_affiliation': fac.get('lab_affiliation', 'N/A'),
                    'personal_website': fac.get('personal_website', 'N/A'),
                    'profile_url': profile_url if profile_url else 'N/A',
                    'publications': fac.get('publications', [])
                })
            enriched_results.append(prof)

        # Try to match Perplexity answer sections to professors (if possible)
        prof_summaries = {}
        for line in paras:
            for prof in enriched_results:
                if prof.get('name') and prof['name'] in line:
                    prof_summaries[prof['name']] = line[:350]
        for prof in enriched_results:
            prof['perplexity_excerpt'] = prof_summaries.get(prof.get('name'), '')
        return jsonify({'short_answer': short_answer, 'professors': enriched_results, 'query': query})
    else:
        return jsonify({'error': f'Perplexity API error: {resp.status_code}', 'details': resp.text}), 500


# --- New endpoints for professor search ---
@app.route('/find_professors', methods=['POST'])
def find_professors():
    import requests
    from flask import request, jsonify
    data = request.get_json()
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'professors': [], 'error': 'Please enter a search term (school, field, or both).'}), 200
    # Use OpenAlex search parameter for fuzzy matching
    authors_url = f'https://api.openalex.org/authors?search={requests.utils.quote(query)}&per-page=10&sort=cited_by_count:desc'
    print(f'[DEBUG] Authors URL: {authors_url}')
    authors_resp = requests.get(authors_url)
    if authors_resp.status_code == 200:
        authors_data = authors_resp.json()
        profs = []
        for author in authors_data.get('results', []):
            name = author.get('display_name', '').strip()
            if not name or len(name) < 3:
                continue
            affiliation = author.get('last_known_institution', {}).get('display_name', '')
            email = author.get('email', None)
            works_url = f'https://api.openalex.org/works?filter=author.id:{author["id"]}&sort=publication_year:desc&per-page=3'
            works_resp = requests.get(works_url)
            papers = []
            if works_resp.status_code == 200:
                works_data = works_resp.json()
                for work in works_data.get('results', []):
                    papers.append({
                        'title': work.get('display_name', ''),
                        'year': work.get('publication_year', ''),
                        'url': work.get('id', ''),
                        'venue': work.get('host_venue', {}).get('display_name', ''),
                        'authors': [a.get('author', {}).get('display_name', '') for a in work.get('authorships', [])]
                    })
            profs.append({
                'name': name,
                'affiliations': [affiliation],
                'email': email,
                'matching_papers': papers,
                'research_interests': [c['display_name'] for c in author.get('x_concepts', [])]
            })
            if len(profs) >= 10:
                break
        if profs:
            return jsonify({'professors': profs, 'query_used': query})
        else:
            return jsonify({'professors': [], 'error': f'No professors found matching "{query}".'}), 200
    else:
        return jsonify({'professors': [], 'error': 'Error connecting to OpenAlex API.'}), 500
    concept_id = None
    concept_name = None
    concept_raw_responses = []
    for f in mapped_fields:
        concept_url = f'https://api.openalex.org/concepts?search={f}&per-page=1'
        concept_resp = requests.get(concept_url)
        concept_raw_responses.append({'field': f, 'url': concept_url, 'status': concept_resp.status_code, 'response': concept_resp.text})
        if concept_resp.status_code != 200:
            continue
        concept_data = concept_resp.json()
        if concept_data.get('results'):
            concept_id = concept_data['results'][0]['id']
            concept_name = concept_data['results'][0]['display_name']
            print(f"[DEBUG] Concept: {concept_name} (ID: {concept_id})")
            # Print the full OpenAlex concept API response for debugging
            print(f"[DEBUG] Full concept API response for {concept_name}: {concept_data['results'][0]}")
            break
    if not concept_id:
        # Suggest closest concepts
        suggest_url = f'https://api.openalex.org/concepts?search={field}&per-page=5'
        suggest_resp = requests.get(suggest_url)
        if suggest_resp.status_code == 200 and suggest_resp.json().get('results'):
            suggestions = [c['display_name'] for c in suggest_resp.json()['results']]
            return jsonify({'error': f'No field found matching "{field}". Did you mean one of: {', '.join(suggestions)}?', 'debug': {'institution': inst_data, 'concept_attempts': concept_raw_responses}}), 404
        return jsonify({'error': f'No field found matching "{field}".', 'debug': {'institution': inst_data, 'concept_attempts': concept_raw_responses}}), 404

    # 3. Get authors at the institution with this concept
    authors_url = f'https://api.openalex.org/authors?filter=last_known_institutions.id:{inst_id},x_concepts.id:{concept_id}&per-page=10&sort=cited_by_count:desc'
    print(f'[DEBUG] Authors URL: {authors_url}')
    authors_resp = requests.get(authors_url)
    print(f'[DEBUG] Authors Response Status: {authors_resp.status_code}')
    authors_data = authors_resp.json() if authors_resp.status_code == 200 else {}
    profs = []
    fallback_used = None
    if authors_data.get('results'):
        fallback_used = 'institution+field'
        print(f"[DEBUG] Fallback used: {fallback_used}")
        for author in authors_data['results']:
            # Only include authors with a real name and institution match
            name = author.get('display_name', '').strip()
            if not name or len(name) < 3:
                continue
            affiliation = author.get('last_known_institution', {}).get('display_name', '')
            if not affiliation or school.lower() not in affiliation.lower():
                continue
            # Get email if available (OpenAlex rarely has this)
            email = author.get('email', None)
            # Get top 3 recent papers
            works_url = f'https://api.openalex.org/works?filter=author.id:{author["id"]}&sort=publication_year:desc&per-page=3'
            works_resp = requests.get(works_url)
            papers = []
            if works_resp.status_code == 200:
                works_data = works_resp.json()
                for work in works_data.get('results', []):
                    papers.append({
                        'title': work.get('display_name', ''),
                        'year': work.get('publication_year', ''),
                        'url': work.get('id', ''),
                        'venue': work.get('host_venue', {}).get('display_name', ''),
                        'authors': [a.get('author', {}).get('display_name', '') for a in work.get('authorships', [])]
                    })
            profs.append({
                'name': name,
                'affiliations': [affiliation],
                'email': email,
                'matching_papers': papers,
                'research_interests': [c['display_name'] for c in author.get('x_concepts', [])]
            })
            if len(profs) >= 5:
                break
    else:
        # (2) Fallback: Try all subfields/related concepts
        parent_data = concept_resp.json() if concept_resp.status_code == 200 else {}
        subfields = []
        subfields_key = None
        if parent_data.get('related_concepts') and len(parent_data['related_concepts']) > 0:
            subfields = parent_data['related_concepts']
            subfields_key = 'related_concepts'
        elif parent_data.get('children') and len(parent_data['children']) > 0:
            subfields = parent_data['children']
            subfields_key = 'children'
        elif parent_data.get('ancestors') and len(parent_data['ancestors']) > 0:
            subfields = parent_data['ancestors']
            subfields_key = 'ancestors'
        print(f'[DEBUG] Using {subfields_key} as subfields')
        subfield_results = []
        if subfields:
            for sub in subfields:
                sub_id_url = sub.get('id') or sub.get('openalex')
                if not sub_id_url:
                    continue
                sub_id = sub_id_url.split('/')[-1]
                sub_name = sub.get('display_name', 'Unknown')
                sub_authors_url = f'https://api.openalex.org/authors?filter=last_known_institutions.id:{inst_id},x_concepts.id:{sub_id}&per-page=5&sort=cited_by_count:desc'
                sub_authors_resp = requests.get(sub_authors_url)
                if sub_authors_resp.status_code == 200:
                    sub_authors_data = sub_authors_resp.json()
                    for author in sub_authors_data.get('results', []):
                        subfield_results.append((sub_name, author))
            if subfield_results:
                fallback_used = 'subfields'
                print(f"[DEBUG] Fallback used: {fallback_used}")
                profs = []
                seen = set()
                for sub_name, author in subfield_results:
                    name = author.get('display_name', '').strip()
                    if not name or len(name) < 3 or name in seen:
                        continue
                    seen.add(name)
                    affiliation = author.get('last_known_institution', {}).get('display_name', '')
                    email = author.get('email', None)
                    works_url = f'https://api.openalex.org/works?filter=author.id:{author["id"]}&sort=publication_year:desc&per-page=3'
                    works_resp = requests.get(works_url)
                    papers = []
                    if works_resp.status_code == 200:
                        works_data = works_resp.json()
                        for work in works_data.get('results', []):
                            papers.append({
                                'title': work.get('display_name', ''),
                                'year': work.get('publication_year', ''),
                                'url': work.get('id', ''),
                                'venue': work.get('host_venue', {}).get('display_name', ''),
                                'authors': [a.get('author', {}).get('display_name', '') for a in work.get('authorships', [])]
                            })
                    profs.append({
                        'name': name,
                        'affiliations': [affiliation],
                        'email': email,
                        'matching_papers': papers,
                        'research_interests': [c['display_name'] for c in author.get('x_concepts', [])],
                        'source_field': sub_name
                    })
                    if len(profs) >= 10:
                        break
                if profs:
                    return jsonify({'institution_used': inst_name, 'professors': profs, 'fallback': 'subfields', 'fallback_fields': list(set([p['source_field'] for p in profs]))})
        # (3) Fallback: Show all professors at institution
        all_inst_url = f'https://api.openalex.org/authors?filter=last_known_institutions.id:{inst_id}&per-page=10&sort=cited_by_count:desc'
        all_inst_resp = requests.get(all_inst_url)
        all_inst_data = all_inst_resp.json() if all_inst_resp.status_code == 200 else {}
        if all_inst_data.get('results'):
            fallback_used = 'institution_only'
            print(f"[DEBUG] Fallback used: {fallback_used}")
            profs = []
            seen = set()
            for author in all_inst_data['results']:
                name = author.get('display_name', '').strip()
                if not name or len(name) < 3 or name in seen:
                    continue
                seen.add(name)
                affiliation = author.get('last_known_institution', {}).get('display_name', '')
                email = author.get('email', None)
                works_url = f'https://api.openalex.org/works?filter=author.id:{author["id"]}&sort=publication_year:desc&per-page=3'
                works_resp = requests.get(works_url)
                papers = []
                if works_resp.status_code == 200:
                    works_data = works_resp.json()
                    for work in works_data.get('results', []):
                        papers.append({
                            'title': work.get('display_name', ''),
                            'year': work.get('publication_year', ''),
                            'url': work.get('id', ''),
                            'venue': work.get('host_venue', {}).get('display_name', ''),
                            'authors': [a.get('author', {}).get('display_name', '') for a in work.get('authorships', [])]
                        })
                profs.append({
                    'name': name,
                    'affiliations': [affiliation],
                    'email': email,
                    'matching_papers': papers,
                    'research_interests': [c['display_name'] for c in author.get('x_concepts', [])]
                })
                if len(profs) >= 10:
                    break
            if profs:
                return jsonify({'institution_used': inst_name, 'professors': profs, 'fallback': 'institution_only'})
        # (4) Fallback: Show all in field, filter for institution
        all_field_url = f'https://api.openalex.org/authors?filter=x_concepts.id:{concept_id}&per-page=20&sort=cited_by_count:desc'
        all_field_resp = requests.get(all_field_url)
        all_field_data = all_field_resp.json() if all_field_resp.status_code == 200 else {}
        filtered = []
        if all_field_data.get('results'):
            for author in all_field_data['results']:
                affil = author.get('last_known_institution', {}).get('display_name', '')
                if school.lower() in affil.lower():
                    filtered.append(author)
        if filtered:
            fallback_used = 'field_only_filtered_by_institution'
            print(f"[DEBUG] Fallback used: {fallback_used}")
            profs = []
            seen = set()
            for author in filtered:
                name = author.get('display_name', '').strip()
                if not name or len(name) < 3 or name in seen:
                    continue
                seen.add(name)
                affiliation = author.get('last_known_institution', {}).get('display_name', '')
                email = author.get('email', None)
                works_url = f'https://api.openalex.org/works?filter=author.id:{author["id"]}&sort=publication_year:desc&per-page=3'
                works_resp = requests.get(works_url)
                papers = []
                if works_resp.status_code == 200:
                    works_data = works_resp.json()
                    for work in works_data.get('results', []):
                        papers.append({
                            'title': work.get('display_name', ''),
                            'year': work.get('publication_year', ''),
                            'url': work.get('id', ''),
                            'venue': work.get('host_venue', {}).get('display_name', ''),
                            'authors': [a.get('author', {}).get('display_name', '') for a in work.get('authorships', [])]
                        })
                profs.append({
                    'name': name,
                    'affiliations': [affiliation],
                    'email': email,
                    'matching_papers': papers,
                    'research_interests': [c['display_name'] for c in author.get('x_concepts', [])]
                })
                if len(profs) >= 10:
                    break
            else:
                for sub in subfields:
                    # Extract the short concept ID from the full OpenAlex URL
                    sub_id_url = sub.get('id') or sub.get('openalex')
                    if not sub_id_url:
                        print('[DEBUG] Skipping subfield with missing id:', sub)
                        continue
                    sub_id = sub_id_url.split('/')[-1]
                    sub_name = sub.get('display_name', 'Unknown')
                    print(f'[DEBUG] Subfield: {sub_name}, sub_id: {sub_id}')
                    sub_authors_url = f'https://api.openalex.org/authors?filter=last_known_institutions.id:{inst_id},x_concepts.id:{sub_id}&per-page=5&sort=cited_by_count:desc'
                    sub_authors_resp = requests.get(sub_authors_url)
                    if sub_authors_resp.status_code == 200:
                        sub_authors_data = sub_authors_resp.json()
                        for author in sub_authors_data.get('results', []):
                            subfield_results.append((sub_name, author))
                if not subfield_results:
                    print('[DEBUG] No professors found for any subfields.')
                else:
                    print(f'[DEBUG] Found {len(subfield_results)} professors in subfields.')
                if subfield_results:
                    # Combine results and return
                    profs = []
                    seen = set()
                    for sub_name, author in subfield_results:
                        name = author.get('display_name', '').strip()
                        if not name or len(name) < 3 or name in seen:
                            continue
                        seen.add(name)
                        affiliation = author.get('last_known_institution', {}).get('display_name', '')
                        email = author.get('email', None)
                        works_url = f'https://api.openalex.org/works?filter=author.id:{author["id"]}&sort=publication_year:desc&per-page=3'
                        works_resp = requests.get(works_url)
                        papers = []
                        if works_resp.status_code == 200:
                            works_data = works_resp.json()
                            for work in works_data.get('results', []):
                                papers.append({
                                    'title': work.get('display_name', ''),
                                    'year': work.get('publication_year', ''),
                                    'url': work.get('id', ''),
                                    'venue': work.get('host_venue', {}).get('display_name', ''),
                                    'authors': [a.get('author', {}).get('display_name', '') for a in work.get('authorships', [])]
                                })
                        profs.append({
                            'name': name,
                            'affiliations': [affiliation],
                            'email': email,
                            'matching_papers': papers,
                            'research_interests': [c['display_name'] for c in author.get('x_concepts', [])],
                            'source_field': sub_name
                        })
                        if len(profs) >= 10:
                            break
                    if profs:
                        fallback_used = 'subfields'
                        print(f"[DEBUG] Fallback used: {fallback_used}")
                        return jsonify({'institution_used': inst_name, 'professors': profs, 'fallback': 'subfields', 'fallback_fields': list(set([p['source_field'] for p in profs]))})
                # If subfields existed but no professors were found, fallback to all professors
                print('[DEBUG] Subfields existed but no professors found, falling back to all_professors.')
            # (Fallback 2) Try parent field
            if parent_data.get('ancestors'):
                parent_concept = parent_data['ancestors'][0]
                parent_id = parent_concept['id']
                parent_name = parent_concept['display_name']
                print(f"[DEBUG] Parent Concept: {parent_name} (ID: {parent_id})")
                authors_url_parent = f'https://api.openalex.org/authors?filter=last_known_institutions.id:{inst_id},x_concepts.id:{parent_id}&per-page=10&sort=cited_by_count:desc'
                authors_resp_parent = requests.get(authors_url_parent)
                print(f"[DEBUG] Parent Authors URL: {authors_url_parent}")
                print(f"[DEBUG] Parent Authors Response Status: {authors_resp_parent.status_code}")
                if authors_resp_parent.status_code == 200:
                    authors_data_parent = authors_resp_parent.json()
                    if authors_data_parent.get('results'):
                        authors_data = authors_data_parent
                        concept_name = parent_name
                        fallback_used = 'parent_field'
                        print(f"[DEBUG] Fallback used: {fallback_used}")
                        # continue to normal processing below
        # (3) If still no results, show all professors at the institution
        if not authors_data.get('results'):
            print(f"[DEBUG] Fallback used: all_professors")
            all_authors_url = f'https://api.openalex.org/authors?filter=last_known_institutions.id:{inst_id}&per-page=10&sort=cited_by_count:desc'
            all_authors_resp = requests.get(all_authors_url)
            all_profs = []
            if all_authors_resp.status_code == 200:
                all_authors_data = all_authors_resp.json()
                for author in all_authors_data.get('results', []):
                    name = author.get('display_name', '').strip()
                    if not name or len(name) < 3:
                        continue
                    affiliation = author.get('last_known_institution', {}).get('display_name', '')
                    email = author.get('email', None)
                    works_url = f'https://api.openalex.org/works?filter=author.id:{author["id"]}&sort=publication_year:desc&per-page=3'
                    works_resp = requests.get(works_url)
                    papers = []
                    if works_resp.status_code == 200:
                        works_data = works_resp.json()
                        for work in works_data.get('results', []):
                            papers.append({
                                'title': work.get('display_name', ''),
                                'year': work.get('publication_year', ''),
                                'url': work.get('id', ''),
                                'venue': work.get('host_venue', {}).get('display_name', ''),
                                'authors': [a.get('author', {}).get('display_name', '') for a in work.get('authorships', [])]
                            })
                    all_profs.append({
                        'name': name,
                        'affiliations': [affiliation],
                        'email': email,
                        'matching_papers': papers,
                        'research_interests': [c['display_name'] for c in author.get('x_concepts', [])],
                        'source_field': None
                    })
                    if len(all_profs) >= 10:
                        break
                if all_profs:
                    return jsonify({'institution_used': inst_name, 'professors': all_profs, 'fallback': 'all_professors'}), 200
            # (4) Suggest most common fields at the institution
            inst_concepts_url = f'https://api.openalex.org/institutions/{inst_id}'
            inst_concepts_resp = requests.get(inst_concepts_url)
            inst_concepts = []
            if inst_concepts_resp.status_code == 200:
                inst_concepts_data = inst_concepts_resp.json()
                if inst_concepts_data.get('x_concepts'):
                    inst_concepts = [c['display_name'] for c in inst_concepts_data['x_concepts'][:5]]
            # Always return something, never a 404, if we get here
            print('[DEBUG] No professors found for field, subfields, or all_professors. Returning empty list.')
            return jsonify({'institution_used': inst_name, 'professors': [], 'fallback': 'none', 'suggested_fields': inst_concepts, 'error': f'No professors found for "{inst_name}" in field "{concept_name or field}".'}), 200

    profs = []
    for author in authors_data['results']:
        # Only include authors with a real name and institution match
        name = author.get('display_name', '').strip()
        if not name or len(name) < 3:
            continue
        affiliation = author.get('last_known_institution', {}).get('display_name', '')
        if not affiliation or school.lower() not in affiliation.lower():
            continue
        # Get email if available (OpenAlex rarely has this)
        email = author.get('email', None)
        # Get top 3 recent papers
        works_url = f'https://api.openalex.org/works?filter=author.id:{author["id"]}&sort=publication_year:desc&per-page=3'
        works_resp = requests.get(works_url)
        papers = []
        if works_resp.status_code == 200:
            works_data = works_resp.json()
            for work in works_data.get('results', []):
                papers.append({
                    'title': work.get('display_name', ''),
                    'year': work.get('publication_year', ''),
                    'url': work.get('id', ''),
                    'venue': work.get('host_venue', {}).get('display_name', ''),
                    'authors': [a.get('author', {}).get('display_name', '') for a in work.get('authorships', [])]
                })
        profs.append({
            'name': name,
            'affiliations': [affiliation],
            'email': email,
            'matching_papers': papers,
            'research_interests': [c['display_name'] for c in author.get('x_concepts', [])]
        })
        if len(profs) >= 5:
            break
    if not profs:
        return jsonify({'error': f'No professors found for "{inst_name}" in field "{field}".'}), 404
    return jsonify({'institution_used': inst_name, 'professors': profs})

# --- Helper functions for summarization and overlap ---
def summarize_with_hf(text):
    import os
    import requests as py_requests
    api_url = 'https://api-inference.huggingface.co/models/deepseek-ai/deepseek-llm-7b-chat'
    headers = {"Authorization": f"Bearer {os.getenv('HF_API_KEY', '')}"}
    payload = {"inputs": f"Summarize this academic abstract: {text}"}
    resp = py_requests.post(api_url, headers=headers, json=payload, timeout=20)
    if resp.status_code == 200:
        try:
            return resp.json()[0]['generated_text']
        except Exception:
            return ''
    return ''

def compute_overlap(user_interest, concepts):
    # Simple overlap: check if any user interest keywords appear in concepts
    user_words = set(user_interest.lower().split())
    concept_words = set(' '.join(concepts).lower().split())
    overlap = user_words & concept_words
    return ', '.join(overlap) if overlap else ''

@app.route('/get_professor_papers', methods=['POST'])
def get_professor_papers():
    import os
    author_id = request.form.get('author_id')
    user_interest = request.form.get('user_interest', '')
    # Get 3 most recent papers for this author from OpenAlex
    works_url = f'https://api.openalex.org/works'
    params = {
        'filter': f'authorships.author.id:{author_id}',
        'sort': 'publication_date:desc',
        'per-page': 3
    }
    resp = requests.get(works_url, params=params)
    papers = []
    if resp.status_code == 200:
        for w in resp.json().get('results', []):
            title = w.get('title', '')
            abstract = w.get('abstract', '')
            doi = w.get('doi', '')
            url = w.get('primary_location', {}).get('url', '')
            pdf_url = w.get('primary_location', {}).get('pdf_url', '')
            citation_count = w.get('cited_by_count', 0)
            concepts = [c['display_name'] for c in w.get('concepts', [])]
            # Summarize abstract
            summary = summarize_with_hf(abstract)
            # Compute overlap with user interest
            overlap = ''
            if user_interest:
                overlap = compute_overlap(user_interest, concepts)
            papers.append({
                'title': title,
                'abstract': abstract,
                'summary': summary,
                'doi': doi,
                'url': url,
                'pdf_url': pdf_url,
                'citation_count': citation_count,
                'concepts': concepts,
                'overlap': overlap
            })
    # Reconstruct abstract if needed
    for p in papers:
        if isinstance(p['abstract'], dict):
            idx = p['abstract']
            words = sorted(idx.items(), key=lambda x: x[1][0])
            p['abstract'] = ' '.join([w for w, pos in words])
    return jsonify(papers)

# --- End new endpoints ---

def get_hf_token():
    # Load HuggingFace API token from config.yaml
    import yaml
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    return config.get('huggingface_token', None)

@app.route('/summarize', methods=['POST'])
def summarize():
    abstract = request.form.get('abstract')
    print(f"Received abstract: {abstract}")  # Debug log
    if not abstract:
        print("No abstract provided!")
        return jsonify({'error': 'No abstract provided'}), 400
    hf_token = get_hf_token()
    if not hf_token:
        print("No HuggingFace token found!")
        return jsonify({'error': 'No HuggingFace API token found in config.yaml'}), 403
    headers = {"Authorization": f"Bearer {hf_token}"}
    payload = {"inputs": abstract}
    hf_url = "https://api-inference.huggingface.co/models/deepseek-ai/deepseek-llm-7b-instruct"
    response = requests.post(hf_url, headers=headers, json=payload)
    print(f"HuggingFace response: {response.status_code} {response.text}")  # Debug log
    if response.status_code != 200:
        return jsonify({'summary': abstract, 'error': 'Summarization failed'}), 500
    try:
        summary = response.json()[0]['generated_text']
    except Exception as e:
        print(f"Error parsing summary: {e}")
        summary = abstract
    return jsonify({'summary': summary})

def search_arxiv(query, max_results=3):
    url = f'http://export.arxiv.org/api/query?search_query=all:{query}&start=0&max_results={max_results}'
    response = requests.get(url)
    entries = []
    if response.status_code == 200:
        root = ET.fromstring(response.text)
        for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
            title = entry.find('{http://www.w3.org/2005/Atom}title').text.strip()
            authors = [a.find('{http://www.w3.org/2005/Atom}name').text for a in entry.findall('{http://www.w3.org/2005/Atom}author')]
            summary = entry.find('{http://www.w3.org/2005/Atom}summary').text.strip()
            url = entry.find('{http://www.w3.org/2005/Atom}id').text
            entries.append({
                'title': title,
                'authors': [{'name': n} for n in authors],
                'abstract': summary,
                'url': url
            })
    return entries

def search_openalex(query, per_page=3):
    url = 'https://api.openalex.org/works'
    params = {'search': query, 'per-page': per_page}
    response = requests.get(url, params=params)
    results = []
    if response.status_code == 200:
        for item in response.json().get('results', []):
            title = item.get('title', '')
            authors = [{'name': a['author']['display_name']} for a in item.get('authorships', [])]
            # Fix: reconstruct abstract from abstract_inverted_index if present
            abstract = ''
            if 'abstract' in item and item['abstract']:
                abstract = item['abstract']
            elif 'abstract_inverted_index' in item and item['abstract_inverted_index']:
                idx = item['abstract_inverted_index']
                # Reconstruct the abstract in the correct order
                words = sorted(idx.items(), key=lambda x: x[1][0])
                abstract = ' '.join([w for w, pos in words])
            url = item.get('id', '')
            results.append({
                'title': title,
                'authors': authors,
                'abstract': abstract,
                'url': url
            })
    return results

@app.route("/")
def index():
    return render_template("index.html")

from scholarly import scholarly

def search_google_scholar(query, max_results=5):
    results = scholarly.search_pubs(query)
    papers = []
    for i, paper in enumerate(results):
        if i >= max_results:
            break
        bib = paper.get("bib", {})
        papers.append({
            "title": bib.get("title", ""),
            "authors": [{"name": bib.get("author", "")}],
            "abstract": bib.get("abstract", ""),
            "url": paper.get("pub_url", "")
        })
    return papers

@app.route("/search", methods=["POST"])
def search():
    query = request.form.get("query")
    source = request.form.get("source", "both")
    if not query:
        return jsonify({"error": "No query provided."}), 400
    results = []
    if source == "arxiv":
        results = search_arxiv(query, max_results=20)
    elif source == "openalex":
        results = search_openalex(query, per_page=20)
    elif source == "googlescholar":
        results = search_google_scholar(query, max_results=5)
    else:  # both (arxiv + openalex)
        results = search_arxiv(query, max_results=20) + search_openalex(query, per_page=20)
    return jsonify(results)

from ga_tech_scraper import extract_professor_info

@app.route('/enrich_perplexity_professors', methods=['POST'])
def enrich_perplexity_professors():
    data = request.get_json()
    professor_names = data.get('professor_names', [])
    school_name = data.get('school_name', 'Georgia Tech')
    results = []
    for name in professor_names:
        try:
            # Dummy profile URL and soup for now; ideally, you'd scrape the actual profile page
            # For demo, just pass name and school
            prof_info = extract_professor_info(None, name, '', school_name)
            results.append(prof_info)
        except Exception as e:
            results.append({'name': name, 'error': str(e)})
    return jsonify({'professors': results})

if __name__ == "__main__":
    app.run(debug=True)
