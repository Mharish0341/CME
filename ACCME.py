import time
import pandas as pd
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import date

# URL of the CME Provider Directory
url = "https://accme.org/cme-provider-directory/"

# Initialize WebDriver (assuming Chrome; ensure chromedriver is installed and in PATH)
driver = webdriver.Chrome()
driver.get(url)

# List to hold all extracted data
data = []

# Page counter for tqdm description
page = 1

while True:
    # Wait for the page to load providers
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".provider-feed-card-header"))
    )

    # Get current page URL
    current_page_url = driver.current_url

    # Find all "More Details" toggle labels and click them to expand
    toggles = driver.find_elements(By.CSS_SELECTOR, ".provider-more-details__toggle-label")
    for toggle in toggles:
        driver.execute_script("arguments[0].click();", toggle)  # Use JS click to avoid issues
    time.sleep(5)  # Increased wait for details to expand

    # Find all provider cards
    cards = driver.find_elements(By.CSS_SELECTOR, ".provide-feed-card")

    # Process each card with tqdm for progress
    for card in tqdm(cards, desc=f"Processing Page {page}"):
        # Extract Provider Title
        try:
            title = card.find_element(By.CSS_SELECTOR, ".provider-title h2.h3").text.strip()
        except:
            title = ""

        # Extract Accredited By
        try:
            accredited_by = card.find_element(By.CSS_SELECTOR, ".eyebrow").text.strip().replace("Accredited By: ", "")
        except:
            accredited_by = ""

        # Extract Location
        try:
            location_elem = card.find_element(By.CSS_SELECTOR, ".provide-footer-details__address")
            location = ' '.join(location_elem.text.strip().split()[1:])  # Skip icon text if any
        except:
            location = ""

        # Extract Provider Website
        try:
            website = card.find_element(By.CSS_SELECTOR, ".provider-website a").get_attribute("href")
        except:
            website = ""

        # Extract details from provider-details
        details = {}
        try:
            details_div = card.find_element(By.CSS_SELECTOR, ".provider-details")
            detail_rows = details_div.find_elements(By.CSS_SELECTOR, ".provider-detail-row")
            for row in detail_rows:
                text = row.text.strip()
                if ":" in text:
                    key, value = text.split(":", 1)
                    details[key.strip()] = value.strip()
        except:
            pass

        # Extract Participates in Joint Providership
        try:
            joint_elem = card.find_element(By.CSS_SELECTOR, ".provide-footer-details__providership")
            participates = "Yes"
        except:
            participates = "No"

        # Create row dictionary
        row = {
            "Provider Title": title,
            "Accredited By": accredited_by,
            "Location": location,
            "Provider Website": website,
            "Scrape Date": date.today().isoformat(),
            "Participates in Joint Providership": participates,
            "Page URL": current_page_url,
        }
        row.update(details)  # Add details as separate columns

        data.append(row)

    # Save the current data to Excel after processing each page
    df = pd.DataFrame(data)
    df.to_excel("accme_providers.xlsx", index=False)

    # Check for next page button and click if present
    try:
        next_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '.jet-filters-pagination__item[data-value="next"] .jet-filters-pagination__link'))
        )
        driver.execute_script("arguments[0].click();", next_button)
        time.sleep(3)  # Wait for next page to load
        page += 1
    except:
        break

# Close the driver
driver.quit()

print("Scraping completed. Data saved to cme_providers.xlsx")