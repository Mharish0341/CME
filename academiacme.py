import time, re, json, unicodedata
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service as ChromeService
from bs4 import BeautifulSoup, Tag
import pandas as pd

# ----------------- CONFIG -----------------
START_URL = "https://academiccme.com/courses/"
OUTPUT_XLSX = "academiccme_extracted data2.xlsx"
EARLY_SNAPSHOT = "academiccme_additionalinfo_first5.xlsx"
MAX_PAGES = 30
HEADLESS = True
CHROMEDRIVER_PATH = None
# ------------------------------------------

def setup_driver(headless=True, chromedriver_path=None):
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1920,1200")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    if chromedriver_path:
        service = ChromeService(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=opts)
    else:
        driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(60)
    return driver

def _safe_text(elem):
    if not elem:
        return ""
    return " ".join(elem.get_text(" ", strip=True).split())

def normalize_type(type_text):
    if not type_text:
        return ""
    t = type_text.strip().lower()
    t = re.sub(r"^view\s+", "", t)
    return t

# ------------- Listing extraction -------------
def extract_grid_items_from_soup(soup, base_url=START_URL):
    items = []
    for a in soup.select("a.elementor-button.elementor-button-link"):
        txt = a.get_text(" ", strip=True)
        href = a.get("href")
        if not href:
            continue
        # skip if href is just the listing root
        abs_href = urljoin(base_url, href)
        if abs_href.rstrip("/") == START_URL.rstrip("/"):
            continue
        if txt.lower().startswith("view "):
            t = normalize_type(txt)
            container = a.find_parent(["article","div"], class_=re.compile(r"jet-listing|listing|grid", re.I)) or a.parent
            title = _safe_text(container.find(["h1","h2","h3","h4"])) if container else ""
            area_el = container.select_one(".jet-listing-dynamic-terms_link, .jet-listing-dynamic-field_content, .post-meta, .course-category") if container else None
            area = _safe_text(area_el) if area_el else ""
            credits_el = container.select_one(".jet-listing-dynamic-terms__link, .elementor-widget-jet-listing-dynamic-terms, .credits") if container else None
            grid_credits = _safe_text(credits_el)
            items.append({
                "detail_link": abs_href,
                "grid_title": title,
                "grid_area": area,
                "grid_type": t,
                "grid_credits": grid_credits
            })
    # dedupe
    unique=[]; seen=set()
    for it in items:
        if it["detail_link"] not in seen:
            unique.append(it); seen.add(it["detail_link"])
    return unique

def click_next_on_listing(driver):
    time.sleep(0.6)
    try:
        next_el = driver.find_element(By.CSS_SELECTOR, "div.jet-filters-pagination__item.prev-next.next")
        link = next_el.find_element(By.CSS_SELECTOR, ".jet-filters-pagination__link")
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
        try:
            link.click()
        except Exception:
            ActionChains(driver).move_to_element(link).click(link).perform()
        time.sleep(1.0)
        return True
    except Exception:
        try:
            nxt = driver.find_element(By.LINK_TEXT, "Next")
            nxt.click(); time.sleep(1.0); return True
        except Exception:
            return False

