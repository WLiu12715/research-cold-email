import sqlite3
import json
import os
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("faculty_db.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("faculty_db")

class FacultyDatabase:
    def __init__(self, db_path="faculty_data.db"):
        """Initialize the faculty database"""
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.initialize_db()
    
    def initialize_db(self):
        """Create the database and tables if they don't exist"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            
            # Create faculty table
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS faculty (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                department TEXT,
                school TEXT,
                research_interests TEXT,
                lab_affiliation TEXT,
                personal_website TEXT,
                profile_url TEXT,
                confidence_score REAL DEFAULT 0.5,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name, department)
            )
            ''')
            
            # Create publications table with foreign key to faculty
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS publications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                faculty_id INTEGER,
                title TEXT NOT NULL,
                source TEXT,
                FOREIGN KEY (faculty_id) REFERENCES faculty(id),
                UNIQUE(faculty_id, title)
            )
            ''')
            
            # Create data_sources table to track where faculty info came from
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS data_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                faculty_id INTEGER,
                source_name TEXT NOT NULL,
                source_url TEXT,
                data_retrieved TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (faculty_id) REFERENCES faculty(id)
            )
            ''')
            
            self.conn.commit()
            logger.info("Database initialized successfully")
        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
    
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
    
    def add_faculty(self, faculty_data, source_name="scraper"):
        """Add or update a faculty member in the database"""
        try:
            # Extract basic faculty info
            name = faculty_data.get('name')
            if not name:
                logger.warning("Cannot add faculty without a name")
                return None
                
            email = faculty_data.get('email')
            department = faculty_data.get('department')
            school = faculty_data.get('school')
            research_interests = faculty_data.get('research_interests')
            lab_affiliation = faculty_data.get('lab_affiliation')
            personal_website = faculty_data.get('personal_website')
            profile_url = faculty_data.get('profile_url')
            
            # Insert or update faculty record
            self.cursor.execute('''
            INSERT INTO faculty 
            (name, email, department, school, research_interests, lab_affiliation, personal_website, profile_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name, department) DO UPDATE SET
            email=excluded.email,
            school=excluded.school,
            research_interests=excluded.research_interests,
            lab_affiliation=excluded.lab_affiliation,
            personal_website=excluded.personal_website,
            profile_url=excluded.profile_url,
            last_updated=CURRENT_TIMESTAMP
            ''', (name, email, department, school, research_interests, lab_affiliation, personal_website, profile_url))
            
            # Get the faculty ID (either newly inserted or existing)
            self.cursor.execute('SELECT id FROM faculty WHERE name=? AND department=?', (name, department))
            faculty_id = self.cursor.fetchone()[0]
            
            # Add publications if available
            publications = faculty_data.get('publications', [])
            for pub in publications:
                if pub:  # Skip empty publications
                    self.cursor.execute('''
                    INSERT OR IGNORE INTO publications (faculty_id, title, source)
                    VALUES (?, ?, ?)
                    ''', (faculty_id, pub, source_name))
            
            # Record the data source
            self.cursor.execute('''
            INSERT INTO data_sources (faculty_id, source_name, source_url)
            VALUES (?, ?, ?)
            ''', (faculty_id, source_name, profile_url))
            
            self.conn.commit()
            logger.info(f"Added/updated faculty: {name}")
            return faculty_id
            
        except sqlite3.Error as e:
            logger.error(f"Error adding faculty {faculty_data.get('name')}: {e}")
            self.conn.rollback()
            return None
    
    def get_faculty_by_name(self, name, fuzzy_match=True):
        """Get faculty by name, with optional fuzzy matching"""
        try:
            if fuzzy_match:
                # Use SQLite's LIKE for basic fuzzy matching
                self.cursor.execute('''
                SELECT id, name, email, department, school, research_interests, 
                       lab_affiliation, personal_website, profile_url, confidence_score
                FROM faculty 
                WHERE name LIKE ?
                ''', (f"%{name}%",))
            else:
                # Exact match
                self.cursor.execute('''
                SELECT id, name, email, department, school, research_interests, 
                       lab_affiliation, personal_website, profile_url, confidence_score
                FROM faculty 
                WHERE name = ?
                ''', (name,))
            
            faculty_rows = self.cursor.fetchall()
            faculty_list = []
            
            for row in faculty_rows:
                faculty_id = row[0]
                
                # Get publications for this faculty
                self.cursor.execute('SELECT title FROM publications WHERE faculty_id = ?', (faculty_id,))
                publications = [pub[0] for pub in self.cursor.fetchall()]
                
                faculty = {
                    'id': faculty_id,
                    'name': row[1],
                    'email': row[2],
                    'department': row[3],
                    'school': row[4],
                    'research_interests': row[5],
                    'lab_affiliation': row[6],
                    'personal_website': row[7],
                    'profile_url': row[8],
                    'confidence_score': row[9],
                    'publications': publications
                }
                faculty_list.append(faculty)
            
            return faculty_list
            
        except sqlite3.Error as e:
            logger.error(f"Error getting faculty by name {name}: {e}")
            return []
    
    def search_faculty_by_department(self, department_keyword):
        """Search for faculty by department keyword"""
        try:
            # Use SQLite's LIKE for keyword matching in department or school
            self.cursor.execute('''
            SELECT id, name, email, department, school, research_interests, 
                   lab_affiliation, personal_website, profile_url, confidence_score
            FROM faculty 
            WHERE department LIKE ? OR school LIKE ?
            ''', (f"%{department_keyword}%", f"%{department_keyword}%"))
            
            faculty_rows = self.cursor.fetchall()
            faculty_list = []
            
            for row in faculty_rows:
                faculty_id = row[0]
                
                # Get publications for this faculty
                self.cursor.execute('SELECT title FROM publications WHERE faculty_id = ?', (faculty_id,))
                publications = [pub[0] for pub in self.cursor.fetchall()]
                
                faculty = {
                    'id': faculty_id,
                    'name': row[1],
                    'email': row[2],
                    'department': row[3],
                    'school': row[4],
                    'research_interests': row[5],
                    'lab_affiliation': row[6],
                    'personal_website': row[7],
                    'profile_url': row[8],
                    'confidence_score': row[9],
                    'publications': publications
                }
                faculty_list.append(faculty)
            
            return faculty_list
            
        except sqlite3.Error as e:
            logger.error(f"Error searching faculty by department {department_keyword}: {e}")
            return []
    
    def get_faculty_by_id(self, faculty_id):
        """Get faculty by ID"""
        try:
            self.cursor.execute('''
            SELECT id, name, email, department, school, research_interests, 
                   lab_affiliation, personal_website, profile_url, confidence_score
            FROM faculty 
            WHERE id = ?
            ''', (faculty_id,))
            
            row = self.cursor.fetchone()
            if not row:
                return []
                
            # Get publications for this faculty
            self.cursor.execute('SELECT title FROM publications WHERE faculty_id = ?', (faculty_id,))
            publications = [pub[0] for pub in self.cursor.fetchall()]
            
            faculty = {
                'id': row[0],
                'name': row[1],
                'email': row[2],
                'department': row[3],
                'school': row[4],
                'research_interests': row[5],
                'lab_affiliation': row[6],
                'personal_website': row[7],
                'profile_url': row[8],
                'confidence_score': row[9],
                'publications': publications
            }
            
            return [faculty]
            
        except sqlite3.Error as e:
            logger.error(f"Error getting faculty by ID {faculty_id}: {e}")
            return []
    
    def get_all_faculty(self, min_confidence=0.0):
        """Get all faculty with confidence score above threshold"""
        try:
            self.cursor.execute('''
            SELECT id, name, email, department, school, research_interests, 
                   lab_affiliation, personal_website, profile_url, confidence_score
            FROM faculty 
            WHERE confidence_score >= ?
            ORDER BY confidence_score DESC
            ''', (min_confidence,))
            
            faculty_rows = self.cursor.fetchall()
            faculty_list = []
            
            for row in faculty_rows:
                faculty_id = row[0]
                
                # Get publications for this faculty
                self.cursor.execute('SELECT title FROM publications WHERE faculty_id = ?', (faculty_id,))
                publications = [pub[0] for pub in self.cursor.fetchall()]
                
                faculty = {
                    'id': faculty_id,
                    'name': row[1],
                    'email': row[2],
                    'department': row[3],
                    'school': row[4],
                    'research_interests': row[5],
                    'lab_affiliation': row[6],
                    'personal_website': row[7],
                    'profile_url': row[8],
                    'confidence_score': row[9],
                    'publications': publications
                }
                faculty_list.append(faculty)
            
            return faculty_list
            
        except sqlite3.Error as e:
            logger.error(f"Error getting all faculty: {e}")
            return []
    
    def update_faculty(self, faculty_id, updates):
        """Update faculty record with new information"""
        try:
            # Handle basic fields
            update_fields = []
            update_values = []
            
            for field in ['name', 'email', 'department', 'school', 'research_interests', 
                          'lab_affiliation', 'personal_website', 'profile_url', 'confidence_score']:
                if field in updates:
                    update_fields.append(f"{field} = ?")
                    update_values.append(updates[field])
            
            if update_fields:
                # Add faculty_id to values
                update_values.append(faculty_id)
                
                # Construct and execute update query
                update_query = f"UPDATE faculty SET {', '.join(update_fields)}, last_updated = CURRENT_TIMESTAMP WHERE id = ?"
                self.cursor.execute(update_query, update_values)
            
            # Handle new publications if any
            if 'new_publications' in updates and updates['new_publications']:
                for pub in updates['new_publications']:
                    self.cursor.execute('''
                    INSERT OR IGNORE INTO publications (faculty_id, title, source)
                    VALUES (?, ?, ?)
                    ''', (faculty_id, pub, 'verification'))
            
            self.conn.commit()
            logger.info(f"Updated faculty ID {faculty_id}")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Error updating faculty ID {faculty_id}: {e}")
            self.conn.rollback()
            return False
    
    def import_from_json(self, json_file):
        """Import faculty data from a JSON file"""
        try:
            if not os.path.exists(json_file):
                logger.error(f"JSON file not found: {json_file}")
                return False
                
            with open(json_file, 'r', encoding='utf-8') as f:
                faculty_data = json.load(f)
            
            # Filter out non-faculty entries
            non_faculty_names = set([
                'home', 'directory', 'visitor parking information', 'main directory', 'day', 'welcome',
                'undergraduate handbook', 'professional education', 'financial aid', 'faculty', 'staff', 
                'office', 'about', 'contact', 'events', 'graduate handbook', 'student', 'advising', 
                'administration', 'resources', 'faq', 'news', 'alumni', 'forms', 'information', 'handbook', 'overview'
            ])
            
            faculty_count = 0
            for faculty in faculty_data:
                name = faculty.get('name', '').lower()
                if name and name not in non_faculty_names:
                    self.add_faculty(faculty, source_name="json_import")
                    faculty_count += 1
            
            logger.info(f"Imported {faculty_count} faculty members from {json_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error importing from JSON: {e}")
            return False
    
    def export_to_json(self, json_file):
        """Export faculty data to a JSON file"""
        try:
            self.cursor.execute('''
            SELECT id, name, email, department, school, research_interests, 
                   lab_affiliation, personal_website, profile_url
            FROM faculty
            ''')
            
            faculty_rows = self.cursor.fetchall()
            faculty_list = []
            
            for row in faculty_rows:
                faculty_id = row[0]
                
                # Get publications for this faculty
                self.cursor.execute('SELECT title FROM publications WHERE faculty_id = ?', (faculty_id,))
                publications = [pub[0] for pub in self.cursor.fetchall()]
                
                faculty = {
                    'name': row[1],
                    'email': row[2],
                    'department': row[3],
                    'school': row[4],
                    'research_interests': row[5],
                    'lab_affiliation': row[6],
                    'personal_website': row[7],
                    'profile_url': row[8],
                    'publications': publications
                }
                faculty_list.append(faculty)
            
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(faculty_list, indent=2, ensure_ascii=False, fp=f)
            
            logger.info(f"Exported {len(faculty_list)} faculty members to {json_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting to JSON: {e}")
            return False
    
    def update_confidence_scores(self):
        """Update confidence scores based on data completeness"""
        try:
            self.cursor.execute('''
            UPDATE faculty
            SET confidence_score = (
                CASE 
                    WHEN email IS NOT NULL THEN 0.2 ELSE 0 
                END +
                CASE 
                    WHEN personal_website IS NOT NULL AND personal_website != 'N/A' THEN 0.2 ELSE 0 
                END +
                CASE 
                    WHEN profile_url IS NOT NULL AND profile_url != 'N/A' THEN 0.2 ELSE 0 
                END +
                CASE 
                    WHEN research_interests IS NOT NULL AND research_interests != 'N/A' THEN 0.2 ELSE 0 
                END +
                CASE 
                    WHEN EXISTS (SELECT 1 FROM publications WHERE publications.faculty_id = faculty.id LIMIT 1) THEN 0.2 ELSE 0 
                END
            )
            ''')
            
            self.conn.commit()
            logger.info("Updated confidence scores for all faculty")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Error updating confidence scores: {e}")
            self.conn.rollback()
            return False

# Example usage
if __name__ == "__main__":
    db = FacultyDatabase()
    
    # Import from existing JSON file if available
    if os.path.exists('ga_tech_faculty.json'):
        db.import_from_json('ga_tech_faculty.json')
        db.update_confidence_scores()
    
    # Example of retrieving faculty
    results = db.get_faculty_by_name("Smith")
    print(f"Found {len(results)} faculty matching 'Smith'")
    
    # Close the database connection
    db.close()
