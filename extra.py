import time
import pandas as pd
from tqdm import tqdm

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

driver = webdriver.Chrome()

url = "https://www.cmepassport.org/activity/search"
driver.get(url)

# For testing, scrape only the first page

WebDriverWait(driver, 10).until(
    EC.presence_of_element_located(
        (By.CSS_SELECTOR, ".LearnerResultCard_learner-results-card-title__G6rw3")
    )
)

link_elems = driver.find_elements(
    By.CSS_SELECTOR,
    ".LearnerResultCard_learner-results-card-title__G6rw3 a"
)
links = [link.get_attribute("href") for link in link_elems if link.get_attribute("href")]

print(f"Activity links found on the first page: {len(links)}")

data = []

for link in tqdm(links, desc="Processing activities from first page"):
    driver.get(link)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "h4.ActivityDetail_detail-title__b9NVs")
            )
        )
    except Exception:
        continue

    row = {
        "Source URL": url,
        "Activity URL": link
    }

    # Extract Title
    try:
        row["Title"] = driver.find_element(By.CSS_SELECTOR, "h4.ActivityDetail_detail-title__b9NVs").text.strip()
    except Exception:
        row["Title"] = ""

    # Extract Accredited Provider
    try:
        row["Accredited Provider"] = driver.find_element(
            By.XPATH,
            "//div[normalize-space(.)='Accredited Provider']/following-sibling::p"
        ).text.strip()
    except Exception:
        row["Accredited Provider"] = ""

    # Extract Activity Link
    try:
        row["Activity Link"] = driver.find_element(
            By.CSS_SELECTOR,
            "a.ActivityDetail_activity-url__QOEM9"
        ).get_attribute("href")
    except Exception:
        row["Activity Link"] = ""

    # Extract About this Activity
    try:
        row["About this Activity"] = driver.find_element(
            By.XPATH,
            "//div[normalize-space(.)='About this Activity']/following-sibling::p"
        ).text.strip()
    except Exception:
        row["About this Activity"] = ""

    # Extract Registration
    try:
        row["Registration"] = driver.find_element(
            By.XPATH,
            "//div[normalize-space(.)='Registration']/following-sibling::p"
        ).text.strip()
    except Exception:
        row["Registration"] = ""

    # Extract Fee to Participate
    try:
        row["Fee to Participate"] = driver.find_element(
            By.XPATH,
            "//div[normalize-space(.)='Fee to Participate']/following-sibling::p"
        ).text.strip()
    except Exception:
        row["Fee to Participate"] = ""

    # Extract Activity Type
    try:
        row["Activity Type"] = driver.find_element(
            By.XPATH,
            "//div[normalize-space(.)='Activity Type']/following-sibling::p"
        ).text.strip()
    except Exception:
        row["Activity Type"] = ""

    # Extract Start and End Dates
    try:
        row["Start and End Dates"] = driver.find_element(
            By.XPATH,
            "//div[normalize-space(.)='Start and End Dates']/following-sibling::p"
        ).text.strip()
    except Exception:
        row["Start and End Dates"] = ""

    # Extract Location
    try:
        row["Location"] = driver.find_element(
            By.XPATH,
            "//div[normalize-space(.)='Location']/following-sibling::p"
        ).text.strip()
    except Exception:
        row["Location"] = ""

    # Extract AMA PRA Category 1 Credit™️
    try:
        row["AMA PRA Category 1 Credit™️"] = driver.find_element(
            By.XPATH,
            "//div[normalize-space(.)='AMA PRA Category 1 Credit™️']/following-sibling::p"
        ).text.strip()
    except Exception:
        row["AMA PRA Category 1 Credit™️"] = ""

    # Extract Specialties
    try:
        specialties_lis = driver.find_elements(
            By.XPATH,
            "//section[h5[normalize-space(.)='Specialties']]//li"
        )
        specs = [li.text.strip() for li in specialties_lis if li.text.strip()]
        row["Specialties"] = ", ".join(specs)
    except Exception:
        row["Specialties"] = ""

    # Extract Registered for MOC
    try:
        row["Registered for MOC"] = driver.find_element(
            By.XPATH,
            "//div[normalize-space(.)='Registered for MOC']/following-sibling::p//div[contains(@class, 'list')]"
        ).text.strip()
    except Exception:
        row["Registered for MOC"] = ""

    # Extract FDA REMS
    try:
        row["FDA REMS"] = driver.find_element(
            By.XPATH,
            "//div[normalize-space(.)='FDA REMS']/following-sibling::p"
        ).text.strip()
    except Exception:
        row["FDA REMS"] = ""

    # Extract Qualifies for MIPS
    try:
        row["Qualifies for MIPS"] = driver.find_element(
            By.XPATH,
            "//div[normalize-space(.)='Qualifies for MIPS']/following-sibling::p"
        ).text.strip()
    except Exception:
        row["Qualifies for MIPS"] = ""

    # Extract Content Outlines
    try:
        content_outlines = driver.find_element(
            By.XPATH,
            "//div[normalize-space(.)='Content Outlines']/following-sibling::*"
        ).text.strip() or "None"
        row["Content Outlines"] = content_outlines
    except Exception:
        row["Content Outlines"] = "None"

    # Extract Providership
    try:
        row["Providership"] = driver.find_element(
            By.XPATH,
            "//div[normalize-space(.)='Providership']/following-sibling::p"
        ).text.strip()
    except Exception:
        row["Providership"] = ""

    # Extract Measured Outcomes
    try:
        row["Measured Outcomes"] = driver.find_element(
            By.XPATH,
            "//div[normalize-space(.)='Measured Outcomes']/following-sibling::p"
        ).text.strip()
    except Exception:
        row["Measured Outcomes"] = ""

    # Extract Commercial Support
    try:
        row["Commercial Support"] = driver.find_element(
            By.XPATH,
            "//div[normalize-space(.)='Commercial Support']/following-sibling::p"
        ).text.strip()
    except Exception:
        row["Commercial Support"] = ""

    data.append(row)

df = pd.DataFrame(data)
df.to_excel("cme_passport_first_page.xlsx", index=False)

driver.quit()

print("Scraping of first page completed. Data saved to cme_passport_first_page.xlsx")