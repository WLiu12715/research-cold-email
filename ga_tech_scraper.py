import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urlparse, urljoin
from scholarly import scholarly

def get_publications_from_google_scholar(name, affiliation="Georgia Tech"):
    """Get publications for a professor using Google Scholar via scholarly"""
    try:
        print(f"Searching Google Scholar for {name} at {affiliation}...")
        # Search for the author
        search_query = scholarly.search_author(f"{name} {affiliation}")
        
        # Try to get the first author result
        author = next(search_query, None)
        
        if not author:
            print(f"No Google Scholar profile found for {name}")
            return []
            
        # Fill in all available details for the author
        try:
            author = scholarly.fill(author)
            
            # Get the publications (limit to top 5 most cited)
            publications = sorted(
                author.get('publications', []), 
                key=lambda x: x.get('num_citations', 0), 
                reverse=True
            )[:5]
            
            # Extract publication titles
            publication_titles = []
            for pub in publications:
                if 'bib' in pub and 'title' in pub['bib']:
                    publication_titles.append(pub['bib']['title'])
                    
            print(f"Found {len(publication_titles)} publications for {name} on Google Scholar")
            return publication_titles
            
        except Exception as e:
            print(f"Error filling author details for {name}: {e}")
            return []
            
    except Exception as e:
        print(f"Error searching Google Scholar for {name}: {e}")
        
    return []

def scrape_ga_tech_faculty():
    """Scrape Georgia Tech College of Computing faculty information"""
    base_url = "https://www.cc.gatech.edu"
    
    # Schools to scrape within cc.gatech.edu domain
    schools = [
        {"name": "College of Computing (General)", "url": f"{base_url}/people/faculty"}
    ]
    
    # School-specific domains - these have their own websites
    school_specific_urls = [
        {"name": "School of Interactive Computing", "url": "https://ic.gatech.edu/people/faculty"},
        {"name": "School of Computer Science", "url": "https://scs.gatech.edu/people/faculty"},
        {"name": "School of Computational Science and Engineering", "url": "https://cse.gatech.edu/people/faculty"},
        {"name": "School of Cybersecurity and Privacy", "url": "https://scp.gatech.edu/people/faculty"}
    ]
    
    # Add all schools to our list
    schools.extend(school_specific_urls)
    
    # Dictionary to store professor information, using URLs as keys to avoid duplicates
    professors_dict = {}
    
    # Process each school
    for school in schools:
        school_name = school["name"]
        faculty_url = school["url"]
        
        # Try to fetch all faculty members at once by adding a large items_per_page parameter
        all_faculty_url = f"{faculty_url}?items_per_page=1000"
        print(f"\nAttempting to fetch faculty from {school_name} at {all_faculty_url}")
        
        try:
            resp = requests.get(all_faculty_url)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Save HTML to help with debugging (just for the first school)
            if school_name == "College of Computing (General)":
                with open('faculty_page.html', 'w', encoding='utf-8') as f:
                    f.write(soup.prettify())
                print("Saved faculty page HTML for debugging")
                    
            # Process the faculty page and find faculty links
            # Extract base domain from the URL
            school_url = school["url"]
            if school_url.startswith('http'):
                # For full URLs, parse the domain
                parsed_url = urlparse(school_url)
                school_base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            else:
                # For relative URLs, use the base_url
                school_base_url = base_url
                
            faculty_links = process_faculty_page(soup, school_name, school_base_url)
            
            # Follow pagination if needed
            current_page = 0
            while True:
                current_page += 1
                # Look for "next" link in pagination
                next_link = soup.select_one('a[rel="next"], li.pager__item--next a, a.pager-next')
                if next_link and 'href' in next_link.attrs:
                    next_url = next_link['href']
                    # Make sure it's a full URL
                    if next_url.startswith('/'):
                        next_url = base_url + next_url
                    elif not next_url.startswith(('http://', 'https://')):
                        next_url = base_url + '/' + next_url
                        
                    print(f"Fetching page {current_page + 1} from {next_url}")
                    try:
                        next_resp = requests.get(next_url)
                        soup = BeautifulSoup(next_resp.text, 'html.parser')
                        
                        # Process the next page
                        new_links = process_faculty_page(soup, school_name, school_base_url)
                        if new_links:
                            faculty_links.extend(new_links)
                            print(f"Total faculty links found so far in {school_name}: {len(faculty_links)}")
                        else:
                            print("No new faculty links found on this page. Stopping pagination.")
                            break
                            
                        # Add a small delay between requests to be respectful
                        time.sleep(1)
                    except Exception as e:
                        print(f"Error fetching next page: {e}")
                        break
                else:
                    print("No more pagination links found.")
                    break
            
            # Process all faculty from this school
            print(f"Found {len(faculty_links)} faculty in {school_name}")
            process_faculty_profiles(faculty_links, professors_dict, base_url, school_name)
            
        except Exception as e:
            print(f"Error processing {school_name}: {e}")
    
    # Convert dictionary to list for output
    professors = list(professors_dict.values())
    return professors


