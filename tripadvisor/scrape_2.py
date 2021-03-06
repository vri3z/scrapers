"""
Scrape links naar attracties.

@author: Roel de Vries
@email: roel.de.vries@amsterdam.nl
"""
import re
from datetime import datetime as dt
from time import sleep

import bs4
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from tripadvisor.browser import Browser, scroll_into_view

BASE = 'https://www.tripadvisor.com'

XPATH_NEXT_BUTTON_1 = "//a[@class='nav next rndBtn ui_button primary taLnk']"
XPATH_NEXT_BUTTON_2 = "//a[@class='ui_button nav next primary ']"

XPATH_BUTTON_DISABLED = "//span[@class='ui_button nav next primary disabled']"

XPATH_LISTING_TITLE = "//div[@class='listing_title']/a"
XPATH_LISTING_TITLE_SPACE = "//div[@class='listing_title ']/a"
# XPATH_BUTTON_DISABLED = "//span[@class='nav next disabled']"

LOC_CATEGORY_ITEM = 'attractions-attraction-filtered-main-index__listItem--3trCl'


def _wait_for(driver, elem: str):
    try:
        element_present = ec.presence_of_element_located((By.XPATH, elem))
        WebDriverWait(driver, 1).until(element_present)
    except TimeoutException:
        print('Timed out waiting for page to load')


def get_provincie_from_url(url_str: str) -> str:
    if 'North_Holland' in url_str:
        return 'Noord-Holland'
    elif 'Flevoland' in url_str:
        return 'Flevoland'
    else:
        return ''


def strip_link(js_link: str) -> str:
    return re.search(r'[^*.]?(/Attraction[\w+-]+.html)', js_link, re.IGNORECASE).group(1)


def find_link(bs_obj: bs4.Tag) -> str:
    if not hasattr(bs_obj, 'attrs'):
        print('bs_obj betaat niet.')

    if 'href' in bs_obj.attrs:
        return strip_link(bs_obj.get('href'))

    elif 'onclick' in bs_obj.attrs:
        return strip_link(bs_obj.get('onclick'))

    else:
        print(bs_obj)
        return "GEEN LINK"


def find_price(bs_obj: bs4.Tag) -> float:
    from scrape_3 import extract_float

    price = bs_obj.find('div', {'class', 'attractions-ap-product-card-Attributes__priceFrom--2jhVp'})

    if price:
        price = price.get_text().split("€")

        try:
            price = price[1]
        except KeyError:
            price = -1

    return extract_float(price)


def find_title(bs_obj: bs4.Tag) -> str:
    title = bs_obj.find('a')
    return bs_obj.get_text(strip=True) if title else '< GEEN TITEL >'


def get_links(soup: bs4.BeautifulSoup, link: str) -> list:
    return [
        (
            find_title(i),
            find_price(i),
            find_link(i.find('a')),  # link to attractie
            dt.now().date(),
            'NEW',
            get_provincie_from_url(link),
            link
        )
        for i in soup.find_all('div', {'class': [
                lambda x: str(x).startswith('attractions-ap-product-card-ProductCard__productCard'),
                'attraction_element'
            ]
        })
    ]


def get_activities(category: tuple, browser: Browser) -> tuple:
    """Return list met attractie links."""
    link = category[1]
    browser.get(BASE + link)

    page_counter = 1

    while True:
        page_counter += 1

        # scroll_down(browser)
        scroll_into_view(
            [(By.XPATH, XPATH_NEXT_BUTTON_1), (By.XPATH, XPATH_NEXT_BUTTON_2), (By.XPATH, XPATH_BUTTON_DISABLED)],
            browser
        )

        data = get_links(bs4.BeautifulSoup(browser.driver.page_source, features='lxml'), link)

        for i in data:
            yield i

        button_disabled = browser.driver.find_elements_by_xpath(XPATH_BUTTON_DISABLED)
        next_button_enabled1 = browser.driver.find_elements_by_xpath(XPATH_NEXT_BUTTON_1)
        next_button_enabled2 = browser.driver.find_elements_by_xpath(XPATH_NEXT_BUTTON_2)

        if next_button_enabled1:
            next_button = XPATH_NEXT_BUTTON_1
        elif next_button_enabled2:
            next_button = XPATH_NEXT_BUTTON_2
        else:
            next_button = None
            if button_disabled:
                print("Einde categorie.")

        if not button_disabled and (next_button_enabled1 or next_button_enabled2):
            _wait_for(browser.driver, next_button)
            browser.driver.find_element_by_xpath(next_button).click()
            sleep(1)

            print(f'CLICK...   (pagina {page_counter})')

        else:
            break