# ------------- Common field heuristics -------------
def extract_dates_from_text(text):
    start = end = ""
    m = re.search(r"([A-Z][a-z]{2,}\s+\d{1,2},\s*\d{4})\s*(?:to|-|—)\s*([A-Z][a-z]{2,}\s+\d{1,2},\s*\d{4})", text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.search(r"(Start Date|Date|Available)\s*[:\-]?\s*([A-Z][a-z]{2,}\s+\d{1,2},\s*\d{4})", text, re.I)
    if m:
        return m.group(2).strip(), ""
    m = re.search(r"([A-Z][a-z]{2,}\s+\d{1,2},\s*\d{4})", text)
    if m:
        return m.group(1).strip(), ""
    return "", ""

def extract_earned_credits(text):
    m = re.search(r"(EARNed Credits.*?([\d\.]+))", text, re.I|re.S)
    if m: return m.group(2)
    m2 = re.search(r"([\d\.]+)\s*(AMA PRA|Credit|Credits|Contact Hour)", text, re.I)
    if m2: return m2.group(1)
    return ""

# ------------- Tabs / panels helpers -------------
def click_tabs_and_get_panels(driver):
    panels=[]
    try:
        tabs = driver.find_elements(By.CSS_SELECTOR, "div.e-n-tabs-heading button.e-n-tab-title")
        if not tabs:
            return []
        for i, tab in enumerate(tabs):
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab)
                tab.click()
            except Exception:
                try:
                    ActionChains(driver).move_to_element(tab).click(tab).perform()
                except Exception:
                    pass
            time.sleep(0.4)
            aria = tab.get_attribute("aria-controls")
            html = ""
            if aria:
                try:
                    panel = driver.find_element(By.ID, aria)
                    html = panel.get_attribute("innerHTML")
                except Exception:
                    html = ""
            else:
                panels_vis = driver.find_elements(By.CSS_SELECTOR, "div[id^='e-n-tab-content-']")
                for p in panels_vis:
                    style = p.get_attribute("style") or ""
                    if "display: none" not in style:
                        html = p.get_attribute("innerHTML"); break
                if not html and panels_vis:
                    html = panels_vis[0].get_attribute("innerHTML")
            text = BeautifulSoup(html or "", "lxml").get_text(" ", strip=True)
            title = (tab.text or f"tab_{i}").strip()
            panels.append((title, html or "", text))
    except Exception:
        pass
    return panels

def expand_accordions_in_scope(driver, scope_css=None):
    scope = scope_css if scope_css else ""
    try:
        selectors = [f"{scope} summary", f"{scope} .e-n-accordion-item-title-icon", f"{scope} .e-n-accordion-item-title", f"{scope} .jet-accordion__title", f"{scope} .accordion-toggle"]
        buttons=[]
        for sel in selectors:
            try:
                elems = driver.find_elements(By.CSS_SELECTOR, sel)
                if elems: buttons.extend(elems)
            except Exception:
                pass
        seen=set()
        for b in buttons:
            try:
                html_id = b.get_attribute("outerHTML")[:200]
                if html_id in seen: continue
                seen.add(html_id)
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                try:
                    b.click()
                except Exception:
                    try:
                        ActionChains(driver).move_to_element(b).click(b).perform()
                    except Exception:
                        pass
                time.sleep(0.12)
            except Exception:
                continue
    except Exception:
        pass

def extract_accordions_from_soup(soup):
    acc={}
    for det in soup.select("details.e-n-accordion-item, details"):
        try:
            summary = det.find("summary")
            heading = _safe_text(summary) or _safe_text(det.find(lambda t: t.name in ["h3","h4","strong"]))
            for s in det.find_all("summary"):
                s.extract()
            content_text = _safe_text(det)
            if heading:
                acc[heading] = content_text
        except Exception:
            continue
    for header in soup.select(".e-n-accordion-item-title-text, .e-n-accordion-item-title, .accordion-title, .jet-accordion__title"):
        heading = _safe_text(header)
        if not heading:
            continue
        parent = header.find_parent()
        content_text = ""
        if parent:
            sib = parent.find_next_sibling()
            if sib:
                content_text = _safe_text(sib)
        if not content_text:
            content_text = _safe_text(parent)
        if heading and heading not in acc:
            acc[heading] = content_text
    return acc

