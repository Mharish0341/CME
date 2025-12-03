import time
import re
import pandas as pd
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from bs4 import BeautifulSoup
from urllib.parse import urljoin

START_URL = "https://www.pri-med.com/online-cme-ce"
BASE = "https://www.pri-med.com"

def setup_driver(headless=True):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    driver.implicitly_wait(5)
    return driver

def safe_text(el):
    return el.get_text(strip=True) if el else ""

def find_course_links_on_page(soup):
    links = []
    blocks = soup.select("div.course-block")
    for b in blocks:
        a = b.select_one("h4.title a") or b.select_one("div.course-block__image a")
        if a and a.get("href"):
            links.append(urljoin(BASE, a["href"]))
    return links

def click_next_page(driver):
    try:
        time.sleep(0.5)
        next_link = None
        try:
            next_link = driver.find_element(By.CSS_SELECTOR, "a[rel='next']")
        except:
            pass
        if next_link:
            driver.execute_script("arguments[0].scrollIntoView(true);", next_link)
            next_link.click()
            return True
        try:
            el = driver.find_element(By.CSS_SELECTOR, ".next.pagination-nav, .pagination-nav.next")
            driver.execute_script("arguments[0].scrollIntoView(true);", el)
            el.click()
            return True
        except:
            return False
    except:
        return False

def extract_course_details(driver, course_url):
    driver.get(course_url)
    time.sleep(1)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    title = safe_text(soup.select_one(".course-detail__intro__title h1"))
    course_type = safe_text(soup.select_one(".course-detail__intro__title p.type"))
    credits = safe_text(soup.select_one(".course-detail__intro__title p.credits"))
    description = safe_text(soup.select_one(".course-detail__intro__title p.overview"))

    release_date = ""
    expiration_date = ""
    detailed_credits = ""
    cme_block = None

    for block in soup.select(".course-detail__highlights__item"):
        h2 = block.find("h2")
        if h2 and "CME/CE Information" in h2.get_text():
            cme_block = block
            break

    if cme_block:
        p_list = cme_block.find_all("p")
        if p_list:
            detailed_credits = safe_text(p_list[0])
        all_text = cme_block.get_text("\n", strip=True)
        m = re.search(r"Release Date:\s*([0-9/]+)", all_text)
        if m:
            release_date = m.group(1)
        m2 = re.search(r"Expiration Date:\s*([0-9/]+)", all_text)
        if m2:
            expiration_date = m2.group(1)

    topics = ""
    for block in soup.select(".course-detail__highlights__item"):
        h2 = block.find("h2")
        if h2 and "Topics" in h2.get_text():
            lis = [li.get_text(strip=True) for li in block.select("ul li a")]
            topics = ";".join(lis)
            break

    faculty_items = []
    faculty_blocks = soup.select(".course-detail__faculty__item")

    for fb in faculty_blocks:
        name_tag = fb.select_one("h3")
        faculty_name = safe_text(name_tag)
        learn_more = fb.select_one("a[href*='/globals/faculty']")
        profile_url = urljoin(BASE, learn_more["href"]) if learn_more and learn_more.get("href") else None
        faculty_items.append({
            "faculty_name": faculty_name,
            "faculty_profile_url": profile_url,
            "faculty_qualification": "",
            "faculty_affiliation": "",
            "faculty_bio": ""
        })

    main_window = driver.current_window_handle

    for f in tqdm(faculty_items, desc="Faculty", leave=False):
        prof = f.get("faculty_profile_url")
        if not prof:
            continue
        try:
            driver.execute_script("window.open(arguments[0]);", prof)
            WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
            new_handles = [h for h in driver.window_handles if h != main_window]
            driver.switch_to.window(new_handles[-1])
            time.sleep(1)
            prof_soup = BeautifulSoup(driver.page_source, "html.parser")

            q_tag = prof_soup.select_one("h3.subtitle")
            f["faculty_qualification"] = safe_text(q_tag)

            aff = prof_soup.select_one("ul.affiliation__list li")
            f["faculty_affiliation"] = safe_text(aff)

            bio = prof_soup.select_one("p#collapsable-bio") or prof_soup.select_one(".bio__text, .bio")
            f["faculty_bio"] = safe_text(bio)

        except:
            pass
        finally:
            try:
                driver.close()
            except:
                pass
            driver.switch_to.window(main_window)
            time.sleep(0.2)

    course_info = {
        "title": title,
        "type": course_type,
        "credits": credits if credits else detailed_credits,
        "description": description,
        "release_date": release_date,
        "expiration_date": expiration_date,
        "topics": topics,
        "course_url": course_url
    }

    return course_info, faculty_items

def main(save_csv="courses_faculty.csv", save_xlsx="courses_faculty.xlsx", headless=True):
    driver = setup_driver(headless=headless)
    try:
        driver.get(START_URL)
        time.sleep(1)
        all_course_links = []

        soup = BeautifulSoup(driver.page_source, "html.parser")
        first_page_links = find_course_links_on_page(soup)
        for l in first_page_links:
            if l not in all_course_links:
                all_course_links.append(l)

        for i in tqdm(range(57), desc="Next Pages"):
            try:
                old_first = ""
                try:
                    old_first = driver.find_element(By.CSS_SELECTOR, "div.course-block h4.title a").get_attribute("href")
                except NoSuchElementException:
                    old_first = ""
                clicked = click_next_page(driver)
                if not clicked:
                    time.sleep(1)
                try:
                    WebDriverWait(driver, 12).until(
                        lambda d: d.find_element(By.CSS_SELECTOR, "div.course-block h4.title a").get_attribute("href") != old_first
                    )
                except (TimeoutException, NoSuchElementException):
                    time.sleep(1)
                time.sleep(0.6)
                soup = BeautifulSoup(driver.page_source, "html.parser")
                new_links = find_course_links_on_page(soup)
                for l in new_links:
                    if l not in all_course_links:
                        all_course_links.append(l)
            except Exception:
                continue

        rows = []

        for c_link in tqdm(all_course_links, desc="Courses"):
            course_info, faculty_items = extract_course_details(driver, c_link)
            if not faculty_items:
                rows.append({
                    **course_info,
                    "faculty_name": "",
                    "faculty_qualification": "",
                    "faculty_affiliation": "",
                    "faculty_bio": "",
                    "faculty_profile_url": ""
                })
            else:
                for f in faculty_items:
                    rows.append({
                        **course_info,
                        "faculty_name": f["faculty_name"],
                        "faculty_qualification": f["faculty_qualification"],
                        "faculty_affiliation": f["faculty_affiliation"],
                        "faculty_bio": f["faculty_bio"],
                        "faculty_profile_url": f["faculty_profile_url"]
                    })
            time.sleep(0.4)

        df = pd.DataFrame(rows)
        if not df.empty:
            df.to_csv(save_csv, index=False, encoding="utf-8-sig")
            df.to_excel(save_xlsx, index=False)

        driver.quit()
    except:
        driver.quit()

if __name__ == "__main__":
    main(headless=False)
