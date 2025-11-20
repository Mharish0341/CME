import time
import pandas as pd
from tqdm import tqdm

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options


driver = webdriver.Chrome()

url = "https://www.medscape.org/neurology"
driver.get(url)

# Click "View More Activities" until no more
while True:
    try:
        more_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".view-more.view-all-main-content"))
        )
        driver.execute_script("arguments[0].click();", more_button)
        time.sleep(1)  # Reduced sleep
    except:
        break

# Find all activity cards
cards = driver.find_elements(By.CSS_SELECTOR, ".hp-card_main")

# Extract links
links = []
for card in cards:
    try:
        title_a = card.find_element(By.CSS_SELECTOR, ".title")
        link = title_a.get_attribute("href")
        links.append(link)
    except:
        pass

print(f"Total activities found: {len(links)}")

data = []

for link in tqdm(links, desc="Processing activities"):
    driver.get(link)

    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1.title"))
        )
    except:
        continue

    row = {"Activity URL": link}

    # Extract Title
    try:
        row["Title"] = driver.find_element(By.CSS_SELECTOR, "h1.title").text.strip()
    except:
        row["Title"] = ""

    # Extract Physicians credits
    try:
        phys_div = driver.find_element(By.XPATH, "//p[normalize-space(.)='Physicians']/following-sibling::span/parent::div")
        row["Physicians credits"] = phys_div.text.strip().replace('Physicians', '').strip()
    except:
        row["Physicians credits"] = ""

    # Extract Nurses Credits
    try:
        nurse_div = driver.find_element(By.XPATH, "//p[normalize-space(.)='Nurses']/following-sibling::span/parent::div/parent::div")
        row["Nurses Credits"] = nurse_div.text.strip().replace('Nurses', '').strip()
    except:
        row["Nurses Credits"] = ""

    # Extract Pharmacists credits
    try:
        pharm_div = driver.find_element(By.XPATH, "//p[normalize-space(.)='Pharmacists']/following-sibling::span/parent::div/parent::div")
        row["Pharmacists credits"] = pharm_div.text.strip().replace('Pharmacists', '').strip()
    except:
        row["Pharmacists credits"] = ""

    # Extract physicians assistants credits
    try:
        pa_div = driver.find_element(By.XPATH, "//p[normalize-space(.)='Physician Assistants']/following-sibling::span/parent::div/parent::div")
        row["Physician Assistants credits"] = pa_div.text.strip().replace('Physician Assistants', '').strip()
    except:
        row["Physician Assistants credits"] = ""

    # Extract ABIM diplomates credits
    try:
        abim_div = driver.find_element(By.XPATH, "//p[normalize-space(.)='ABIM Diplomates']/following-sibling::span/parent::div/parent::div")
        row["ABIM Diplomates credits"] = abim_div.text.strip().replace('ABIM Diplomates', '').strip()
    except:
        row["ABIM Diplomates credits"] = ""

    # Extract IPCE credits
    try:
        ipce_div = driver.find_element(By.XPATH, "//p[strong[normalize-space(.)='IPCE']]")
        row["IPCE credits"] = ipce_div.text.strip().replace('IPCE', '').strip()
    except:
        row["IPCE credits"] = ""

    # Extract CME / ABIM MOC / CE Released Date
    try:
        released = driver.find_element(By.CSS_SELECTOR, ".cme-released-date")
        row["CME / ABIM MOC / CE Released Date"] = released.text.strip().replace('CME / ABIM MOC / CE Released:', '').strip()
    except:
        row["CME / ABIM MOC / CE Released Date"] = ""

    # Extract Valid for credit through
    try:
        valid = driver.find_element(By.CSS_SELECTOR, ".valid-credit-through")
        row["Valid for credit through"] = valid.text.strip().replace('Valid for credit through:', '').strip()
    except:
        row["Valid for credit through"] = ""

    # Extract Target Audience and Goal Statement
    try:
        target = driver.find_element(By.CSS_SELECTOR, ".adp-infolayer-targetaudience")
        row["Target Audience and Goal Statement"] = target.text.strip().replace('Target Audience and Goal Statement', '').strip()
    except:
        row["Target Audience and Goal Statement"] = ""

    # Extract Disclosures
    try:
        disc = driver.find_element(By.CSS_SELECTOR, ".adp-infolayer-disclosures")
        row["Disclosures"] = disc.text.strip().replace('Disclosures', '').strip()
    except:
        row["Disclosures"] = ""

    # Extract Author
    try:
        author_section = driver.find_element(By.CSS_SELECTOR, ".adp-infolayer-contributers")
        row["Author"] = author_section.text.strip()
    except:
        row["Author"] = ""

    # Extract Instructions for Participation & Credit
    try:
        instr = driver.find_element(By.CSS_SELECTOR, ".instructions")
        row["Instructions for Participation & Credit"] = instr.text.strip().replace('Instructions for Participation & Credit', '').strip()
    except:
        row["Instructions for Participation & Credit"] = ""

    data.append(row)

    # Save incrementally
    df = pd.DataFrame(data)
    df.to_excel("medscape_neurology_activities.xlsx", index=False)

driver.quit()

print("Scraping completed. Data saved to medscape_neurology_activities.xlsx")