# ------------- Program Overview helpers (faculty removed) -------------
def extract_program_overview_fields(panel_html):
    """
    Extract overview_heading, overview, who_should_attend, provided_by
    (faculty extraction removed — handled separately by extract_faculty_from_panel).
    - If Provided By contains an <img>, returns the image 'src' (URL).
    - Otherwise returns plain text found in the icon-box description.
    """
    soup = BeautifulSoup(panel_html or "", "lxml")

    def _safe_text(elem):
        if not elem:
            return ""
        return " ".join(elem.get_text(" ", strip=True).split())

    out = {"overview_heading": "", "overview": "", "who_should_attend": "", "provided_by": ""}

    # ----- Overview heading + paragraph(s) -----
    heading_tag = soup.find(lambda t: t.name in ["h1","h2","h3","h4"] and "overview" in t.get_text(" ", strip=True).lower())
    if heading_tag:
        out["overview_heading"] = _safe_text(heading_tag)
    else:
        for htag in ["h1","h2","h3","h4"]:
            h = soup.find(htag)
            if h and len(_safe_text(h)) > 3:
                out["overview_heading"] = _safe_text(h)
                heading_tag = h
                break

    overview_texts = []
    if heading_tag:
        for sib in heading_tag.find_next_siblings():
            if getattr(sib, "name", None) in ["h1","h2","h3","h4"]:
                break
            dyn = sib.select_one(".jet-listing-dynamic-field__content, .jet-listing-dynamic-field")
            if dyn:
                txt = _safe_text(dyn)
                if txt:
                    overview_texts.append(txt)
                    break
            if sib.select_one(".elementor-icon-box-title, .elementor-icon-box-wrapper"):
                break
            for p in sib.find_all("p"):
                txt = _safe_text(p)
                if txt and "who should attend" not in txt.lower() and "provided by" not in txt.lower():
                    overview_texts.append(txt)
            if overview_texts:
                break

    if not overview_texts:
        for p in soup.find_all("p"):
            t = _safe_text(p)
            if t and len(t) > 40 and "who should attend" not in t.lower():
                overview_texts.append(t)
                break

    out["overview"] = "\n\n".join(overview_texts).strip()

    # ----- Strict extraction for icon-box content -----
    def extract_icon_box_content_or_img(soup_local, label_text):
        title_node = soup_local.find(lambda tag: tag.name in ["h3","h2","h4","span","strong"] and label_text.lower() in tag.get_text(" ", strip=True).lower())
        if not title_node:
            return ""
        anc = title_node
        target = None
        for _ in range(6):
            if anc is None:
                break
            cls = " ".join(anc.get("class") or [])
            if "elementor-icon-box-content" in cls or "elementor-icon-box-wrapper" in cls or "elementor-widget-container" in cls:
                target = anc
                break
            anc = anc.parent
        if target is None:
            target = title_node.find_parent()

        if target:
            desc = target.select_one(".elementor-icon-box-description")
            if desc:
                img = desc.find("img")
                if img and img.get("src"):
                    return img.get("src").strip()
                desc_text = _safe_text(desc)
                if desc_text:
                    return desc_text
            img_any = target.find("img")
            if img_any and img_any.get("src"):
                return img_any.get("src").strip()
            ps = [p for p in target.find_all("p") if p.get_text(strip=True) and label_text.lower() not in p.get_text(" ",strip=True).lower()]
            if ps:
                texts = [_safe_text(p) for p in ps]
                texts = [t for i,t in enumerate(texts) if t and t not in texts[:i]]
                return "\n\n".join(texts).strip()

        for sib in title_node.find_next_siblings():
            if getattr(sib, "name", None) in ["h1","h2","h3","h4"]:
                break
            img = sib.find("img")
            if img and img.get("src"):
                return img.get("src").strip()
            for p in sib.find_all("p"):
                t = _safe_text(p)
                if t and label_text.lower() not in t.lower():
                    return t
        return ""

    out["who_should_attend"] = extract_icon_box_content_or_img(soup, "Who Should Attend")
    out["provided_by"] = extract_icon_box_content_or_img(soup, "Provided By")

    return out

