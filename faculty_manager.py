import os
import json
import logging
import argparse
from faculty_db import FacultyDatabase
from faculty_verifier import FacultyVerifier
from ga_tech_scraper import scrape_ga_tech_faculty, validate_url

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("faculty_manager.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("faculty_manager")

class FacultyManager:
    def __init__(self, db_path="faculty_data.db"):
        """Initialize the faculty manager"""
        self.db = FacultyDatabase(db_path)
        self.verifier = FacultyVerifier(db_path)
    
    def close(self):
        """Close database connections"""
        self.db.close()
        self.verifier.close()
    
    def initialize_from_json(self, json_file="ga_tech_faculty.json"):
        """Initialize the database from an existing JSON file"""
        if not os.path.exists(json_file):
            logger.error(f"JSON file not found: {json_file}")
            return False
        
        logger.info(f"Initializing database from {json_file}")
        success = self.db.import_from_json(json_file)
        
        if success:
            # Update confidence scores
            self.db.update_confidence_scores()
            logger.info("Database initialized successfully")
        
        return success
    
    def scrape_and_update(self):
        """Scrape faculty data and update the database"""
        try:
            logger.info("Starting faculty scraping")
            faculty_list = scrape_ga_tech_faculty()
            
            if not faculty_list:
                logger.error("No faculty data scraped")
                return False
            
            logger.info(f"Scraped {len(faculty_list)} faculty members")
            
            # Add each faculty member to the database
            for faculty in faculty_list:
                self.db.add_faculty(faculty, source_name="scraper")
            
            # Update confidence scores
            self.db.update_confidence_scores()
            
            logger.info("Faculty data updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error in scrape_and_update: {e}")
            return False
    
    def verify_faculty_data(self, min_confidence=0.3, max_faculty=None):
        """Verify faculty data using multiple sources"""
        try:
            logger.info("Starting faculty verification")
            success = self.verifier.verify_all_faculty(min_confidence, max_faculty)
            
            if success:
                # Update confidence scores after verification
                self.db.update_confidence_scores()
                logger.info("Faculty verification completed successfully")
            
            return success
            
        except Exception as e:
            logger.error(f"Error in verify_faculty_data: {e}")
            return False
    
    def export_to_json(self, json_file="verified_faculty.json", min_confidence=0.0):
        """Export faculty data to a JSON file with minimum confidence threshold"""
        try:
            logger.info(f"Exporting faculty data to {json_file}")
            
            # Get all faculty with confidence score above threshold
            faculty_list = self.db.get_all_faculty(min_confidence)
            
            if not faculty_list:
                logger.warning("No faculty data to export")
                return False
            
            # Prepare data for export
            export_data = []
            for faculty in faculty_list:
                # Validate URLs before export
                profile_url = faculty.get('profile_url')
                if profile_url and profile_url != 'N/A':
                    if not validate_url(profile_url):
                        faculty['profile_url'] = 'N/A'
                
                personal_website = faculty.get('personal_website')
                if personal_website and personal_website != 'N/A':
                    if not validate_url(personal_website):
                        faculty['personal_website'] = 'N/A'
                
                # Remove database-specific fields
                export_faculty = {
                    'name': faculty.get('name'),
                    'email': faculty.get('email'),
                    'department': faculty.get('department'),
                    'school': faculty.get('school'),
                    'research_interests': faculty.get('research_interests'),
                    'lab_affiliation': faculty.get('lab_affiliation'),
                    'personal_website': faculty.get('personal_website'),
                    'profile_url': faculty.get('profile_url'),
                    'publications': faculty.get('publications', [])
                }
                export_data.append(export_faculty)
            
            # Write to JSON file
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, indent=2, ensure_ascii=False, fp=f)
            
            logger.info(f"Exported {len(export_data)} faculty members to {json_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error in export_to_json: {e}")
            return False
    
    def run_full_pipeline(self, json_output="verified_faculty.json"):
        """Run the full faculty data pipeline: scrape, verify, and export"""
        try:
            logger.info("Starting full faculty data pipeline")
            
            # Step 1: Scrape and update
            scrape_success = self.scrape_and_update()
            if not scrape_success:
                logger.warning("Scraping failed, trying to use existing data")
            
            # Step 2: Verify faculty data (limit to 50 for demo purposes)
            verify_success = self.verify_faculty_data(min_confidence=0.3, max_faculty=50)
            if not verify_success:
                logger.warning("Verification process encountered issues")
            
            # Step 3: Export verified data
            export_success = self.export_to_json(json_file=json_output, min_confidence=0.4)
            
            if export_success:
                logger.info(f"Full pipeline completed successfully, data exported to {json_output}")
                return True
            else:
                logger.error("Failed to export data")
                return False
            
        except Exception as e:
            logger.error(f"Error in run_full_pipeline: {e}")
            return False

def main():
    """Main function to run the faculty manager from command line"""
    parser = argparse.ArgumentParser(description="Faculty data management tool")
    parser.add_argument('--init', action='store_true', help='Initialize database from existing JSON')
    parser.add_argument('--scrape', action='store_true', help='Scrape and update faculty data')
    parser.add_argument('--verify', action='store_true', help='Verify faculty data')
    parser.add_argument('--export', action='store_true', help='Export faculty data to JSON')
    parser.add_argument('--full', action='store_true', help='Run full pipeline')
    parser.add_argument('--input', type=str, default='ga_tech_faculty.json', help='Input JSON file')
    parser.add_argument('--output', type=str, default='verified_faculty.json', help='Output JSON file')
    parser.add_argument('--confidence', type=float, default=0.4, help='Minimum confidence score')
    parser.add_argument('--max', type=int, default=None, help='Maximum number of faculty to process')
    
    args = parser.parse_args()
    
    manager = FacultyManager()
    
    try:
        if args.init:
            manager.initialize_from_json(args.input)
        
        if args.scrape:
            manager.scrape_and_update()
        
        if args.verify:
            manager.verify_faculty_data(min_confidence=args.confidence, max_faculty=args.max)
        
        if args.export:
            manager.export_to_json(json_file=args.output, min_confidence=args.confidence)
        
        if args.full:
            manager.run_full_pipeline(json_output=args.output)
        
        # If no arguments provided, show help
        if not (args.init or args.scrape or args.verify or args.export or args.full):
            parser.print_help()
    
    finally:
        manager.close()

if __name__ == "__main__":
    main()
