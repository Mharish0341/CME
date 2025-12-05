import time
import os
import json
import pandas as pd
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup, NavigableString
from fake_useragent import UserAgent
import undetected_chromedriver as uc

# Co
BASE_URL = "https://www.mycme.com"
SEARCH_URL_PATTERN = ""
OUTPUT_FILE = "mycme_data.csv"
PAGES_TO_SCRAPE = 16  # change this if you don't want all 16 pages

# Added "Course Details" and "Agenda" columns before "Content Type"
COLUMNS = [
    "Faculty Name", "Degree", "Affiliation", "Faculty Bio",
    "Course Title", "Course Details", "Agenda", "Content Type", "Program Description", "Source Link"
]

def setup_driver():
    ua = UserAgent()
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")
    options.add_argument("--incognito")
    options.add_argument(f"user-agent={ua.random}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # If you want headless uncomment the next two lines:
    # options.add_argument("--headless=new")
    # options.add_argument("--no-sandbox")

    # If user provided an explicit driver path via env var, use it; otherwise let undetected_chromedriver manage it.
    if CHROME_DRIVER_PATH:
        # newer uc versions accept driver_executable_path keyword; if that errors, uc.Chrome should try to manage binary automatically
        try:
            driver = uc.Chrome(driver_executable_path=CHROME_DRIVER_PATH, options=options)
        except TypeError:
            # fallback for versions that don't accept driver_executable_path
            driver = uc.Chrome(options=options)
    else:
        driver = uc.Chrome(options=options)

    # small implicit wait to reduce brittle failures
    driver.implicitly_wait(5)
    return driver

def load_all_course_links():
    print(f"🔍 Loading myCME course catalog across {PAGES_TO_SCRAPE} pages...")
    course_links = set()
    driver = setup_driver()
    try:
        # pages are 1..PAGES_TO_SCRAPE inclusive
        for page in range(1, PAGES_TO_SCRAPE + 1):
            page_url = SEARCH_URL_PATTERN.format(page=page)
            print(f"🔄 Loading page: {page_url}")
            driver.get(page_url)
            time.sleep(3)  # allow page to load (adjust if needed)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            course_tags = soup.find_all("a", class_="ember-view catalog-item")
            for tag in course_tags:
                href = tag.get("href")
                if href:
                    full_link = BASE_URL + href if href.startswith("/") else href
                    course_links.add(full_link)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    print(f"✅ Found {len(course_links)} course links across {PAGES_TO_SCRAPE} pages.")
    return list(course_links)

def extract_program_description(soup):
    program_description = ""
    desc_div = soup.find("div", id="ember37978")
    if desc_div:
        headers = desc_div.find_all("p", class_="detailsTitle")
        for header in headers:
            if "Program Description" in header.get_text():
                for sibling in header.find_next_siblings("p"):
                    if sibling.get("class") and "detailsTitle" in sibling.get("class"):
                        break
                    program_description += sibling.get_text(" ", strip=True) + "\n"
                break
    if program_description:
        return program_description.strip()

    editor_div = soup.find("div", {"id": "ember2101", "class": "ember-view editor-content indent-list"})
    if not editor_div:
        editor_div = soup.find("div", class_="editor-content")
    if editor_div:
        prog_desc_header = editor_div.find("p", class_="detailsTitle", string=lambda t: t and "Program Description" in t)
        if prog_desc_header:
            parts = []
            for sibling in prog_desc_header.find_next_siblings("p"):
                if sibling.get("class") and "detailsTitle" in sibling.get("class"):
                    break
                parts.append(sibling.get_text(" ", strip=True))
            return "\n".join(parts).strip()
    return ""

def extract_title(soup):
    header_div = soup.find("div", class_="course__detail__header")
    if header_div:
        h1 = header_div.find("h1", class_="h2")
        if h1:
            for script in h1.find_all("script"):
                script.decompose()
            title = h1.get_text(strip=True)
            if title:
                return title
    h1 = soup.find("h1")
    if h1:
        for script in h1.find_all("script"):
            script.decompose()
        title = h1.get_text(strip=True)
        if title:
            return title
    head_title = soup.find("title")
    if head_title:
        return head_title.get_text(strip=True)
    return ""

def extract_content_type(soup):
    overview_div = soup.find("div", class_="overviewFormat")
    if overview_div:
        strong = overview_div.find("strong")
        if strong:
            return strong.get_text(strip=True)
    source_div = soup.find("div", class_="catalog-grid-item__source")
    if source_div:
        return source_div.get_text(" ", strip=True)
    return ""

def extract_course_details(soup):
    details = {}
    overview_div = soup.find("div", class_="overviewFormat")
    if overview_div:
        p_tags = overview_div.find_all("p")
        for p in p_tags:
            strong_tag = p.find("strong")
            if strong_tag:
                key_text = strong_tag.get_text(strip=True).rstrip(":")
                value = p.get_text(" ", strip=True).replace(strong_tag.get_text(strip=True), "").strip()
                if key_text == "Time to Complete":
                    details["course_time"] = value
                elif key_text == "Released":
                    details["course_release_date"] = value
                elif key_text == "Expires":
                    details["course_expires_date"] = value
                elif key_text == "Maximum Credits":
                    details["course_credits"] = value
    if not details:
        live_div = soup.find("div", class_="overviewFormatLive")
        if live_div:
            live_date = live_div.find("p", class_="live_date")
            if live_date:
                details["course_release_date"] = live_date.get("data-date-start", "")
                details["course_expires_date"] = live_date.get("data-date-end", "")
                start_time = live_date.get("data-time-start", "")
                end_time = live_date.get("data-time-end", "")
                time_zone = live_date.get("data-time-zone", "")
                if start_time and end_time:
                    details["course_time"] = f"{start_time} - {end_time} {time_zone}"
            live_credits = live_div.find("p", class_="live_credits")
            if live_credits:
                details["course_credits"] = live_div.get_text(" ", strip=True)
    if details:
        return json.dumps(details)
    return ""

def extract_agenda(soup):
    agenda_title = soup.find("p", class_="detailsTitle", string=lambda t: t and "Agenda" in t)
    if agenda_title:
        img = agenda_title.find_next("img")
        if img and img.get("src"):
            return img.get("src")
        agenda_parts = []
        for sibling in agenda_title.find_next_siblings():
            if sibling.name == "p" and sibling.get("class") and "detailsTitle" in sibling.get("class"):
                break
            if sibling.name == "p":
                text = sibling.get_text(" ", strip=True)
                if text:
                    agenda_parts.append(text)
        return "\n".join(agenda_parts)
    return ""

def extract_affiliation(element):
    affiliation_parts = []
    parent_p = element.find_parent("p")
    if parent_p:
        strong_tag = parent_p.find("strong")
        if strong_tag:
            for sibling in strong_tag.next_siblings:
                if isinstance(sibling, NavigableString):
                    text = sibling.strip()
                    if text:
                        affiliation_parts.append(text)
                elif sibling.name == "br":
                    continue
                else:
                    text = sibling.get_text(" ", strip=True)
                    if text:
                        affiliation_parts.append(text)
    return ", ".join(affiliation_parts) if affiliation_parts else ""

def extract_faculty_details(driver):
    faculty_details = []
    faculty_button = None
    for tab_text in ["Faculty and Disclosures", "Faculty", "Speaker"]:
        try:
            candidates = driver.find_elements(By.XPATH, f"//a[span[contains(text(), '{tab_text}')]]")
            if candidates:
                faculty_button = candidates[0]
                print(f"Using '{tab_text}' tab for faculty details.")
                break
        except Exception as e:
            print(f"Error searching for tab '{tab_text}': {e}")
    if faculty_button:
        driver.execute_script("arguments[0].scrollIntoView(true);", faculty_button)
        time.sleep(1)
        try:
            driver.execute_script("document.querySelector('header.header--microsite').style.display='none';")
        except Exception:
            pass
        try:
            faculty_button.click()
        except Exception as e:
            print("Standard click failed, attempting ActionChains...", e)
            try:
                ActionChains(driver).move_to_element(faculty_button).click().perform()
            except Exception as e2:
                print("ActionChains click failed, using JavaScript click...", e2)
                driver.execute_script("arguments[0].click();", faculty_button)
        time.sleep(3)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        pdf_faculty = soup.find_all("a", href=lambda x: x and ".pdf" in x)
        if pdf_faculty:
            for a in pdf_faculty:
                pdf_link = a.get("href")
                if pdf_link and pdf_link.startswith("/"):
                    pdf_link = BASE_URL + pdf_link
                text = a.get_text(" ", strip=True)
                if "(" in text:
                    text = text.split("(")[0].strip()
                parts = text.split(",")
                faculty_name = parts[0].strip() if parts else ""
                degree = ""
                if len(parts) > 1:
                    degree = ", ".join(part.strip() for part in parts[1:])
                affiliation = extract_affiliation(a)
                faculty_details.append({
                    "Faculty Name": faculty_name,
                    "Degree": degree,
                    "Affiliation": affiliation,
                    "Faculty Bio": pdf_link
                })
        else:
            def extract_faculty_details_from_p(p):
                details = []
                strong_tags = p.find_all("strong")
                if not strong_tags:
                    return details
                for i, strong in enumerate(strong_tags):
                    text = strong.get_text(" ", strip=True)
                    if not text or "," not in text:
                        continue
                    parts = text.split(",")
                    faculty_name = parts[0].strip() if parts else ""
                    degree = ""
                    if len(parts) > 1:
                        degree = ", ".join(part.strip() for part in parts[1:])
                    affiliation_parts = []
                    next_strong = strong_tags[i + 1] if i + 1 < len(strong_tags) else None
                    for sibling in strong.next_siblings:
                        if sibling == next_strong:
                            break
                        if isinstance(sibling, NavigableString):
                            txt = sibling.strip()
                            if txt:
                                affiliation_parts.append(txt)
                        elif sibling.name == "br":
                            continue
                        else:
                            txt = sibling.get_text(" ", strip=True)
                            if txt:
                                affiliation_parts.append(txt)
                    affiliation = ", ".join(affiliation_parts)
                    details.append({
                        "Faculty Name": faculty_name,
                        "Degree": degree,
                        "Affiliation": affiliation,
                        "Faculty Bio": ""
                    })
                return details

            p_faculty = soup.find_all("p")
            for p in p_faculty:
                if p.get("class") and "detailsTitle" in p.get("class"):
                    continue
                details = extract_faculty_details_from_p(p)
                faculty_details.extend(details)

    if not faculty_details:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        editor_div = soup.find("div", {"id": "ember2101", "class": "ember-view editor-content indent-list"})
        if not editor_div:
            editor_div = soup.find("div", class_="editor-content")
        if editor_div:
            print("Using alternative extraction from editor-content div for faculty details.")
            p_tags = editor_div.find_all("p")
            def extract_faculty_details_from_p(p):
                details = []
                strong_tags = p.find_all("strong")
                if not strong_tags:
                    return details
                for i, strong in enumerate(strong_tags):
                    text = strong.get_text(" ", strip=True)
                    if not text or "," not in text:
                        continue
                    parts = text.split(",")
                    faculty_name = parts[0].strip() if parts else ""
                    degree = ""
                    if len(parts) > 1:
                        degree = ", ".join(part.strip() for part in parts[1:])
                    affiliation_parts = []
                    next_strong = strong_tags[i + 1] if i + 1 < len(strong_tags) else None
                    for sibling in strong.next_siblings:
                        if sibling == next_strong:
                            break
                        if isinstance(sibling, NavigableString):
                            txt = sibling.strip()
                            if txt:
                                affiliation_parts.append(txt)
                        elif sibling.name == "br":
                            continue
                        else:
                            txt = sibling.get_text(" ", strip=True)
                            if txt:
                                affiliation_parts.append(txt)
                    affiliation = ", ".join(affiliation_parts)
                    details.append({
                        "Faculty Name": faculty_name,
                        "Degree": degree,
                        "Affiliation": affiliation,
                        "Faculty Bio": ""
                    })
                return details

            for p in p_tags:
                if p.get("class") and "detailsTitle" in p.get("class"):
                    continue
                if p.find("img"):
                    continue
                details = extract_faculty_details_from_p(p)
                faculty_details.extend(details)
    if not faculty_details:
        print("No faculty details found after all extraction methods.")
    return faculty_details

def scrape_course_details(course_url):
    driver = setup_driver()
    course_rows = []
    course_data = {
        "Course Title": "",
        "Course Details": "",
        "Agenda": "",
        "Content Type": "",
        "Program Description": "",
        "Source Link": course_url
    }
    try:
        driver.get(course_url)
        time.sleep(5)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        course_data["Course Title"] = extract_title(soup)
        course_data["Course Details"] = extract_course_details(soup)
        course_data["Agenda"] = extract_agenda(soup)
        course_data["Content Type"] = extract_content_type(soup)
        course_data["Program Description"] = extract_program_description(soup)
        faculty_details = extract_faculty_details(driver)

        if faculty_details:
            separator = " || "
            faculty_names = separator.join([f.get("Faculty Name", "") for f in faculty_details])
            degrees = separator.join([f.get("Degree", "") for f in faculty_details])
            affiliations = separator.join([f.get("Affiliation", "") for f in faculty_details])
            bios_list = [f.get("Faculty Bio", "").strip() for f in faculty_details if f.get("Faculty Bio", "").strip()]
            faculty_bios = separator.join(bios_list) if bios_list else ""

            row = {
                "Faculty Name": faculty_names,
                "Degree": degrees,
                "Affiliation": affiliations,
                "Faculty Bio": faculty_bios,
                "Course Title": course_data["Course Title"],
                "Course Details": course_data["Course Details"],
                "Agenda": course_data["Agenda"],
                "Content Type": course_data["Content Type"],
                "Program Description": course_data["Program Description"],
                "Source Link": course_data["Source Link"]
            }
            course_rows.append(row)
        else:
            row = {
                "Faculty Name": "",
                "Degree": "",
                "Affiliation": "",
                "Faculty Bio": "",
                "Course Title": course_data["Course Title"],
                "Course Details": course_data["Course Details"],
                "Agenda": course_data["Agenda"],
                "Content Type": course_data["Content Type"],
                "Program Description": course_data["Program Description"],
                "Source Link": course_data["Source Link"]
            }
            course_rows.append(row)
    except Exception as e:
        print(f"❌ Error scraping {course_url}: {e}")
        row = {
            "Faculty Name": "",
            "Degree": "",
            "Affiliation": "",
            "Faculty Bio": "",
            "Course Title": course_data.get("Course Title", ""),
            "Course Details": course_data.get("Course Details", ""),
            "Agenda": course_data.get("Agenda", ""),
            "Content Type": course_data.get("Content Type", ""),
            "Program Description": course_data.get("Program Description", ""),
            "Source Link": course_data.get("Source Link", course_url)
        }
        course_rows.append(row)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    return course_rows

def main():
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
    course_links = load_all_course_links()
    if not course_links:
        print("❌ No course links found. Exiting.")
        return
    for course_url in tqdm(course_links, desc="Scraping Courses"):
        course_rows = scrape_course_details(course_url)
        df = pd.DataFrame(course_rows, columns=COLUMNS)
        if not os.path.exists(OUTPUT_FILE):
            df.to_csv(OUTPUT_FILE, mode='w', index=False)
        else:
            df.to_csv(OUTPUT_FILE, mode='a', header=False, index=False)
        print(f"✅ Saved data for {course_url}")
    print(f"✅ Data scraping completed and saved to '{OUTPUT_FILE}' successfully!")

if __name__ == "__main__":
    main()
