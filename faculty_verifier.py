import requests
import logging
import re
import time
from bs4 import BeautifulSoup
from scholarly import scholarly
from faculty_db import FacultyDatabase
from ga_tech_scraper import create_session, validate_url

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("faculty_verifier.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("faculty_verifier")

class FacultyVerifier:
    def __init__(self, db_path="faculty_data.db"):
        """Initialize the faculty verifier with database connection"""
        self.db = FacultyDatabase(db_path)
        self.session = create_session()
    
    def close(self):
        """Close database connection"""
        self.db.close()
    
    def verify_faculty(self, faculty_id=None, name=None):
        """Verify faculty information using multiple sources"""
        if faculty_id is None and name is None:
            logger.error("Either faculty_id or name must be provided")
            return False
        
        # Get faculty data from database
        if faculty_id is not None:
            faculty_list = self.db.get_faculty_by_id(faculty_id)
        else:
            faculty_list = self.db.get_faculty_by_name(name, fuzzy_match=False)
        
        if not faculty_list:
            logger.warning(f"No faculty found with {'ID ' + str(faculty_id) if faculty_id else 'name ' + name}")
            return False
        
        faculty = faculty_list[0]
        logger.info(f"Verifying faculty: {faculty['name']}")
        
        # Initialize verification results
        verification_results = {
            'google_scholar': self._verify_google_scholar(faculty),
            'dblp': self._verify_dblp(faculty),
            'department_website': self._verify_department_website(faculty),
            'personal_website': self._verify_personal_website(faculty)
        }
        
        # Calculate overall confidence score
        confidence_score = sum(result.get('confidence', 0) for result in verification_results.values()) / len(verification_results)
        
        # Update faculty record with verified information
        self._update_faculty_with_verified_info(faculty, verification_results, confidence_score)
        
        logger.info(f"Verification complete for {faculty['name']} with confidence score {confidence_score:.2f}")
        return True
    
    def _verify_google_scholar(self, faculty):
        """Verify faculty information using Google Scholar"""
        try:
            logger.info(f"Verifying {faculty['name']} on Google Scholar")
            result = {'source': 'google_scholar', 'confidence': 0.0, 'data': {}}
            
            # Search for the author
            search_query = scholarly.search_author(f"{faculty['name']} {faculty['department']}")
            author = next(search_query, None)
            
            if not author:
                logger.info(f"No Google Scholar profile found for {faculty['name']}")
                return result
            
            # Get detailed author information
            try:
                author = scholarly.fill(author)
                
                # Extract and verify information
                verified_data = {}
                
                # Verify name
                scholar_name = author.get('name', '')
                if self._name_similarity(faculty['name'], scholar_name) > 0.8:
                    verified_data['name_verified'] = True
                    result['confidence'] += 0.2
                
                # Verify affiliation
                affiliation = author.get('affiliation', '')
                if 'georgia tech' in affiliation.lower() or 'gatech' in affiliation.lower():
                    verified_data['affiliation_verified'] = True
                    result['confidence'] += 0.2
                
                # Get publications
                publications = []
                for pub in author.get('publications', [])[:5]:  # Top 5 publications
                    if 'bib' in pub and 'title' in pub['bib']:
                        publications.append(pub['bib']['title'])
                
                if publications:
                    verified_data['publications'] = publications
                    result['confidence'] += 0.2
                
                # Get homepage if available
                homepage = author.get('homepage')
                if homepage:
                    verified_data['personal_website'] = homepage
                    result['confidence'] += 0.2
                
                # Get email domains from publications if available
                email_domains = set()
                for pub in author.get('publications', []):
                    if 'bib' in pub and 'pub_year' in pub['bib'] and int(pub['bib'].get('pub_year', 0)) > 2015:
                        # Recent publication might have email
                        try:
                            pub_filled = scholarly.fill(pub)
                            if 'author_pub_id' in pub_filled:
                                email_pattern = r'[\w.+-]+@[\w-]+\.[\w.-]+'
                                pub_text = str(pub_filled)
                                emails = re.findall(email_pattern, pub_text)
                                for email in emails:
                                    if 'gatech.edu' in email:
                                        verified_data['email'] = email
                                        result['confidence'] += 0.2
                                        break
                        except Exception as e:
                            logger.warning(f"Error filling publication details: {e}")
                
                result['data'] = verified_data
                logger.info(f"Google Scholar verification for {faculty['name']}: {result['confidence']:.2f} confidence")
                
            except Exception as e:
                logger.error(f"Error filling Google Scholar author details: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in Google Scholar verification: {e}")
            return {'source': 'google_scholar', 'confidence': 0.0, 'data': {}}
    
    def _verify_dblp(self, faculty):
        """Verify faculty information using DBLP"""
        try:
            logger.info(f"Verifying {faculty['name']} on DBLP")
            result = {'source': 'dblp', 'confidence': 0.0, 'data': {}}
            
            # Format name for DBLP query
            name_parts = faculty['name'].split()
            if len(name_parts) < 2:
                return result
            
            # DBLP uses format: firstname_lastname
            first_name = name_parts[0].lower()
            last_name = name_parts[-1].lower()
            
            # Try different name formats
            name_formats = [
                f"{first_name}_{last_name}",  # firstname_lastname
                f"{first_name[0]}_{last_name}"  # f_lastname (initial)
            ]
            
            for name_format in name_formats:
                dblp_url = f"https://dblp.org/pid/{name_format}.html"
                
                try:
                    response = self.session.get(dblp_url, timeout=10)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Verify it's the right person by checking affiliation
                        affiliation_elements = soup.select('.affiliation')
                        is_gatech = False
                        for elem in affiliation_elements:
                            if 'georgia tech' in elem.get_text().lower() or 'gatech' in elem.get_text().lower():
                                is_gatech = True
                                result['confidence'] += 0.3
                                break
                        
                        if not is_gatech:
                            continue  # Try next name format
                        
                        # Extract publications
                        publications = []
                        pub_elements = soup.select('.title')
                        for i, elem in enumerate(pub_elements):
                            if i >= 5:  # Limit to 5 publications
                                break
                            publications.append(elem.get_text().strip())
                        
                        if publications:
                            result['data']['publications'] = publications
                            result['confidence'] += 0.3
                        
                        # Extract homepage if available
                        homepage_elem = soup.select_one('a[href*="homepage"]')
                        if homepage_elem:
                            homepage = homepage_elem.get('href')
                            if homepage and validate_url(homepage):
                                result['data']['personal_website'] = homepage
                                result['confidence'] += 0.2
                        
                        # Extract email if available (rare on DBLP but possible)
                        email_pattern = r'[\w.+-]+@[\w-]+\.[\w.-]+'
                        email_matches = re.findall(email_pattern, response.text)
                        for email in email_matches:
                            if 'gatech.edu' in email:
                                result['data']['email'] = email
                                result['confidence'] += 0.2
                                break
                        
                        logger.info(f"DBLP verification for {faculty['name']}: {result['confidence']:.2f} confidence")
                        return result
                
                except Exception as e:
                    logger.warning(f"Error checking DBLP format {name_format}: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in DBLP verification: {e}")
            return {'source': 'dblp', 'confidence': 0.0, 'data': {}}
    
    def _verify_department_website(self, faculty):
        """Verify faculty information using department website"""
        try:
            logger.info(f"Verifying {faculty['name']} on department website")
            result = {'source': 'department_website', 'confidence': 0.0, 'data': {}}
            
            # Skip if no profile URL
            if not faculty.get('profile_url') or faculty['profile_url'] == 'N/A':
                return result
            
            # Validate and fetch the profile page
            profile_url = faculty['profile_url']
            if not validate_url(profile_url):
                return result
            
            try:
                response = self.session.get(profile_url, timeout=10)
                if response.status_code != 200:
                    return result
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Verify name on page
                page_text = soup.get_text()
                if faculty['name'].lower() in page_text.lower():
                    result['confidence'] += 0.2
                
                # Look for email
                email_pattern = r'[\w.+-]+@[\w-]+\.[\w.-]+'
                email_matches = re.findall(email_pattern, page_text)
                for email in email_matches:
                    if 'gatech.edu' in email:
                        result['data']['email'] = email
                        result['confidence'] += 0.2
                        break
                
                # Look for research interests
                research_keywords = ['research areas', 'research interests', 'research focus']
                for keyword in research_keywords:
                    if keyword in page_text.lower():
                        # Extract text after the keyword
                        parts = page_text.lower().split(keyword, 1)
                        if len(parts) > 1:
                            research_text = parts[1].strip()
                            end_markers = ['.', '\n\n', '\r\n', '\n']
                            for marker in end_markers:
                                if marker in research_text:
                                    research_text = research_text.split(marker, 1)[0]
                            if research_text:
                                result['data']['research_interests'] = research_text.strip()
                                result['confidence'] += 0.2
                                break
                
                # Look for personal website
                website_links = soup.select('a[href*="website"], a[href*="homepage"], a:contains("Website"), a:contains("Homepage")')
                for a in website_links:
                    href = a.get('href')
                    if href and not href.startswith(profile_url):
                        if validate_url(href):
                            result['data']['personal_website'] = href
                            result['confidence'] += 0.2
                            break
                
                logger.info(f"Department website verification for {faculty['name']}: {result['confidence']:.2f} confidence")
                
            except Exception as e:
                logger.warning(f"Error fetching department profile: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in department website verification: {e}")
            return {'source': 'department_website', 'confidence': 0.0, 'data': {}}
    
    def _verify_personal_website(self, faculty):
        """Verify faculty information using personal website"""
        try:
            logger.info(f"Verifying {faculty['name']} on personal website")
            result = {'source': 'personal_website', 'confidence': 0.0, 'data': {}}
            
            # Skip if no personal website
            if not faculty.get('personal_website') or faculty['personal_website'] == 'N/A':
                return result
            
            # Validate and fetch the personal website
            personal_website = faculty['personal_website']
            if not validate_url(personal_website):
                return result
            
            try:
                response = self.session.get(personal_website, timeout=10)
                if response.status_code != 200:
                    return result
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Verify name on page
                page_text = soup.get_text()
                if faculty['name'].lower() in page_text.lower():
                    result['confidence'] += 0.3
                
                # Look for Georgia Tech affiliation
                if 'georgia tech' in page_text.lower() or 'gatech' in page_text.lower():
                    result['confidence'] += 0.2
                
                # Look for publications
                pub_keywords = ['publications', 'papers', 'articles', 'research']
                publications = []
                
                for keyword in pub_keywords:
                    pub_sections = soup.find_all(['h1', 'h2', 'h3', 'h4', 'div', 'section'], 
                                              string=lambda text: text and keyword.lower() in text.lower())
                    
                    for section in pub_sections:
                        # Look for list items or paragraphs after the heading
                        items = section.find_all_next(['li', 'p'], limit=10)
                        for item in items:
                            text = item.get_text().strip()
                            if len(text) > 20 and not any(p in text for p in publications):
                                publications.append(text)
                                if len(publications) >= 5:
                                    break
                        
                        if publications:
                            break
                
                if publications:
                    result['data']['publications'] = publications
                    result['confidence'] += 0.3
                
                # Look for email
                email_pattern = r'[\w.+-]+@[\w-]+\.[\w.-]+'
                email_matches = re.findall(email_pattern, page_text)
                for email in email_matches:
                    if 'gatech.edu' in email:
                        result['data']['email'] = email
                        result['confidence'] += 0.2
                        break
                
                logger.info(f"Personal website verification for {faculty['name']}: {result['confidence']:.2f} confidence")
                
            except Exception as e:
                logger.warning(f"Error fetching personal website: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in personal website verification: {e}")
            return {'source': 'personal_website', 'confidence': 0.0, 'data': {}}
    
    def _update_faculty_with_verified_info(self, faculty, verification_results, confidence_score):
        """Update faculty record with verified information"""
        try:
            # Combine verified data from all sources
            verified_data = {}
            
            # Start with highest confidence sources
            sources_by_confidence = sorted(
                verification_results.items(),
                key=lambda x: x[1].get('confidence', 0),
                reverse=True
            )
            
            # Collect data from all sources
            for source_name, result in sources_by_confidence:
                source_data = result.get('data', {})
                for key, value in source_data.items():
                    if key not in verified_data and value:
                        verified_data[key] = value
            
            # Update faculty record with verified information
            updates = {}
            
            # Email
            if 'email' in verified_data and verified_data['email'] != faculty.get('email'):
                updates['email'] = verified_data['email']
            
            # Personal website
            if 'personal_website' in verified_data and verified_data['personal_website'] != faculty.get('personal_website'):
                updates['personal_website'] = verified_data['personal_website']
            
            # Research interests
            if 'research_interests' in verified_data and verified_data['research_interests'] != faculty.get('research_interests'):
                updates['research_interests'] = verified_data['research_interests']
            
            # Publications
            if 'publications' in verified_data:
                # Add any new publications
                existing_pubs = set(faculty.get('publications', []))
                new_pubs = [p for p in verified_data['publications'] if p not in existing_pubs]
                if new_pubs:
                    updates['new_publications'] = new_pubs
            
            # Update confidence score
            updates['confidence_score'] = confidence_score
            
            # Apply updates to database
            if updates:
                logger.info(f"Updating faculty {faculty['name']} with verified info: {updates}")
                self.db.update_faculty(faculty['id'], updates)
            else:
                logger.info(f"No updates needed for faculty {faculty['name']}")
            
        except Exception as e:
            logger.error(f"Error updating faculty with verified info: {e}")
    
    def _name_similarity(self, name1, name2):
        """Calculate similarity between two names"""
        # Normalize names
        name1 = name1.lower().strip()
        name2 = name2.lower().strip()
        
        # Split into parts
        parts1 = set(name1.split())
        parts2 = set(name2.split())
        
        # Calculate Jaccard similarity
        intersection = len(parts1.intersection(parts2))
        union = len(parts1.union(parts2))
        
        return intersection / union if union > 0 else 0.0
    
    def verify_all_faculty(self, min_confidence=0.0, max_faculty=None):
        """Verify all faculty in the database"""
        try:
            # Get all faculty with confidence score above threshold
            faculty_list = self.db.get_all_faculty(min_confidence)
            
            if max_faculty is not None and max_faculty > 0:
                faculty_list = faculty_list[:max_faculty]
            
            logger.info(f"Verifying {len(faculty_list)} faculty members")
            
            for i, faculty in enumerate(faculty_list):
                try:
                    logger.info(f"Verifying faculty {i+1}/{len(faculty_list)}: {faculty['name']}")
                    self.verify_faculty(faculty_id=faculty['id'])
                    
                    # Be nice to external services
                    time.sleep(2)
                    
                except Exception as e:
                    logger.error(f"Error verifying faculty {faculty['name']}: {e}")
            
            logger.info(f"Completed verification of {len(faculty_list)} faculty members")
            return True
            
        except Exception as e:
            logger.error(f"Error in verify_all_faculty: {e}")
            return False

# Example usage
if __name__ == "__main__":
    verifier = FacultyVerifier()
    
    # Verify a specific faculty member
    # verifier.verify_faculty(name="John Doe")
    
    # Or verify all faculty with at least 0.3 confidence score, max 10 faculty
    verifier.verify_all_faculty(min_confidence=0.3, max_faculty=10)
    
    verifier.close()