def extract_faculty_from_panel(panel_html):
    """
    Strict extractor for faculty from panel HTML.
    Returns a single string containing faculty entries separated by newlines.
    The extraction only searches FORWARD from a 'Course Faculty' / 'Faculty' heading
    and looks for the first .jet-listing-grid / .jet-listing container after that heading,
    then extracts the items inside that container.
    """
    def _clean_text(elem):
        if not elem:
            return ""
        return " ".join(elem.get_text(" ", strip=True).replace("\xa0", " ").split())

    soup = BeautifulSoup(panel_html or "", "lxml")
    faculty_heading = soup.find(lambda t: t.name in ["h1", "h2", "h3", "h4", "div"] and ("course faculty" in t.get_text(" ", strip=True).lower() or t.get_text(" ", strip=True).strip().lower() == "faculty"))
    faculty_lines = []

    if faculty_heading:
        faculty_container = None
        for el in faculty_heading.next_elements:
            if isinstance(el, Tag):
                cls = " ".join(el.get("class") or [])
                if "jet-listing-grid" in cls or "jet-listing-grid__items" in cls or "jet-listing" in cls:
                    faculty_container = el
                    break
                if el.name == "div" and any(k in cls for k in ["jet-listing-grid", "jet-listing-grid__items", "jet-listing"]):
                    faculty_container = el
                    break

        if faculty_container:
            items = faculty_container.select(".jet-listing-grid_item, .jet-listing-dynamic-post, .jet-listing-grid_item")
            if not items:
                items = [c for c in faculty_container.find_all("div", recursive=False) if _clean_text(c)]
            for item in items:
                img = item.find("img")
                if img and img.get("alt"):
                    faculty_lines.append(_clean_text(BeautifulSoup(img.get("alt"), "lxml")))
                first_field = item.select_one(".jet-listing-dynamic-field__content, .jet-listing-dynamic-field")
                if first_field:
                    name_txt = _clean_text(first_field)
                    if name_txt:
                        faculty_lines.append(name_txt)
                other_fields = item.select(".jet-listing-dynamic-field__content, .jet-listing-dynamic-field")
                if other_fields and len(other_fields) > 1:
                    for f in other_fields[1:]:
                        t = _clean_text(f)
                        if t:
                            for sub in [s.strip() for s in t.splitlines() if s.strip()]:
                                faculty_lines.append(sub)
                else:
                    for p in item.find_all("p"):
                        t = _clean_text(p)
                        if t:
                            for sub in [s.strip() for s in t.splitlines() if s.strip()]:
                                faculty_lines.append(sub)

    # preserve order but remove exact duplicates
    seen = set()
    final = []
    for ln in faculty_lines:
        if not ln:
            continue
        if ln in seen:
            continue
        seen.add(ln)
        final.append(ln)

    return "\n".join(final).strip()

def extract_learning_objectives(panel_html):
    soup = BeautifulSoup(panel_html or "", "lxml")
    texts=[]
    for card in soup.select(".jet-listing-grid .jet-listing-grid_item, .jet-listing-grid_item, .jet-listing .jet-listing-dynamic-field, li"):
        t = _safe_text(card)
        if t: texts.append(t)
    return "\n\n".join(dict.fromkeys(texts))

def extract_agenda(panel_html):
    return _safe_text(BeautifulSoup(panel_html or "", "lxml"))

# ------------- Detail extraction (uses the fixed program overview) -------------
def find_additional_tab_title_variants(title_text):
    t = (title_text or "").strip().lower()
    keywords = ["additional", "additional course", "additional course info", "additional course information", "additional info"]
    for kw in keywords:
        if kw in t:
            return True
    return False

