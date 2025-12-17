#!/usr/bin/env python3
"""
Vindico scraper — updated:
 - adds series_co_chairs column
 - ensures overview only contains overview text
 - faculty excludes disclosure/legal blocks (moved to 'others')
 - target_audience: only first paragraph; provided_by: subsequent paragraphs after that
 - others: everything not captured (excluding title)
 - saves raw_html for first 5 pages, preview_first5.xlsx, vindico_live_events.xlsx
"""

import time
import re
import os
import hashlib
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup, NavigableString, Tag

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm

# ---------- Configuration ----------
EVENT_LISTING_URL = "https://events.vindicocme.com/en/15kYU86/g/xM5BD6TC2R"
EVENT_BASE_URL = "https://events.vindicocme.com"

# Keywords to detect disclosure/legal boilerplate (to avoid putting in faculty)
DISCLOSURE_KEYWORDS = [
    "accredit", "accreditation", "accrediting", "accreditation council", "acme", "accreditation council",
    "disclos", "financial relationship", "commercial interests", "conflict of interest",
    "privacy policy", "recording", "investigational", "non-fda", "non-fda approved", "investigational uses",
    "office of medical affairs", "vindico medical education", "compliance"
]

# ---------- Utilities ----------
def init_driver(headless=False):
    from selenium.webdriver.chrome.options import Options
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def clean_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.split())

def strip_tags(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)