def process_faculty_page(page_soup, school_name, base_url):
    """Process a faculty directory page to extract faculty links"""
    page_faculty_links = []
    
    # Try multiple selectors for different site structures
    selectors = [
        # Original GT CoC selectors
        'div.views-row div.profile-card__content a[href*="/people/"]',
        'div.views-row a[href*="/people/"]',
        # Common faculty directory selectors
        'div.faculty-listing a',
        'div.directory-listing a',
        'div.faculty-card a',
        'div.people-listing a',
        # Generic article/content selectors
        'article h3 a',
        'div.content a[href*="/faculty/"]',
        'div.content a[href*="/profile/"]',
        # Really broad fallbacks
        'a[href*="/faculty/"]',
        'a[href*="/profile/"]',
        'a[href*="/people/"]'
    ]
    
    # Try each selector in order of specificity
    for selector in selectors:
        faculty_links = page_soup.select(selector)
        valid_links = []
        
        # Filter links to exclude navigation links
        for link in faculty_links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # Skip navigation links, empty links, or overly short names
            if (not text or len(text) < 4 or ' ' not in text or 
                any(x in text.lower() for x in ['faculty', 'staff', 'student', 'alumni', 'board', 'people', 'directory'])):
                continue
            
            # Make sure it looks like a person name (contains a space, not too short)
            if len(text.split()) >= 2:
                valid_links.append(link)
        
        if valid_links:
            print(f"Found {len(valid_links)} faculty links using selector '{selector}' for {school_name}")
            page_faculty_links.extend(valid_links)
            break
    
    # If still no links found, try an even more general approach with all links that might be faculty
    if not page_faculty_links:
        all_links = page_soup.select('a')
        for link in all_links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # Only include links that look like individual faculty profiles (e.g., names with spaces)
            if (text and len(text) > 5 and ' ' in text and 
                not any(x in text.lower() for x in ['faculty', 'staff', 'student', 'alumni', 'board', 'people']) and
                not href.startswith('#') and
                not href.startswith('mailto:') and
                not any(x in href.lower() for x in ['index', 'search', 'contact', 'about', 'home', 'catalog'])):
                # If the name looks like a person (contains at least a first and last name)
                if len(text.split()) >= 2:
                    page_faculty_links.append(link)
        
        if page_faculty_links:
            print(f"Fallback: Found {len(page_faculty_links)} potential faculty links in {school_name}")
    
    return page_faculty_links