def extract_detail_page(driver, url):
    result = {
        "url": url, "title": "", "start_date": "", "end_date": "", "earned_credits": "",
        "overview_heading": "", "overview": "", "who_should_attend": "", "provided_by": "", "faculty": "",
        "learning_objectives": "", "agenda": "", "additional_info": {}
    }
    driver.get(url)
    time.sleep(1.0)

    soup = BeautifulSoup(driver.page_source, "lxml")

    # TITLE FIX: prefer the h2 with the exact classes inside front-matter when available
    fm = soup.find(lambda tag: tag.name=="div" and "front-matter" in " ".join(tag.get("class") or []).lower()) or soup
    title_el = fm.select_one("h2.elementor-heading-title.elementor-size-default")
    if title_el:
        result["title"] = _safe_text(title_el)
    else:
        title_el = soup.find(["h1","h2"], class_=re.compile(r"elementor-heading-title|entry-title", re.I)) or soup.find(["h1","h2"])
        result["title"] = _safe_text(title_el) if title_el else (soup.title.string.strip() if soup.title else "")

    page_text = soup.get_text(" ", strip=True)
    result["earned_credits"] = extract_earned_credits(page_text)
    sdt, edt = extract_dates_from_text(page_text)
    result["start_date"], result["end_date"] = sdt, edt

    # Tabs
    panels = click_tabs_and_get_panels(driver)  # list of (title, html, text)
    panel_map = {title.strip().lower(): (html, text) for title, html, text in panels}

    # Program Overview: find tab or fallback
    prog_html = ""
    for title_key in panel_map:
        if "program" in title_key or "overview" in title_key or "tweetorial" in title_key or title_key.strip() == "overview":
            prog_html = panel_map[title_key][0]; break
    if not prog_html and panels:
        prog_html = panels[0][1]
    if prog_html:
        pov = extract_program_overview_fields(prog_html)
        result.update(pov)
        # extract faculty strictly from the program/overview panel (separate function)
        faculty_text = extract_faculty_from_panel(prog_html)
        # if not found, try the full current document HTML as fallback
        if not faculty_text:
            faculty_text = extract_faculty_from_panel(driver.page_source)
        result["faculty"] = faculty_text

    # Learning objectives
    lo_html = ""
    for title_key in panel_map:
        if "learning" in title_key or "objective" in title_key:
            lo_html = panel_map[title_key][0]; break
    result["learning_objectives"] = extract_learning_objectives(lo_html or "")

    # Agenda
    ag_html = ""
    for title_key in panel_map:
        if "agenda" in title_key:
            ag_html = panel_map[title_key][0]; break
    result["agenda"] = extract_agenda(ag_html or "")

    # Additional Course Info: find panel and expand accordions
    add_panel_id = None
    add_panel_html = ""
    if panels:
        for title, html, txt in panels:
            if find_additional_tab_title_variants(title):
                try:
                    tab_elem = driver.find_element(By.XPATH, f"//div[contains(@class,'e-n-tabs-heading')]//button[contains(normalize-space(.), \"{title}\")]")
                    add_panel_id = tab_elem.get_attribute("aria-controls")
                except Exception:
                    add_panel_id = None
                add_panel_html = html
                break

    if add_panel_id:
        expand_accordions_in_scope(driver, scope_css=f"#{add_panel_id}")
        try:
            panel_dom = driver.find_element(By.ID, add_panel_id)
            add_panel_html = panel_dom.get_attribute("innerHTML")
        except Exception:
            pass
    else:
        expand_accordions_in_scope(driver, scope_css=None)
        # fallback: try to find Additional Course Information heading in current page
        if not add_panel_html:
            h = soup.find(lambda tag: tag.name in ["h2","h3","h4","div","p"] and "additional course" in tag.get_text(" ",strip=True).lower())
            if h:
                parent = h.find_parent()
                add_panel_html = str(parent) if parent else ""

    soup_after = BeautifulSoup(driver.page_source, "lxml")
    add_soup = BeautifulSoup(add_panel_html or "", "lxml") if add_panel_html else soup_after
    additional_dict = extract_accordions_from_soup(add_soup)
    if not additional_dict:
        additional_dict = extract_accordions_from_soup(soup_after)
    result["additional_info"] = additional_dict

    # final faculty fallback if not found earlier (keeps your original regex fallback)
    if not result.get("faculty"):
        m = re.search(r"(Faculty|COURSE FACULTY|Course Faculty)(.*?)(Learning Objectives|Agenda|Additional Course Info|$)", driver.page_source, re.S|re.I)
        if m:
            result["faculty"] = " ".join(m.group(2).split())

    return result