def looks_like_disclosure(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    for kw in DISCLOSURE_KEYWORDS:
        if kw in t:
            return True
    return False

# ---------- Parsing helpers ----------
def _normalize_heading(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip().lower()

def _parse_paragraph_blocks(paragraphs, page_title=None):

    def paragraph_has_bold_heading(p):
        for tag in p.find_all(["strong", "b"], recursive=True):
            txt = tag.get_text(" ", strip=True)
            if txt:
                return txt.strip()
        for s in p.find_all("span", recursive=True):
            style = s.get("style", "") or ""
            if ("font-weight" in style) or ("font-size" in style):
                st = s.get_text(" ", strip=True)
                if st:
                    return st.strip()
        return None

    # --------------------------------------------------------------------------------
    # 🔥 UPDATED heading_map
    # Added:
    #  - "course chair", "course chairs", "course co-chair" → activity_chair
    #  - "topics", "topic" → agenda
    # --------------------------------------------------------------------------------
    heading_map = {
        "activity_chair": [
            "activity chair", "activity chairs",
            "course chair", "course chairs", "course co-chair", "course cochairs", "course co chairs",
            "chair"
        ],
        "series_co_chairs": ["series co-chairs", "series co chairs", "series co-chair", "series cochair"],
        "faculty": ["faculty", "speakers", "panelists"],
        "overview": ["overview", "program overview", "description"],
        # UPDATED agenda synonyms:
        "agenda": ["agenda", "program", "schedule", "topics", "topic"],
        "learning_objectives": ["learning objectives", "learning objective", "objectives"],
        "target_audience": ["target audience", "intended audience", "who should attend"]
    }
    # --------------------------------------------------------------------------------

    texts = [p.get_text(" ", strip=True) for p in paragraphs]

    indices = {k: None for k in heading_map}
    for i, p in enumerate(paragraphs):
        bold_text = paragraph_has_bold_heading(p)
        if bold_text:
            tl = _normalize_heading(bold_text)
            for key, kws in heading_map.items():
                for kw in kws:
                    if tl.startswith(kw):
                        indices[key] = i
                        break

    if all(v is None for v in indices.values()):
        for i, t in enumerate(texts):
            tl = _normalize_heading(t)
            for key, kws in heading_map.items():
                for kw in kws:
                    if tl.startswith(kw):
                        indices[key] = i
                        break

    used = set()

    def join_range(start_idx, end_idx):
        if start_idx is None:
            return ""
        if end_idx is None:
            end_idx = len(paragraphs)
        collected = []
        for j in range(start_idx + 1, end_idx):
            txt = paragraphs[j].get_text(" ", strip=True)
            if txt:
                collected.append(txt)
                used.add(j)
        return "\n".join(collected)

    activity_chair = join_range(indices["activity_chair"], indices["series_co_chairs"] or indices["faculty"])
    series_co_chairs = join_range(indices["series_co_chairs"], indices["faculty"])

    faculty = ""
    faculty_index = None
    for i, p in enumerate(paragraphs):
        bold_text = paragraph_has_bold_heading(p)
        if bold_text and _normalize_heading(bold_text).startswith("faculty"):
            faculty_index = i
            break
    if faculty_index is not None:
        faculty = join_range(faculty_index, indices["overview"])

    overview = ""
    overview_index = None
    for i, p in enumerate(paragraphs):
        bold_text = paragraph_has_bold_heading(p)
        if bold_text and _normalize_heading(bold_text).startswith("overview"):
            overview_index = i
            break
    if overview_index is None:
        overview_index = indices.get("overview")

    if overview_index is not None:
        next_heading = None
        for v in indices.values():
            if v is not None and v > overview_index:
                if next_heading is None or v < next_heading:
                    next_heading = v
        parts = []
        for j in range(overview_index + 1, next_heading if next_heading else len(paragraphs)):
            txt = paragraphs[j].get_text(" ", strip=True)
            if re.search(r"you['’]?re currently using an unsupported browser|skip to main content|ticket information", txt, re.I):
                continue
            if txt:
                parts.append(txt)
                used.add(j)
        overview = "\n".join(parts)

    agenda = join_range(indices["agenda"], indices["learning_objectives"])

    learning_objectives = ""
    if indices["learning_objectives"] is not None:
        start = indices["learning_objectives"]
        end = None
        if indices.get("target_audience") is not None and indices["target_audience"] > start:
            end = indices["target_audience"]
        learning_objectives = join_range(start, end)

    target_audience = ""
    provided_by = ""
    if indices["target_audience"] is not None:
        ta_idx = indices["target_audience"]
        if ta_idx + 1 < len(paragraphs):
            first_para = paragraphs[ta_idx + 1].get_text(" ", strip=True)
            target_audience = first_para
            used.add(ta_idx + 1)

            next_heading_idx = None
            for k_idx in indices.values():
                if k_idx is not None and k_idx > ta_idx:
                    if next_heading_idx is None or k_idx < next_heading_idx:
                        next_heading_idx = k_idx

            startp = ta_idx + 2
            endp = next_heading_idx
            if startp < len(paragraphs):
                provided_parts = []
                stop = endp if endp else len(paragraphs)
                for j in range(startp, stop):
                    txt = paragraphs[j].get_text(" ", strip=True)
                    if txt:
                        provided_parts.append(txt)
                        used.add(j)
                provided_by = "\n".join(provided_parts)

    others_list = []
    heading_indices = {idx for idx in indices.values() if idx is not None}
    if faculty_index is not None:
        heading_indices.add(faculty_index)

    for idx, p in enumerate(paragraphs):
        if idx in used or idx in heading_indices:
            continue
        txt = p.get_text(" ", strip=True)
        if not txt:
            continue
        if page_title and txt.strip() == page_title.strip():
            continue
        if re.search(r"you['’]?re currently using an unsupported browser|skip to main|ticket information", txt, re.I):
            continue
        others_list.append(txt)

    others = "\n".join(others_list).strip()

    if looks_like_disclosure(faculty):
        if faculty:
            others = (others + "\n" + faculty).strip()
        faculty = ""

    return {
        "activity_chair": activity_chair,
        "series_co_chairs": series_co_chairs,
        "faculty": faculty,
        "overview": overview,
        "agenda": agenda,
        "learning_objectives": learning_objectives,
        "target_audience": target_audience,
        "provided_by": provided_by,
        "others": others
    }

# --------------------------------------------------------------------------------
# 🔥 UPDATED: Expand fallback keyword list to include “Topics”
# --------------------------------------------------------------------------------
KEYHEADS = [
    "Activity Chair", "Series Co-Chairs", "Faculty",
    "Overview", "Agenda", "Topics",
    "Learning Objectives", "Target Audience",
    "Provided By", "Provided by", "Provided"
]
# --------------------------------------------------------------------------------


def extract_after_keyword_from_html(html, keyword):
    lower = html.lower()
    k = keyword.lower()
    idx = lower.find(k)
    if idx == -1:
        return ""
    start = idx + len(k)
    next_idx = None
    for kh in KEYHEADS:
        if kh.lower() == k:
            continue
        pos = lower.find(kh.lower(), start)
        if pos != -1:
            if next_idx is None or pos < next_idx:
                next_idx = pos
    end = next_idx if next_idx else min(len(html), start + 1400)
    chunk = html[start:end]
    text = strip_tags(chunk)
    text = re.sub(r"^[\s:\-–—]+", "", text).strip()
    if len(text) > 3000:
        text = text[:3000]
    return text


def extract_all_keywords_from_html(html):
    out = {}
    for kw in KEYHEADS:
        val = extract_after_keyword_from_html(html, kw)
        out[kw] = clean_text(val)
    return out


# ---------- Structured candidate parsing ----------
def parse_rich_text_sections(html, page_title=None):
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    candidates.extend(soup.select("bt-event-overview .content"))
    candidates.extend(soup.select("bt-event-overview .event-content"))
    candidates.extend(soup.select("div.content"))
    candidates.extend(soup.find_all("bt-rich-text"))
    candidates.extend(soup.select(".bt-rich-text"))

    uniq = []
    seen = set()
    for c in candidates:
        key = (c.name if hasattr(c, "name") else str(type(c))) + str(len(str(c)))
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    candidates = uniq

    for node in candidates:
        paragraphs = [p for p in node.find_all("p", recursive=True) if p.get_text(" ", strip=True)]
        if paragraphs:
            return _parse_paragraph_blocks(paragraphs, page_title=page_title)

        lists = node.find_all(["ul", "ol"], recursive=True)
        if lists:
            fake = []
            for lst in lists:
                for li in lst.find_all("li"):
                    t = li.get_text(" ", strip=True)
                    if t:
                        fake.append(BeautifulSoup(f"<p>{t}</p>", "html.parser").p)
            if fake:
                return _parse_paragraph_blocks(fake, page_title=page_title)

        texts = []
        for desc in node.descendants:
            if isinstance(desc, NavigableString):
                t = desc.strip()
                if t and len(t) > 3:
                    texts.append(t)
        if texts:
            fake = [BeautifulSoup(f"<p>{t}</p>", "html.parser").p for t in texts]
            return _parse_paragraph_blocks(fake, page_title=page_title)

    return None


# ---------- Event scraping ----------
def scrape_event_page(driver, url, save_raw_html_first5=True, raw_dir="raw_html", idx_for_save=None):
    print(f"Scraping event: {url}")
    driver.get(url)
    try:
        WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    except TimeoutException:
        pass
    time.sleep(1.0)

    page_html = driver.page_source

    if save_raw_html_first5 and idx_for_save is not None and idx_for_save <= 5:
        os.makedirs(raw_dir, exist_ok=True)
        safe_name = f"{idx_for_save:02d}_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:10] + ".html"
        with open(os.path.join(raw_dir, safe_name), "w", encoding="utf-8") as f:
            f.write(page_html)

    soup = BeautifulSoup(page_html, "html.parser")

    title = ""
    h1 = soup.select_one("app-root bt-event-main header h1, bt-event-main header h1, header h1")
    if h1 and h1.get_text(strip=True):
        title = clean_text(h1.get_text(" ", strip=True))
    else:
        meta_title = soup.select_one('meta[property="og:title"], meta[name="title"]')
        if meta_title and meta_title.get("content"):
            title = clean_text(meta_title.get("content"))
        else:
            h_any = soup.select_one("h1, h2")
            if h_any and h_any.get_text(strip=True):
                title = clean_text(h_any.get_text(" ", strip=True))
            else:
                try:
                    elem = driver.find_element(By.XPATH, "//app-root/bt-event-main//h1")
                    title = clean_text(elem.text)
                except Exception:
                    title = ""

    start_date = ""
    end_date = ""
    try:
        sed = soup.select_one("bt-start-end-date")
        if sed:
            sed_text = sed.get_text(" ", strip=True)
            if "—" in sed_text or "-" in sed_text:
                parts = re.split(r"\s+[-—–]\s+", sed_text)
                if len(parts) >= 2:
                    start_date = clean_text(parts[0])
                    end_date = clean_text(parts[1])
                else:
                    start_date = clean_text(sed_text)
            else:
                date_matches = re.findall(
                    r"[A-Za-z]{3,}\s*,\s*\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}(?:[,\s]\d{1,2}:\d{2}\s(?:AM|PM|am|pm)?)?",
                    sed_text)
                if len(date_matches) >= 2:
                    start_date = clean_text(date_matches[0])
                    end_date = clean_text(date_matches[1])
                else:
                    start_date = clean_text(sed_text)
        else:
            s1 = soup.select_one(".start-date, .event-start-date, .event__dateTime")
            if s1:
                start_date = clean_text(s1.get_text(" ", strip=True))
            s2 = soup.select_one(".end-date, .event-end-date")
            if s2:
                end_date = clean_text(s2.get_text(" ", strip=True))
    except Exception:
        pass

    if not start_date or not end_date:
        body_text = soup.get_text(" ", strip=True)
        date_pattern = r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z][,]?\s\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}(?:[,\s]\d{1,2}:\d{2}\s(?:AM|PM|am|pm))?"
        matches = re.findall(date_pattern, body_text)
        if matches:
            if not start_date:
                start_date = clean_text(matches[0])
            if len(matches) > 1 and not end_date:
                end_date = clean_text(matches[1])
        if not start_date or not end_date:
            loose = re.findall(
                r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s*\d{4}(?:[,\s]\d{1,2}:\d{2}\s(?:AM|PM|am|pm))?",
                body_text)
            if loose:
                if not start_date:
                    start_date = clean_text(loose[0])
                if len(loose) > 1 and not end_date:
                    end_date = clean_text(loose[1])

    sections = parse_rich_text_sections(page_html, page_title=title)
    if sections is None:
        kw_data = extract_all_keywords_from_html(page_html)
        sections = {
            "activity_chair": kw_data.get("Activity Chair", ""),
            "series_co_chairs": kw_data.get("Series Co-Chairs", ""),
            "faculty": kw_data.get("Faculty", ""),
            "overview": kw_data.get("Overview", ""),
            "agenda": kw_data.get("Agenda", "") or kw_data.get("Topics", ""),
            "learning_objectives": kw_data.get("Learning Objectives", ""),
            "target_audience": kw_data.get("Target Audience", ""),
            "provided_by": kw_data.get("Provided By", "") or kw_data.get("Provided by", ""),
            "others": ""
        }
    else:

        missing = [k for k, v in sections.items()
                   if not v and k in (
                        "activity_chair", "series_co_chairs",
                        "faculty", "overview", "agenda",
                        "learning_objectives", "target_audience")]

        if missing:
            kw_data = extract_all_keywords_from_html(page_html)

            if "activity_chair" in missing:
                sections["activity_chair"] = sections["activity_chair"] or kw_data.get("Activity Chair", "")

            if "series_co_chairs" in missing:
                sections["series_co_chairs"] = sections["series_co_chairs"] or kw_data.get("Series Co-Chairs", "")

            if "faculty" in missing:
                raw_fac = kw_data.get("Faculty", "")
                if (
                    re.search(r"<(strong|b)[^>]>\s*faculty\s</\1>", page_html, re.I)
                    or re.search(r"\b(MD|PhD|DO|Professor|Dr\.)\b", raw_fac, re.I)
                ):
                    if not looks_like_disclosure(raw_fac):
                        sections["faculty"] = raw_fac
                    else:
                        sections["others"] = (sections.get("others", "") + "\n" + raw_fac).strip()
                else:
                    if raw_fac:
                        sections["others"] = (sections.get("others", "") + "\n" + raw_fac).strip()

            if "overview" in missing:
                sections["overview"] = sections["overview"] or kw_data.get("Overview", "")

            if "agenda" in missing:
                sections["agenda"] = (
                    sections["agenda"]
                    or kw_data.get("Agenda", "")
                    or kw_data.get("Topics", "")
                )

            if "learning_objectives" in missing:
                sections["learning_objectives"] = (
                    sections["learning_objectives"] or kw_data.get("Learning Objectives", "")
                )

            if "target_audience" in missing:
                sections["target_audience"] = (
                    sections["target_audience"] or kw_data.get("Target Audience", "")
                )

            if not sections.get("provided_by"):
                sections["provided_by"] = kw_data.get("Provided By", "") or kw_data.get("Provided by", "")

    for k in [
        "activity_chair", "series_co_chairs", "faculty",
        "overview", "agenda", "learning_objectives",
        "target_audience", "provided_by", "others"
    ]:
        sections.setdefault(k, "")

    location = ""
    map_link = ""
    loc_el = soup.select_one(".event__venue, .venue, .event-location, .location, address")
    if loc_el:
        location = clean_text(loc_el.get_text(" ", strip=True))
        a = loc_el.find("a", href=True)
        if a and a.get("href"):
            map_link = a.get("href").strip()
    else:
        a_maps = soup.find("a", href=re.compile(r"(google\.com/maps|maps\.place|maps.app.goo.gl|bing\.com/maps)"))
        if a_maps and a_maps.get("href"):
            map_link = a_maps.get("href").strip()
            parent = a_maps.find_parent()
            if parent:
                txt = parent.get_text(" ", strip=True)
                if txt and len(txt) > 10:
                    location = clean_text(txt)

    result = {
        "url": url,
        "title": title or "",
        "start_date": start_date or "",
        "end_date": end_date or "",
        "activity_chair": sections.get("activity_chair", ""),
        "series_co_chairs": sections.get("series_co_chairs", ""),
        "faculty": sections.get("faculty", ""),
        "overview": sections.get("overview", ""),
        "agenda": sections.get("agenda", ""),
        "learning_objectives": sections.get("learning_objectives", ""),
        "target_audience": sections.get("target_audience", ""),
        "provided_by": sections.get("provided_by", ""),
        "others": sections.get("others", ""),
        "location": location or "",
        "map_link": map_link or "",
    }
    return result