def process_faculty_profiles(faculty_links, professors_dict, base_url, school_name):
    """Process faculty profiles and add them to the professors dictionary"""
    # Limit for testing if needed
    # MAX_FACULTY = 5
    # if len(faculty_links) > MAX_FACULTY:
    #     print(f"Limiting to first {MAX_FACULTY} faculty members for testing")
    #     faculty_links = faculty_links[:MAX_FACULTY]
    
    for i, faculty_link in enumerate(faculty_links):
        name = faculty_link.get_text(strip=True)
        href = faculty_link.get('href')
        
        # Make sure href is a valid URL
        if href.startswith(('http://', 'https://')):
            profile_url = href  # Already absolute URL
        else:
            # Use urljoin to handle both relative URLs and path-absolute URLs
            profile_url = urljoin(base_url, href)
            
        # Skip if we've already processed this professor
        if profile_url in professors_dict:
            print(f"Skipping duplicate professor: {name} at {profile_url}")
            continue
            
        print(f"Processing {i+1}/{len(faculty_links)} in {school_name}: {name} at {profile_url}")
        
        try:
            prof_resp = requests.get(profile_url)
            prof_soup = BeautifulSoup(prof_resp.text, 'html.parser')
            
            # Extract info using our existing extraction logic
            professor_data = extract_professor_info(prof_soup, name, profile_url, school_name, base_url)
            
            # Add to our dictionary with profile URL as key to avoid duplicates
            professors_dict[profile_url] = professor_data
            print(f"Successfully processed {name} from {school_name}")
            
            # Be respectful with rate limiting
            time.sleep(1)
            
        except Exception as e:
            print(f"Error processing {name} from {school_name}: {e}")
            
    return professors_dict


