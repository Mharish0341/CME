import time
import pandas as pd
from tqdm import tqdm

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

driver = webdriver.Chrome()

base_url = "https://www.continuingcertification.org/activity-search/"
driver.get(base_url)

index_data = []
page_bar = tqdm(desc="Collecting pages", unit="page")

while True:
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "td.title a"))
    )

    link_elems = driver.find_elements(By.CSS_SELECTOR, "td.title a")
    for a in link_elems:
        href = a.get_attribute("href")
        title = a.text.strip()
        if href:
            index_data.append({"Activity URL": href, "Title": title})

    page_bar.update(1)

    try:
        next_link = driver.find_element(By.CSS_SELECTOR, "a.next.page-numbers")
        next_href = next_link.get_attribute("href")
        if next_href:
            driver.get(next_href)
            time.sleep(2)
        else:
            break
    except Exception:
        break

page_bar.close()

unique_seen = set()
deduped_index = []
for item in index_data:
    url = item["Activity URL"]
    if url not in unique_seen:
        unique_seen.add(url)
        deduped_index.append(item)

data = []

try:
    for item in tqdm(deduped_index, desc="Scraping activity details"):
        link = item["Activity URL"]
        title = item["Title"]

        driver.get(link)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1, h2.provider"))
            )
        except Exception:
            continue

        row = {
            "Source URL": base_url,
            "Activity URL": link,
            "Title": title,
        }

        try:
            provider_link_elem = driver.find_element(
                By.XPATH,
                "//a[contains(@class,'btn') and contains(normalize-space(),'Register for this Activity')]"
            )
            row["Provider Link"] = provider_link_elem.get_attribute("href")
        except Exception:
            row["Provider Link"] = ""

        info_blocks = driver.find_elements(
            By.CSS_SELECTOR,
            "div.activity-id, div.expiration, div.format-type, div.credit, div.fee"
        )

        provider_elems = driver.find_elements(By.CSS_SELECTOR, "h2.provider")
        for prov in provider_elems:
            text = prov.text.strip()
            if text.lower().startswith("cme provider:"):
                row["CME Provider"] = text.split(":", 1)[1].strip()
            else:
                row["CME Provider"] = text

        for block in info_blocks:
            try:
                label_elem = block.find_element(By.CSS_SELECTOR, "h4.info-title")
                value_elem = block.find_element(By.TAG_NAME, "span")
                key = label_elem.text.strip()
                value = value_elem.text.strip()
                row[key] = value
            except Exception:
                continue

        try:
            desc_h = driver.find_element(
                By.XPATH,
                "//h5[@class='description' and normalize-space()='Description of CME Course']"
            )
            desc_paras = []
            siblings = desc_h.find_elements(By.XPATH, "following-sibling::*")
            for sib in siblings:
                if sib.tag_name.lower() == "p":
                    text = sib.text.strip()
                    if text:
                        desc_paras.append(text)
                else:
                    break
            row["Description of CME Course"] = "\n\n".join(desc_paras) if desc_paras else ""
        except Exception:
            row["Description of CME Course"] = ""

        try:
            disc_h = driver.find_element(
                By.XPATH,
                "//h5[@class='description' and normalize-space()='Disclaimers']"
            )
            disc_paras = []
            siblings = disc_h.find_elements(By.XPATH, "following-sibling::*")
            for sib in siblings:
                if sib.tag_name.lower() == "p":
                    text = sib.text.strip()
                    if text:
                        disc_paras.append(text)
                else:
                    break
            row["Disclaimers"] = "\n\n".join(disc_paras) if disc_paras else ""
        except Exception:
            row["Disclaimers"] = ""

        try:
            approval_div = driver.find_element(By.CSS_SELECTOR, "div.approval-table")
            approval_ps = approval_div.find_elements(By.CSS_SELECTOR, "div.approval-list p")
            approvals = [p.text.strip() for p in approval_ps if p.text.strip()]
            row["ABMS Member Board Approvals by Type"] = "; ".join(approvals) if approvals else ""
        except Exception:
            row["ABMS Member Board Approvals by Type"] = ""

        try:
            more_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.ID, "show-activity"))
            )
            driver.execute_script("arguments[0].click();", more_btn)
            time.sleep(1.5)
        except Exception:
            pass

        try:
            commercial_span = driver.find_element(By.CSS_SELECTOR, "span.commercial-option")
            row["Commercial Support?"] = commercial_span.text.strip()
        except Exception:
            row["Commercial Support?"] = ""

        try:
            general_tab = driver.find_element(
                By.CSS_SELECTOR,
                "div.tabs.activity div.tab[data-tab='general']"
            )
            h4_elems = general_tab.find_elements(By.TAG_NAME, "h4")
            for h in h4_elems:
                key = h.text.strip()
                if not key:
                    continue
                try:
                    p_elem = h.find_element(By.XPATH, "following-sibling::p[1]")
                    value = p_elem.text.strip()
                except Exception:
                    value = ""
                row[key] = value
        except Exception:
            pass

        data.append(row)
        df = pd.DataFrame(data)
        df.to_excel("ABMS_Providers.xlsx", index=False)

finally:
    driver.quit()

print("Scraping completed. Data saved to ABMS_Providers.xlsx")