# ---------- Listing helpers ----------
def select_all_dates(driver):
    wait = WebDriverWait(driver, 20)
    try:
        date_group = wait.until(EC.presence_of_element_located((By.XPATH,
            "//div[contains(@class,'category-group')][.//div[@class='category-title' and normalize-space()='Date']]")))
    except TimeoutException:
        return False
    try:
        all_dates_btn = date_group.find_element(By.XPATH, ".//button[normalize-space()='All dates']")
        try:
            all_dates_btn.click()
            time.sleep(1.5)
            return True
        except Exception:
            driver.execute_script("arguments[0].click();", all_dates_btn)
            time.sleep(1.2)
            return True
    except NoSuchElementException:
        return False
    except Exception:
        return False

def load_all_events(driver, max_rounds_without_growth=3):
    wait = WebDriverWait(driver, 30)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "bt-event-listing-aspen-main")))
    except TimeoutException:
        return []

    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "bt-event-listing-aspen-main a.grid-item")))
    except TimeoutException:
        pass

    last_count = 0
    stagnant_rounds = 0
    rounds = 0

    while True:
        rounds += 1
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            pass

        time.sleep(2)

        try:
            load_more_btns = driver.find_elements(
                By.XPATH,
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'load more') "
                "or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'show more')]"
            )
            if load_more_btns:
                try:
                    driver.execute_script("arguments[0].click();", load_more_btns[0])
                    time.sleep(1.5)
                except StaleElementReferenceException:
                    pass
        except Exception:
            pass

        try:
            cards = driver.find_elements(By.CSS_SELECTOR, "bt-event-listing-aspen-main a.grid-item")
            count = len(cards)
        except Exception:
            count = 0

        print(f"Found {count} event cards so far... (round {rounds})")

        if count > last_count:
            last_count = count
            stagnant_rounds = 0
        else:
            stagnant_rounds += 1
            if stagnant_rounds >= max_rounds_without_growth:
                break

        if rounds > 60:
            break

    hrefs = []
    try:
        cards = driver.find_elements(By.CSS_SELECTOR, "bt-event-listing-aspen-main a.grid-item")
    except Exception:
        cards = []

    for c in cards:
        try:
            href = c.get_attribute("href")
            if href:
                hrefs.append(href)
        except Exception:
            continue

    seen = set()
    urls = []
    for h in hrefs:
        if not h:
            continue
        full = h if h.startswith("http") else urljoin(EVENT_BASE_URL, h)
        if full not in seen:
            seen.add(full)
            urls.append(full)

    print(f"Total unique event URLs: {len(urls)}")
    return urls


