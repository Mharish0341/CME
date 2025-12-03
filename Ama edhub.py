import time
import csv
import random
import json
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import undetected_chromedriver as uc

# Base URL and Search URL
BASE_URL = "https://edhub.ama-assn.org"
SEARCH_URL = "https://edhub.ama-assn.org/collections/5777/neurology"

# CSV File
CSV_FILE = "WAVE 1-Activities/ama_articles.csv"

# Initialize CSV file with headers (DOI column removed)
with open(CSV_FILE, "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow([
        "Authors", "Title", "Subtitle", "Topic", "Content", "Source Link",
        "Accepted for Publication", "Published", "Open Access",
        "Corresponding Author", "Author Contributions",
        "Conflict of Interest Disclosures", "Funding/Support",
        "Role of the Funder/Sponsor", "Additional Contributions",
        "Publisher", "Event Date"
    ])


# Function to Setup Chrome Driver
def setup_driver():
    """Initialize the Selenium Chrome WebDriver."""
    ua = UserAgent()
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--incognito")
    options.add_argument(f"user-agent={ua.random}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # Remove hardcoded version_main; let undetected_chromedriver auto-detect
    return uc.Chrome(options=options)


def extract_metadata_field(soup, label):
    """
    Extracts metadata text based on the provided label from <p> tags that contain a <strong> element.
    Returns an empty string if not found.
    """
    p_tags = soup.find_all("p")
    for p in p_tags:
        strong = p.find("strong")
        if strong and label in strong.get_text():
            full_text = p.get_text(separator=" ", strip=True)
            return full_text.replace(strong.get_text(), "").strip()
    return ""


def extract_publisher(soup):
    """Extract publisher text from the article source block."""
    container = soup.find("div", class_="cme-label article-source-and-date")
    publisher = ""
    if container:
        publisher_div = container.find("div", class_="publisher")
        if publisher_div:
            publisher = publisher_div.get_text(strip=True)
    # Fallback: try JSON-LD
    if not publisher:
        ld_json = soup.find("script", type="application/ld+json")
        if ld_json and ld_json.string:
            try:
                ld_data = json.loads(ld_json.string)
                if isinstance(ld_data, list):
                    ld_data = ld_data[0]
                if "publisher" in ld_data and isinstance(ld_data["publisher"], dict):
                    publisher = ld_data["publisher"].get("name", "")
            except Exception:
                pass
    return publisher


def extract_event_date(soup):
    """Extract event date text from the article source block."""
    container = soup.find("div", class_="cme-label article-source-and-date")
    if container:
        divs = container.find_all("div")
        for d in divs:
            text = d.get_text(strip=True)
            if text.startswith("Event Date:"):
                return text.replace("Event Date:", "").strip()
    return ""


# Function to Extract Article Details
def scrape_article_details(article_url):
    """Extract detailed information from a given article page."""
    driver = setup_driver()
    driver.get(article_url)
    time.sleep(random.uniform(4, 6))  # Random sleep to mimic human behavior

    soup = BeautifulSoup(driver.page_source, "html.parser")
    driver.quit()

    try:
        def extract_text(tag, class_name):
            element = soup.find(tag, class_=class_name)
            return element.get_text(strip=True) if element else ""

        # --- Authors extraction with new layout handling ---
        authors = ""
        authors_div = soup.find("div", class_="content-authors")
        authors_list = []
        if authors_div:
            # Try the primary blocks first
            authors_tag = authors_div.find("div", class_="cme-label authors")
            if not authors_tag:
                authors_tag = authors_div.find("div", class_="cme-label authors-limited")
            if authors_tag:
                for a in authors_tag.find_all("a"):
                    text = a.get_text(strip=True)
                    if text.lower() == "et al":
                        continue
                    authors_list.append(text.replace("\xa0", " "))
            # Additional authors block
            remaining = authors_div.find("div", class_="js-authors-remaining")
            if remaining:
                for a in remaining.find_all("a"):
                    text = a.get_text(strip=True)
                    authors_list.append(text.replace("\xa0", " "))
            authors = ", ".join(authors_list)
        # Fallback: if authors is empty, try JSON-LD
        if not authors:
            ld_json = soup.find("script", type="application/ld+json")
            if ld_json and ld_json.string:
                try:
                    ld_data = json.loads(ld_json.string)
                    if isinstance(ld_data, list):
                        ld_data = ld_data[0]
                    author_field = ld_data.get("author", "")
                    if isinstance(author_field, dict):
                        authors = author_field.get("name", "")
                    else:
                        authors = author_field
                except Exception:
                    pass

        # --- End Authors extraction ---
        title = extract_text("h1", "content-title")
        subtitle = extract_text("span", "subtitle")
        topic = extract_text("a", "cme-label category-name")

        # Content extraction using conditional logic
        content = ""
        view_content = soup.find("div", id="view-content-tab")
        if view_content:
            legend_section = view_content.find("div", class_="section-type-multimedialegend")
            if legend_section:
                content = " ".join([p.get_text(strip=True) for p in legend_section.find_all("p")])
                for ul in legend_section.find_all("ul"):
                    content += " " + " ".join([li.get_text(strip=True) for li in ul.find_all("p")])
            else:
                content = " ".join([p.get_text(strip=True) for p in view_content.find_all("p")])
        else:
            content = " ".join([p.get_text(strip=True) for p in soup.find_all("p")])

        # --- DOI extraction removed ---

        accepted_for_publication = extract_metadata_field(soup, "Accepted for Publication:")
        # Updated published extraction: look for "Published Online:" and split on "doi:" if present.
        published_raw = extract_metadata_field(soup, "Published Online:")
        published = published_raw.split("doi:")[0].strip() if "doi:" in published_raw else published_raw.strip()
        # Fallback for published using JSON-LD
        if not published:
            ld_json = soup.find("script", type="application/ld+json")
            if ld_json and ld_json.string:
                try:
                    ld_data = json.loads(ld_json.string)
                    if isinstance(ld_data, list):
                        ld_data = ld_data[0]
                    published = ld_data.get("datePublished", "")
                except Exception:
                    pass

        open_access = extract_metadata_field(soup, "Open Access:")
        corresponding_author = extract_metadata_field(soup, "Corresponding Author:")
        author_contributions = extract_metadata_field(soup, "Author Contributions:")
        conflict_of_interest = extract_metadata_field(soup, "Conflict of Interest Disclosures:")
        funding_support = extract_metadata_field(soup, "Funding/Support:")
        role_of_funder = extract_metadata_field(soup, "Role of the Funder/Sponsor:")
        additional_contributions = extract_metadata_field(soup, "Additional Contributions:")

        publisher = extract_publisher(soup)
        event_date = extract_event_date(soup)

        return [
            authors, title, subtitle, topic, content, article_url,
            accepted_for_publication, published, open_access,
            corresponding_author, author_contributions,
            conflict_of_interest, funding_support,
            role_of_funder, additional_contributions,
            publisher, event_date
        ]
    except Exception as e:
        print(f"❌ ERROR scraping {article_url}: {e}")
        return ["" for _ in range(17)]


def load_all_article_links():
    """Extract article links from multiple pages."""
    print("🔍 Opening browser and loading AMA EdHub Neurology page...")
    driver = setup_driver()
    driver.get(SEARCH_URL)
    time.sleep(5)

    input("👉 Apply your desired filters manually, then press Enter to continue scraping...")

    article_links = set()

    def extract_links():
        """Extracts article links from the current page."""
        soup = BeautifulSoup(driver.page_source, "html.parser")
        anchors = soup.find_all("a", class_="search-result--title")
        for a in anchors:
            href = a.get("href")
            if href and ("jn-learning/module/" in href or "jn-learning/audio-player/" in href):
                article_links.add(href if href.startswith("http") else BASE_URL + href)

    extract_links()
    print(f"✅ Page 1: Extracted {len(article_links)} article links.")

    for page in tqdm(range(2, 54), desc="Extracting pages"):
        try:
            pagination_xpath = f"//a[contains(@class, 'page-number') and text()='{page}']"
            next_page_element = WebDriverWait(driver, 300).until(
                EC.element_to_be_clickable((By.XPATH, pagination_xpath))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", next_page_element)
            time.sleep(random.uniform(2, 4))
            driver.execute_script("arguments[0].click();", next_page_element)
            print(f"🔄 Navigating to page {page}...")
            time.sleep(random.uniform(5, 8))
            extract_links()
            print(f"✅ Page {page}: Total articles found: {len(article_links)}")
        except Exception as e:
            print(f"❌ ERROR navigating to page {page}: {e}")
            break

    driver.quit()
    print(f"✅ Total unique article links extracted: {len(article_links)}")
    return list(article_links)


if __name__ == "__main__":
    article_links = load_all_article_links()

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        for article_url in tqdm(article_links, desc="Scraping articles"):
            article_data = scrape_article_details(article_url)
            writer.writerow(article_data)

    print("✅ Scraping completed. Data saved to CSV.")