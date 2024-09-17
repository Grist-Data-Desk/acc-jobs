from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
import pandas as pd
import time
from tqdm import tqdm
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    service = ChromeService()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def scrape_page(driver, url):
    driver.get(url)
    time.sleep(2)
    
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "result-card-container"))
        )
    except TimeoutException:
        print(f"Timed out waiting for page to load: {url}")
        return []

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    cards = soup.find_all('li', class_='result-card-container')
    
    data = []
    for card in cards:
        title = card.find('h2').text.strip() if card.find('h2') else "N/A"
        project = card.find('span', class_='result-card-container__project').text.strip() if card.find('span', class_='result-card-container__project') else "N/A"
        location = card.find('span', string='Location').find_next('p').text.strip() if card.find('span', string='Location') else "N/A"
        pay = card.find('span', string='Hourly pay equivalent').find_next('p').text.strip() if card.find('span', string='Hourly pay equivalent') else "N/A"
        term_length = card.find('span', string='Term length').find_next('p').text.strip() if card.find('span', string='Term length') else "N/A"
        apply_by = card.find('span', string='Apply by').find_next('p').text.strip() if card.find('span', string='Apply by') else "N/A"
        learn_more_url = card.find('a', class_='usa-button')['href'] if card.find('a', class_='usa-button') else "N/A"
        
        # Scrape additional details from the "Learn more and apply" page
        focus_areas, work_environments = scrape_details(driver, f"https://www.acc.gov{learn_more_url}")
        
        data.append({
            'Title': title,
            'Project': project,
            'Location': location,
            'Hourly Pay': pay,
            'Term Length': term_length,
            'Apply By': apply_by,
            'Learn More URL': f"https://www.acc.gov{learn_more_url}" if learn_more_url != "N/A" else "N/A",
            'Focus Areas': focus_areas,
            'Work Environments': work_environments
        })
    
    return data

def scrape_details(driver, url):
    driver.get(url)
    time.sleep(2)
    
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "section"))
        )
    except TimeoutException:
        print(f"Timed out waiting for details page to load: {url}")
        return "N/A", "N/A"

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    focus_areas = soup.find('h3', string='Focus area').find_next('ul').find_all('li') if soup.find('h3', string='Focus area') else []
    focus_areas = [area.text.strip() for area in focus_areas]
    
    work_environments = soup.find('h3', string='Work environment').find_next('ul').find_all('li') if soup.find('h3', string='Work environment') else []
    work_environments = [env.text.strip() for env in work_environments]
    
    return ', '.join(focus_areas), ', '.join(work_environments)

def get_total_pages(driver, url):
    driver.get(url)
    time.sleep(2)
    
    try:
        pagination = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "usa-pagination__list"))
        )
        last_page = pagination.find_elements(By.CLASS_NAME, "usa-pagination__page-no")[-1].text.strip()
        return int(last_page)
    except TimeoutException:
        print("Timed out waiting for pagination. Assuming only one page.")
        return 1
    except Exception as e:
        print(f"Error getting total pages: {e}")
        return 1

def geocode_location(location):
    geolocator = Nominatim(user_agent="acc_gov_scraper")
    try:
        location_data = geolocator.geocode(location)
        if location_data:
            return location_data.latitude, location_data.longitude
        else:
            return None, None
    except (GeocoderTimedOut, GeocoderServiceError):
        print(f"Geocoding error for location: {location}")
        return None, None

def main():
    base_url = "https://www.acc.gov/join/"
    all_data = []
    
    driver = setup_driver()
    
    try:
        total_pages = get_total_pages(driver, base_url)
        
        print(f"Found {total_pages} pages to scrape.")
        
        for page in tqdm(range(1, total_pages + 1), desc="Scraping pages", unit="page"):
            url = f"{base_url}?page={page}"
            all_data.extend(scrape_page(driver, url))
            time.sleep(1)  # Be polite to the server
        
        print("\nGeocoding locations...")
        for item in tqdm(all_data, desc="Geocoding", unit="location"):
            lat, lon = geocode_location(item['Location'])
            item['Latitude'] = lat
            item['Longitude'] = lon
        
        print("\nCreating DataFrame and saving to CSV...")
        df = pd.DataFrame(all_data)
        df.to_csv('acc_gov_opportunities.csv', index=False)
        print("Scraping complete. Data saved to acc_gov_opportunities.csv")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
