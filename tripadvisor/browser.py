import os
import time
from pathlib import Path
from typing import Optional, List, Union, Tuple
from urllib.parse import urlparse

import bs4
import psutil
from selenium.common.exceptions import TimeoutException, NoSuchElementException, JavascriptException
from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.wait import WebDriverWait


def singleton(class_):
    instances = {}

    def getinstance(*args, **kwargs):
        if class_ not in instances:
            instances[class_] = class_(*args, **kwargs)
        return instances[class_]

    return getinstance


@singleton
class Browser:
    """Class controlling the browser instance."""

    headless = False
    _driver: Optional[WebDriver] = None

    def __init__(self, url: str = None, headless: bool = True, init: bool = True):
        """Initialize browser."""
        self.headless = headless

        if init and self._driver is None:
            self.kill_existing_drivers()
            self._driver = self._init_chrome()

            if url:
                self.get(url, ignore_errors=True)

    @property
    def driver(self) -> Optional[WebDriver]:
        return self._driver

    @property
    def running(self):
        if self._driver is None:
            return False

        from urllib3.exceptions import MaxRetryError
        from selenium.common.exceptions import WebDriverException

        try:
            if self._driver.title:
                return True

        except (WebDriverException, MaxRetryError):
            return False

    if os.name == 'nt':
        CHR_PATH = Path(r'C:\Users\Roel\PycharmProjects\scrapers\tripadvisor\driver\chromedriver.exe')
    else:
        # CHR_PATH = Path().home() / 'chromedriver' / 'chromedriver'
        CHR_PATH = '/home/vries274/scrapers/tripadvisor/chromedriver/chromedriver'

    @staticmethod
    def kill_existing_drivers():
        for proc in psutil.process_iter():
            name = proc.name()

            if 'chromedriver' in name or name == 'chrome.exe' or name == 'chrome':
                print(f'terminated process: {name} ({proc.pid})')
                proc.terminate()

    def _init_chrome(self, adblock: bool = False, incognito: bool = False) -> Chrome:
        empty_dir(str(Path.cwd() / 'chrome-data'))

        chr_opt = ChromeOptions()

        chr_opt.headless = self.headless
        chr_opt.add_argument("--no-sandbox")
        chr_opt.add_argument('log-level=2')
        chr_opt.add_argument('--disable-logging')
        chr_opt.add_argument('--disable-remote-fonts')
        chr_opt.add_argument("--user-data-dir=chrome-data")
        chr_opt.add_argument("--remote-debugging-port=9222")
        chr_opt.add_argument("--disable-infobars")
        chr_opt.add_argument("--disable-dev-shm-usage")
        chr_opt.add_argument("--ignore-certificate-errors")
        chr_opt.add_argument("--disable-gpu")

        if adblock and not self.headless:  # headless + extensions = crash
            chr_opt.add_extension(
                r'C:\Users\Roel\PycharmProjects\scrapers\tripadvisor\driver\ublock.crx.crx')
        if incognito:
            chr_opt.add_argument('--incognito')

        if 'posix' in os.name:
            chr_opt.binary_location = '/home/vries274/scrapers/tripadvisor/chrome/chrome-linux/chrome'

        chrome = Chrome(executable_path=self.CHR_PATH, options=chr_opt)
        chrome.set_window_size(1920, 1080)
        print('\n ---  Browser started  --- \n')
        return chrome

    def get(self, url: str, max_retry: int = 10, ignore_errors: bool = False):
        counter = 0
        print('getting url...', url, self.driver.current_url)

        while self._driver.current_url != url and counter < max_retry:
            self._driver.get(url)
            wait_for_document_ready_state(self)

            if ignore_errors:
                break
            else:
                counter += 1
                print('current url:', self._driver.current_url, f'({counter})')

    def restart(self):
        """Restart webdriver."""
        self.close()
        self.kill()
        self._driver = None

        print('Restarting browser...')
        self._driver = self._init_chrome(self.headless)
        return self

    def close(self):
        self._driver.close()

    def kill(self):
        if self.running:
            self._driver.close()
            self._driver.quit()
            print('Driver and browser closed...')

        else:
            self.kill_existing_drivers()

        self._driver = None