# -------------- Main --------------
def main():
    driver = setup_driver(HEADLESS, CHROMEDRIVER_PATH)
    try:
        driver.get(START_URL)
        time.sleep(1.0)

        all_grid=[]
        page_no=0
        while page_no < MAX_PAGES:
            page_no += 1
            soup = BeautifulSoup(driver.page_source, "lxml")
            items = extract_grid_items_from_soup(soup, base_url=START_URL)
            print(f"[listing page {page_no}] found {len(items)} items")
            for it in items:
                if not any(existing["detail_link"]==it["detail_link"] for existing in all_grid):
                    # skip the START_URL itself (double-check)
                    if it["detail_link"].rstrip("/") == START_URL.rstrip("/"):
                        continue
                    all_grid.append(it)
            if not click_next_on_listing(driver):
                break
            time.sleep(1.0)

        print(f"Total unique detail pages discovered: {len(all_grid)}")

        rows=[]
        for idx, item in enumerate(all_grid, start=1):
            url = item["detail_link"]
            print(f"[{idx}/{len(all_grid)}] scraping {url}")
            try:
                data = extract_detail_page(driver, url)
            except Exception as e:
                print("Detail extraction error:", e)
                data = {"url":url,"title":item.get("grid_title",""),"start_date":"","end_date":"","earned_credits":"","overview_heading":"","overview":"","who_should_attend":"","provided_by":"","faculty":"","learning_objectives":"","agenda":"","additional_info":{}}

            row = {
                "sno": idx,
                "url": url,
                "title": data.get("title",""),
                "start_date": data.get("start_date",""),
                "end_date": data.get("end_date",""),
                "area": item.get("grid_area",""),
                "type": item.get("grid_type",""),
                "earned_credits_detail": data.get("earned_credits",""),
                "grid_credits": item.get("grid_credits",""),
                "overview_heading": data.get("overview_heading",""),
                "overview": data.get("overview",""),
                "who_should_attend": data.get("who_should_attend",""),
                "provided_by": data.get("provided_by",""),
                "faculty": data.get("faculty",""),
                "learning_objectives": data.get("learning_objectives",""),
                "agenda": data.get("agenda",""),
            }

            for heading, content in data.get("additional_info", {}).items():
                col = heading.strip()
                if col in row and row[col]:
                    row[col] = row[col] + "\n\n" + content
                else:
                    row[col] = content

            rows.append(row)

            # Early snapshot after first 5 rows
            if idx == 5:
                df_temp = pd.DataFrame(rows)
                cols = list(df_temp.columns)
                cols_order = ["sno","url"] + [c for c in cols if c not in ("sno","url")]
                df_temp = df_temp[cols_order]
                df_temp.to_excel(EARLY_SNAPSHOT, index=False)
                print(f"Saved first 5 rows to {EARLY_SNAPSHOT}")

        # Final save
        df = pd.DataFrame(rows)
        if "sno" not in df.columns:
            df.insert(0,"sno", range(1, len(df)+1))
        if "url" not in df.columns:
            df.insert(1,"url", [r.get("url","") for r in rows])
        cols = list(df.columns)
        cols_order = ["sno","url"] + [c for c in cols if c not in ("sno","url")]
        df = df[cols_order]
        df.to_excel(OUTPUT_XLSX, index=False)
        print("Final saved to", OUTPUT_XLSX)

    finally:
        driver.quit()

if _name_ == "_main_":
    main()