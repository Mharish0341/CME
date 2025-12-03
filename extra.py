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
SEARCH_URL = "https://edhub.ama-assn.org/jn-learning/by-topic?hd=edhub&f_PublicationYear=2021AND2022AND2023AND2024AND2025&fl_IsDataSupplement=false&page=3"

# CSV File
CSV_FILE = "WAVE 1-Activities/ama_articles.csv"

# Initialize CSV file with headers (DOI column removed, added Type, Audio Link, Video Link)
with open(CSV_FILE, "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow([
        "Authors", "Title", "Subtitle", "Topic", "Content", "Source Link", "Type", "Audio Link", "Video Link",
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
    # Let undetected_chromedriver auto-detect the binary/version
    return uc.Chrome(options=options)


def extract_metadata_field(soup, label):
    p_tags = soup.find_all("p")
    for p in p_tags:
        strong = p.find("strong")
        if strong and label in strong.get_text():
            full_text = p.get_text(separator=" ", strip=True)
            return full_text.replace(strong.get_text(), "").strip()
    return ""


def extract_publisher(soup):
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
    container = soup.find("div", class_="cme-label article-source-and-date")
    if container:
        divs = container.find_all("div")
        for d in divs:
            text = d.get_text(strip=True)
            if text.startswith("Event Date:"):
                return text.replace("Event Date:", "").strip()
    return ""


# Modified: reuse the same driver instance (do NOT create/quit inside this function)
def scrape_article_details(driver, article_url, article_type):
    """Extract detailed information from a given article page using an existing driver."""
    try:
        driver.get(article_url)
        # Wait for a recognizable element on the article page (title) or just body as fallback
        try:
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1.content-title, div.content-authors, #view-content-tab"))
            )
        except Exception:
            # fallback small sleep if element detection fails
            time.sleep(random.uniform(3, 5))

        # Allow dynamic content to load
        time.sleep(random.uniform(1.5, 3.5))

        soup = BeautifulSoup(driver.page_source, "html.parser")

        def extract_text(tag, class_name):
            element = soup.find(tag, class_=class_name)
            return element.get_text(strip=True) if element else ""

        # --- Authors extraction with new layout handling ---
        authors = ""
        authors_div = soup.find("div", class_="content-authors")
        authors_list = []
        if authors_div:
            authors_tag = authors_div.find("div", class_="cme-label authors")
            if not authors_tag:
                authors_tag = authors_div.find("div", class_="cme-label authors-limited")
            if authors_tag:
                for a in authors_tag.find_all("a"):
                    text = a.get_text(strip=True)
                    if text.lower() == "et al":
                        continue
                    authors_list.append(text.replace("\xa0", " "))
            remaining = authors_div.find("div", class_="js-authors-remaining")
            if remaining:
                for a in remaining.find_all("a"):
                    text = a.get_text(strip=True)
                    authors_list.append(text.replace("\xa0", " "))
            authors = ", ".join(authors_list)
        # Fallback: JSON-LD
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

        accepted_for_publication = extract_metadata_field(soup, "Accepted for Publication:")
        published_raw = extract_metadata_field(soup, "Published Online:")
        published = published_raw.split("doi:")[0].strip() if "doi:" in published_raw else published_raw.strip()
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

        # Extract audio link
        audio_link = ""
        audio_elem = soup.find("audio", {"class": "js-audio-player"})
        if audio_elem:
            audio_link = audio_elem.get("src", "")

        # Extract video link
        video_link = ""
        cadmore_div = soup.find("div", {"class": "cadmore-player-wrap"})
        if cadmore_div:
            iframe = cadmore_div.find("iframe")
            if iframe:
                video_link = iframe.get("src", "")

        if not video_link:
            video_container = soup.find("div", class_="video-container")
            if video_container:
                hls_source = video_container.find("source", type="application/x-mpegURL")
                if hls_source:
                    video_link = hls_source.get("src", "")
                else:
                    source = video_container.find("source")
                    if source:
                        video_link = source.get("src", "")

        return [
            authors, title, subtitle, topic, content, article_url,
            article_type, audio_link, video_link,
            accepted_for_publication, published, open_access,
            corresponding_author, author_contributions,
            conflict_of_interest, funding_support,
            role_of_funder, additional_contributions,
            publisher, event_date
        ]
    except Exception as e:
        print(f"❌ ERROR scraping {article_url}: {e}")
        return ["" for _ in range(19)]