class Response:
    link: str
    _browser: Browser
    page_source: Optional[str]
    soup: Optional[bs4.BeautifulSoup]

    def __init__(self, link: str, headless: bool = True, init: bool = False):
        self.link = link
        self._browser = Browser(headless=headless, init=init)

    @property
    def link(self):
        return self._link

    @link.setter
    def link(self, value):
        def uri_validator(x):
            try:
                result = urlparse(x)
                return all([result.scheme, result.netloc, result.path])
            except:
                return False

        self._link = value if uri_validator(value) else None

    def get_response(self, wait_for_elements: List[tuple] = None):
        try:
            self._browser.driver.get(self.link)

        except:
            self.page_source = None

        else:
            wait_for_document_ready_state(self._browser, 'complete')

            if wait_for_elements:
                for el, time_out in wait_for_elements:
                    self.add_wait_for_element(el, time_out)

            self.page_source = self._browser.driver.page_source

    def create_soup(self):
        try:
            self.soup = bs4.BeautifulSoup(self._browser.driver.page_source, features='lxml')

        except TypeError:
            self.soup = None

    def add_wait_for_element(self, xpath_elem, time_out: int = 5):
        """Wait for element to appear on website (Silently fail)."""
        try:
            wait_for_document_ready_state(self._browser)
            element_present = ec.presence_of_element_located((By.XPATH, xpath_elem))
            WebDriverWait(self._browser.driver, time_out).until(element_present)

        except TimeoutException:
            # print(f'Timed out ({self.link}) ({xpath_elem})')
            pass

    def get_css_properties(self, elem, prop: str, by='xpath', pseudo: str = None) -> List:
        driver = self._browser.driver
        prop = f"var prop = \'{prop}\';" if prop else ''
        item = "return items[prop];" if prop else "return items;"
        pseudo = f"\'{pseudo}\'" if pseudo else 'null'

        if by == 'css':
            by = By.CSS_SELECTOR
        if by == 'xpath':
            by = By.XPATH

        results = []

        for el in elem:
            try:
                js = (
                    "var items = {};"
                    f"{prop}"
                    f"var compsty = getComputedStyle(arguments[0], {pseudo});"
                    "var len = compsty.length;"
                    "for (index = 0; index < len; index++)"
                    "   {items [compsty[index]] = compsty.getPropertyValue(compsty[index]);}"
                    f"{item}"
                )
                res = driver.execute_script(js, driver.find_element(by, el))

            except (NoSuchElementException, JavascriptException):
                pass

            else:
                results.append(res)

        return results

    def get_css_property(self, elem, prop, by=By.XPATH, pseudo: str = ''):
        driver = self._browser.driver
        return driver.execute_script(
            f"var prop = '{prop}';"
            f"var compsty = getComputedStyle(arguments[0], '{pseudo}');"
            f"return compsty.getPropertyValue(compsty[prop]);",
            driver.find_element(by, elem)
        )

    def get_property(self, elem, prop: str):
        driver = self._browser.driver
        elem = driver.find_element(By.XPATH, elem)
        return elem.get_property(prop)


def wait_for_document_ready_state(browser, wait_for: str = None, time_out: float = 0.1):
    try:
        ready_state = browser.driver.execute_script("return document.readyState;")

        while ready_state == 'loading':
            time.sleep(time_out)
            ready_state = browser.driver.execute_script("return document.readyState;")

            if wait_for and ready_state == wait_for:
                break

    except JavascriptException:
        print('Document Readystate ongeldig.')


def scroll_down(browser: Browser):
    # Get scroll height
    driver = browser.driver

    wait_for_document_ready_state(browser, 'complete')

    try:
        last_height = driver.execute_script("return document.body.scrollHeight;")
    except JavascriptException as j:
        print("poging 0: ", j)
        last_height = 0

    try_times = 0

    while True:
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except JavascriptException as j:
            print("Poging 1 (scrollen) : ", j)

        # Wait to load page
        wait_for_document_ready_state(browser)  # works: 0.75

        # Calculate new scroll height and compare with last scroll height
        try:
            new_height = driver.execute_script("return document.body.scrollHeight;")
        except JavascriptException as j:
            print("Poging 2 (nieuwe hoogte): ", j)
            new_height = 0

        if last_height == new_height:
            try_times += 1

        if try_times > 3 or last_height != new_height:
            break

        last_height = new_height


def hide_elements(elem: list, browser: Browser):
    try:
        str_elem = "'" + "', '".join(elem) + "'"
        print(f"trying to hide elements: {str_elem}")

        browser.driver.execute_script(
            f'var cls = [{str_elem}];' +
            """
            for (var i=0;i<cls.length;i++) {
                 var t = document.querySelector("."+cls[i])
                 if (t && t.style) {
                    document.querySelector("."+cls[i]).style.display = "none";
                 }
            }
            """
        )
    except JavascriptException as e_:
        print(e_)


def scroll_into_view(element: Union[tuple, List[Tuple]], browser: Browser):
    if isinstance(element, tuple):
        element = [element]

    wait_for_document_ready_state(browser)
    try:
        for el in element:
            browser.driver.execute_script(
                "return arguments[0].scrollIntoView();",
                browser.driver.find_element(*el)
            )

    except NoSuchElementException:
        pass
    except JavascriptException as j:
        print(j)


def empty_dir(dir_: str):
    import shutil
    print('removing ', dir_)
    shutil.rmtree(dir_)