# ---------- Main ----------
def main():
    driver = init_driver(headless=False)
    all_rows = []

    try:
        print("Opening listing:", EVENT_LISTING_URL)
        driver.get(EVENT_LISTING_URL)
        time.sleep(1.5)

        try:
            ok = select_all_dates(driver)
            print("select_all_dates ->", ok)
        except Exception as e:
            print("select_all_dates raised:", e)

        event_urls = load_all_events(driver)

        if not event_urls:
            print("No event URLs found. Exiting.")
            return

        print(f"Found {len(event_urls)} event URLs — scraping...")

        first5_saved = False

        for idx, url in enumerate(tqdm(event_urls, desc="Events", unit="evt"), start=1):

            print(f"\n[{idx}/{len(event_urls)}] {url}")

            row = scrape_event_page(driver, url, save_raw_html_first5=True,
                                    raw_dir="raw_html", idx_for_save=idx)

            all_rows.append(row)

            if not first5_saved and len(all_rows) >= 5:
                pd.DataFrame(all_rows[:5]).to_excel("preview_first5.xlsx", index=False)
                print("Saved preview_first5.xlsx (first 5 rows).")
                first5_saved = True

    finally:
        driver.quit()

    df = pd.DataFrame(all_rows, columns=[
        "url", "title", "start_date", "end_date",
        "activity_chair", "series_co_chairs", "faculty",
        "overview", "agenda", "learning_objectives",
        "target_audience", "provided_by", "others",
        "location", "map_link"
    ])

    out = "vindico_live_events.xlsx"
    df.to_excel(out, index=False)
    print(f"Saved {len(df)} rows to {out}")


if _name_ == "_main_":
    main()