def extract_professor_info(prof_soup, name, profile_url, school_name, base_url="https://www.cc.gatech.edu"):
    """Extract all information for a professor from their profile page"""
    # Save profile HTML for debugging (uncomment if needed)
    # with open(f'profile_{name.replace(" ", "_")}.html', 'w', encoding='utf-8') as f:
    #     f.write(prof_soup.prettify())
    
    # Extract all content as text for analysis
    page_text = prof_soup.get_text(" ", strip=True)
    
    # Name (from profile page)
    name_tag = prof_soup.select_one('h1.page-title span') or prof_soup.select_one('h1.page-title')
    if name_tag:
        name = name_tag.get_text(strip=True)
    
    # Email - Try different approaches
    email = None
    # 1. Look for mailto links
    email_tag = prof_soup.select_one('a[href^="mailto:"]')
    if email_tag:
        email = email_tag.get_text(strip=True)
    
    # 2. Look for text that matches email pattern
    if not email:
        email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', page_text)
        if email_match:
            email = email_match.group(0)
    
    # Department/School - Use the school name from our crawl or look for more specific info
    department = school_name  # Default to the school we're currently crawling
    dept_tags = prof_soup.select('a[href^="/school/"]')
    if dept_tags:
        department = dept_tags[0].get_text(strip=True)
    
    # Research Interests - Try multiple approaches
    research_interests = None
    # 1. Look for card-block text with Research Areas
    for p in prof_soup.select('p'):
        if p.find('strong') and 'Research Areas' in p.get_text():
            interest_text = p.get_text(strip=True)
            # Extract text after "Research Areas:" label
            if ':' in interest_text:
                research_interests = interest_text.split(':', 1)[1].strip()
    
    # 2. Look for any sections that might contain research information
    if not research_interests:
        research_sections = []
        for elem in prof_soup.find_all(['h2', 'h3', 'h4', 'strong']):
            text = elem.get_text(strip=True).lower()
            if any(term in text for term in ['research', 'interests', 'areas', 'expertise']):
                if elem.find_next_sibling():
                    research_sections.append(elem.find_next_sibling().get_text(strip=True))
        if research_sections:
            research_interests = '; '.join(research_sections)
    
    # Personal Website - Comprehensive detection
    website = None
    professor_first_name = name.split()[0].lower()
    professor_last_name = name.split()[-1].lower()
    
    # Strategy 1: Look for links with explicit website-related text
    for a in prof_soup.select('a'):
        href = a.get('href', '')
        text = a.get_text(strip=True).lower()
        # Only consider external links (exclude gatech.edu and form links)
        if (href.startswith(('http://', 'https://')) and 
            not href.startswith(base_url) and
            not any(exclude in href.lower() for exclude in 
                ['qualtrics', 'gatech.edu', 'forms.', 'survey.', 
                 'twitter.com', 'linkedin.com', 'facebook.com', 'youtube.com'])):
            # Check if link text suggests it's a personal site
            if any(term in text for term in 
                  ['website', 'homepage', 'personal', 'lab', 'group', 'research', 
                   'project', professor_first_name, professor_last_name]):
                website = href
                print(f"Found website via explicit link text: {website}")
                break
    
    # Strategy 2: Search for name-based patterns in URLs
    if not website:
        for a in prof_soup.select('a[href^="http"]'):
            href = a.get('href', '').lower()
            # Skip inappropriate links
            if any(exclude in href for exclude in 
                  ['qualtrics', 'gatech.edu', 'twitter', 'linkedin', 'facebook']):
                continue
                
            # Common patterns for faculty websites
            name_patterns = [
                f'~{professor_last_name}',                   # ~/lastname
                f'~{professor_first_name}',                  # ~/firstname
                f'{professor_first_name}{professor_last_name}',  # firstnamelastname
                f'{professor_last_name}.{professor_first_name}',  # lastname.firstname
                f'{professor_first_name}.{professor_last_name}',  # firstname.lastname
                f'{professor_first_name}-{professor_last_name}',  # firstname-lastname
                f'/{professor_last_name}/',                   # /lastname/
                f'users/{professor_first_name}',              # users/firstname
                f'people/{professor_last_name}',              # people/lastname
                f'faculty/{professor_last_name}',             # faculty/lastname
            ]
            
            if any(pattern in href for pattern in name_patterns):
                website = a.get('href')
                print(f"Found website via name pattern in URL: {website}")
                break
    
    # Strategy 3: Look for links in proximity to website-related keywords
    if not website:
        website_keywords = ['website', 'homepage', 'personal page', 'lab page', 'research group']
        for keyword in website_keywords:
            elements = prof_soup.find_all(string=re.compile(keyword, re.IGNORECASE))
            for element in elements:
                # Get parent and check nearby links
                parent = element.parent
                for _ in range(3):  # Check up to 3 levels up
                    if not parent:
                        break
                        
                    # Find nearby links
                    links = parent.find_all('a', href=re.compile('^https?://'))
                    for link in links:
                        href = link.get('href')
                        if (href and 
                            not href.startswith(base_url) and 
                            not any(exclude in href.lower() for exclude in 
                                   ['qualtrics', 'gatech.edu', 'twitter', 'linkedin'])):
                            website = href
                            print(f"Found website near keyword '{keyword}': {website}")
                            break
                    
                    if website:
                        break
                    parent = parent.parent
                    
    # Strategy 4: Look for any external links that might be personal sites
    if not website:
        # Common TLDs for academic and personal sites
        academic_tlds = ['.edu', '.org', '.io', '.net', 'github.io', '.me']
        
        for a in prof_soup.select('a[href^="http"]'):
            href = a.get('href', '')
            
            # Skip internal links and social media
            if (href.startswith(base_url) or 
                any(exclude in href.lower() for exclude in 
                   ['qualtrics', 'gatech.edu', 'twitter.com', 'linkedin.com'])):
                continue
                
            # Prioritize links with academic TLDs
            if any(tld in href.lower() for tld in academic_tlds):
                website = href
                print(f"Found academic website by TLD: {website}")
                break
    
    # Get publications from Google Scholar
    print(f"Fetching publications for {name} from Google Scholar...")
    publications = get_publications_from_google_scholar(name)
    
    # Create professor data dictionary
    professor_data = {
        'name': name,
        'email': email,
        'department': department,
        'research_interests': research_interests,
        'personal_website': website,
        'publications': publications,
        'school': school_name,
        'profile_url': profile_url
    }
    
    return professor_data

if __name__ == "__main__":
    profs = scrape_ga_tech_faculty()
    
    # Save to a JSON file
    with open('ga_tech_faculty.json', 'w', encoding='utf-8') as f:
        json.dump(profs, indent=2, ensure_ascii=False, fp=f)
    
    # Also print to console
    print(json.dumps(profs, indent=2))
    print(f"Successfully scraped {len(profs)} faculty members")