# Modified: accept driver parameter and reuse it for pagination/link extraction
def load_all_article_links(driver):
    """Extract article links from multiple pages using the provided logged-in driver."""
    print("🔍 Loading AMA EdHub Neurology page...")
    driver.get(SEARCH_URL)
    # Let page and JS load
    time.sleep(4)

    # Let user manually log in and apply filters
    input("👉 Please log in (if needed) and apply any filters on the site in the opened browser. When ready, press Enter to continue...")

    articles = []

    def extract_links():
        soup = BeautifulSoup(driver.page_source, "html.parser")
        search_results = soup.find_all("li", class_="search-result")
        new_articles = []
        for li in search_results:
            content_div = li.find("div", class_="search-result--content")
            if not content_div:
                continue
            title_a = content_div.find("a", class_="search-result--title")
            if not title_a:
                continue
            href = title_a.get("href")
            if not href:
                continue
            full_url = href if href.startswith("http") else BASE_URL + href
            if any(a["url"] == full_url for a in articles):
                continue  # Skip duplicate

            # Type detection using icons and path
            type_ = "Other"
            icons = content_div.find_all("icon")
            icon_classes = []
            for icon in icons:
                classes = icon.get("class", [])
                if isinstance(classes, list):
                    icon_classes.extend(classes)
                else:
                    icon_classes.append(classes)
            has_audio = "icon-Content-Audio" in icon_classes
            has_video = "icon-Content-Video" in icon_classes
            has_event = "icon-Content-Event" in icon_classes
            has_interactive = "icon-Content-Interactive-Module" in icon_classes

            if has_audio or "audio-player" in href:
                type_ = "Audio"
            elif has_video or "video-player" in href:
                type_ = "Video"
            elif has_event:
                type_ = "Event"
            elif has_interactive or "interactive" in href:
                type_ = "Interactive"
            elif "module/" in href or "provider-referrer/" in href:
                type_ = "Module"

            new_articles.append({"url": full_url, "type": type_})
        return new_articles

    # Initial page extraction
    new_articles = extract_links()
    articles.extend(new_articles)
    print(f"✅ Page 1: Extracted {len(articles)} article links.")

    # Pagination loop using Next button
    page = 1
    while True:
        try:
            next_button = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "page-next"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
            time.sleep(random.uniform(1.5, 3.0))
            driver.execute_script("arguments[0].click();", next_button)
            print(f"🔄 Navigating to page {page + 1}...")
            time.sleep(random.uniform(4.5, 7.0))
            new_articles = extract_links()
            articles.extend(new_articles)
            page += 1
            print(f"✅ Page {page}: Total articles found: {len(articles)}")
        except Exception as e:
            print(f"❌ No more pages or error: {e}")
            break

    # Deduplicate by URL just in case
    unique = {}
    for a in articles:
        unique[a["url"]] = a
    final_list = list(unique.values())

    print(f"✅ Total unique article links extracted: {len(final_list)}")
    return final_list


if __name__ == "__main__":
    driver = setup_driver()

    try:
        # Load links using the same driver (allows manual login)
        articles = load_all_article_links(driver)

        # Scrape each article using the same logged-in driver
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            for art in tqdm(articles, desc="Scraping articles"):
                # small random delay between article visits to reduce detection
                time.sleep(random.uniform(1.0, 2.5))
                article_data = scrape_article_details(driver, art["url"], art["type"])
                writer.writerow(article_data)

        print("✅ Scraping completed. Data saved to CSV.")
    finally:
        # Ensure driver quits when finished or on exception
        try:
            driver.quit()
        except Exception:
            pass