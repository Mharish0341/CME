from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import pandas as pd
import time
from tqdm import tqdm

# Base URL
base_url = "https://primeinc.org"
main_url = "https://primeinc.org/?utm_medium=mptcme"

# Set up Selenium WebDriver (assuming Chrome; ensure chromedriver is in PATH)
driver = webdriver.Chrome()
driver.get(main_url)

# Wait for the page to load
time.sleep(5)  # Adjust if needed

# Find all course blocks
course_blocks = driver.find_elements(By.CSS_SELECTOR, "div.ce-finder-directory-block")

# Collect course links
course_links = []
for block in course_blocks:
    try:
        a_tag = block.find_element(By.TAG_NAME, "a")
        href = a_tag.get_attribute("href")
        if href.startswith("/"):
            full_link = base_url + href
        else:
            full_link = href
        course_links.append(full_link)
    except NoSuchElementException:
        continue

# List to hold all data rows
data_rows = []

# Scrape each course link with tqdm progress bar
for link in tqdm(course_links, desc="Scraping courses"):
    driver.get(link)
    time.sleep(3)  # Wait for page load

    # Dictionary for course details
    course_data = {}
    course_data['Course Link'] = link

    # Course Title
    try:
        title_elem = driver.find_element(By.CSS_SELECTOR, "h1.h2.mt-0.pt-0.text-white")
        course_data['Course Title'] = title_elem.text.strip()
    except NoSuchElementException:
        try:
            title_elem = driver.find_element(By.CSS_SELECTOR, "h1.h2.mt-0.pt-0")
            course_data['Course Title'] = title_elem.text.strip()
        except NoSuchElementException:
            course_data['Course Title'] = "N/A"

    # Date and Time
    try:
        date_time_elem = driver.find_element(By.CSS_SELECTOR, "div.col-sm-8 h3.h5")
        course_data['Date and Time'] = date_time_elem.text.strip()
        # Also get location if present
        location_elem = driver.find_element(By.CSS_SELECTOR, "div.col-sm-8 h2.h2.mt-0.pt-0.text-primary")
        course_data['Location'] = location_elem.text.strip()
    except NoSuchElementException:
        try:
            broadcast_strong = driver.find_element(By.XPATH, '//strong[contains(text(), "Broadcast Date:")]')
            date_div = broadcast_strong.find_element(By.XPATH, './following-sibling::div[contains(@class, "clearfix")]')
            date_li = date_div.find_element(By.CSS_SELECTOR, "ul li")
            course_data['Date and Time'] = date_li.text.strip()
            course_data['Location'] = "N/A"
        except NoSuchElementException:
            course_data['Date and Time'] = "N/A"
            course_data['Location'] = "N/A"

    # Activity Type
    try:
        activity_strong = driver.find_element(By.XPATH, '//strong[contains(text(), "Activity Type:")]')
        type_value = activity_strong.find_element(By.XPATH, './parent::div/following-sibling::div').text.strip()
        course_data['Activity Type'] = type_value
    except NoSuchElementException:
        course_data['Activity Type'] = "N/A"

    # Credits
    try:
        credits_strong = driver.find_element(By.XPATH, '//strong[contains(text(), "Continuing Education Credits:")]')
        credits_div = credits_strong.find_element(By.XPATH, './following-sibling::div[contains(@class, "clearfix")]')
        credits_list = credits_div.find_elements(By.CSS_SELECTOR, "ul li")
        credits = []
        for li in credits_list:
            strong = li.find_element(By.TAG_NAME, "strong").text.strip()
            text = li.text.strip().replace(strong, "").strip()
            # Extract the number and type
            credit_text = text.split("for")[0].strip() + " for " + strong
            credits.append(credit_text)
        course_data['Credits'] = "; ".join(credits)
    except NoSuchElementException:
        course_data['Credits'] = "N/A"

    # Overview
    try:
        overview_elem = driver.find_element(By.CSS_SELECTOR, "div.activity-tabs-content")
        course_data['Overview'] = overview_elem.text.strip()
    except NoSuchElementException:
        try:
            # Alternative: from h2.sr-only to next section
            driver.find_element(By.CSS_SELECTOR, "h2.sr-only")  # Just to check presence
            # Collect text until agenda
            overview_text = ""
            elements = driver.find_elements(By.XPATH, "//*[self::p or self::div[contains(@class, 'clearfix')]]")
            for elem in elements:
                if "agenda" in elem.text.lower():
                    break
                overview_text += elem.text + "\n"
            course_data['Overview'] = overview_text.strip()
        except NoSuchElementException:
            course_data['Overview'] = "N/A"

    # Agenda
    try:
        agenda_elem = driver.find_element(By.CSS_SELECTOR, "div.padding-helper ol")
        agenda_items = [li.text.strip() for li in agenda_elem.find_elements(By.TAG_NAME, "li")]
        course_data['Agenda'] = "; ".join(agenda_items)
    except NoSuchElementException:
        try:
            div_clearfix = driver.find_element(By.CSS_SELECTOR, "div.clearfix.mt-1")
            course_data['Agenda'] = div_clearfix.text.strip()
        except NoSuchElementException:
            course_data['Agenda'] = "N/A"

    # Faculty
    faculty_wraps = driver.find_elements(By.CSS_SELECTOR, "div.single-faculty-wrap")
    if not faculty_wraps:
        # Add a single row with no faculty
        course_data['Faculty Name'] = "N/A"
        course_data['Faculty Role'] = "N/A"
        course_data['Faculty Affiliation'] = "N/A"
        course_data['Faculty Qualification'] = "N/A"
        data_rows.append(course_data.copy())
    else:
        for faculty in faculty_wraps:
            try:
                name_elem = faculty.find_element(By.CSS_SELECTOR, "h3.h5.mb-0")
                full_name = name_elem.text.strip()
                full_name = full_name.replace("(opens in a new tab)", "").strip()  # Clean extra text
            except:
                full_name = "N/A"

            try:
                role_elem = faculty.find_element(By.CSS_SELECTOR, "div.mb-1.italic")
                course_data['Faculty Role'] = role_elem.text.strip()
            except:
                course_data['Faculty Role'] = "N/A"

            try:
                affil_elem = faculty.find_element(By.CSS_SELECTOR, "p.text-sm")
                course_data['Faculty Affiliation'] = affil_elem.text.strip()
            except:
                course_data['Faculty Affiliation'] = "N/A"

            # Qualification: assuming it's part of name, like MD, etc.
            if "," in full_name:
                parts = full_name.rsplit(",", 1)
                course_data['Faculty Name'] = parts[0].strip()
                course_data['Faculty Qualification'] = parts[1].strip().replace("(opens in a new tab)",
                                                                                "").strip()  # Extra clean
            else:
                course_data['Faculty Name'] = full_name
                course_data['Faculty Qualification'] = "N/A"

            # Append row for this faculty
            data_rows.append(course_data.copy())

# Close driver
driver.quit()

# Create DataFrame
df = pd.DataFrame(data_rows)

# Save to CSV and Excel
df.to_csv("scraped_courses.csv", index=False)
df.to_excel("scraped_courses.xlsx", index=False)

print("Scraping completed. Files saved: scraped_courses.csv and scraped_courses.xlsx")