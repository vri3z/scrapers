#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main running class.

@author: Roel de Vries
@email: roel.de.vries@amsterdam.nl
"""
import os
from datetime import datetime

import pandas as pd
from selenium.webdriver import Chrome, ChromeOptions

import scrape_1
import scrape_2
import scrape_3


class Browser:
    """Class controlling the browser instance."""

    headless = False

    if os.name == 'nt':
        CHR_PATH = os.getcwd() + '//scripts//driver//chromedriver.exe'
    else:
        CHR_PATH = 'chromedriver/chromedriver'

    def _init_chrome(self, headless: bool = True) -> Chrome:
        chr_opt = ChromeOptions()
        chr_opt.headless = headless
        chr_opt.add_argument('log-level=2')
        chr_opt.add_argument('--disable-logging')
        chr_opt.add_argument('--disable-remote-fonts')
        chr_opt.add_argument('--incognito')

        if 'posix' in os.name:
            chr_opt.binary_location = 'chrome/chrome'
        chrome = Chrome(executable_path=self.CHR_PATH, options=chr_opt)
        chrome.set_window_size(1920, 1080)
        return chrome

    def __init__(self, headless=True):
        """Initialize browser."""
        self.headless = headless

    def __enter__(self):
        """Initialize driver."""
        self.driver = self._init_chrome(self.headless)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close and quit browser instance."""
        self.driver.close()
        self.driver.quit()
        print('Browser closed...')

    def restart(self):
        """Restart webdriver."""
        self.driver.close()
        print('Restarting browser...')
        self.__enter__()
        return self


def _datetime_now() -> str:
    return datetime.now().strftime('%d-%m-%Y %H%M')


def create_dataframe(s1: list, s2: list, s3: set) -> pd.DataFrame:
    """Create dataframe from scraped data."""
    df3 = pd.DataFrame(
        list(s3),
        columns=[
            'status',
            'titel',
            'attrac_url',
            'ta_id',
            'beoordeling',
            'adres',
            'pc_stad',
            'postcode',
            'plaats',
            'land',
            'aantal_reviews',
            'percentage_excellent',
            'percentage_verygood',
            'percentage_average',
            'percentage_poor',
            'percentage_terrible',
            'telefoon',
            'lat',
            'lon'
        ],
    )
    df2 = pd.DataFrame(s2, columns=['titel', 'attrac_url', 'added',
                                    'status', 'provincie', 'cat_url'])
    df1 = pd.DataFrame(
        s1, columns=['categorie', 'cat_url', 'added', 'status', 'provincie'])

    data = df3.merge(df2, how='left', on='attrac_url')
    data = data.merge(df1, how='left', on='cat_url')

    data.drop(
        columns=[c for c in data.columns if c.endswith('_y')] +
        ['status', 'cat_url'],
        inplace=True)
    data.rename(
        columns={c: c.rstrip('_x') for c in data.columns if c.endswith('_x')},
        inplace=True,
    )
    data['added'] = pd.to_datetime(data['added'])
    data['categorie'] = data['categorie'].astype('category')

    return data


def write_to_csv(data: pd.DataFrame):
    """Write csv file to disk."""
    print('writing csv for backup...')
    try:
        os.makedirs('results', exist_ok=True)
        time = _datetime_now()
        data.to_csv('results/attracties {0}.csv'.format(time), sep=';',
                    index=False)
    except Exception as e:
        print(e.__class__)
        print('writing csv failed...')


def pivot_categories(data: pd.DataFrame) -> pd.DataFrame:
    """Pivot categorie kolom in dataframe."""
    for c in data.categorie.unique():
        print(c)

    data = pd.get_dummies(data, columns=['categorie'])

    max_cols = [m for m in data.columns
                if m.startswith(('categorie_', 'percentage_')) or
                m == 'added' or m == 'aantal_reviews']

    rest_cols = [c for c in data.columns if c not in max_cols]

    data = data.groupby(rest_cols, as_index=False)[max_cols].max()
    print(data.info())

    try:
        data.set_index('attrac_url', verify_integrity=True)
    except ValueError:
        print('\nWARNING: Data bevat dubbele attracties / index niet uniek\n')
    return data


def _get_links_from_list(scrape_list: list, idx: int) -> list:
    return list({s[idx] for s in scrape_list})


def _running_time(start):
    now = datetime.now()
    print('\nrunning: {0:.0f} minute(s)...\n'.format(
        round((now - start).total_seconds() / 60, 0)))


def _print_item(idx: int, links, ta_link: str):
    print('[{0}/{1}] {2}'.format(idx + 1, len(links), ta_link))


def _sqlcol(dfparam):
    from sqlalchemy import Numeric, Date, String, Integer
    dtypedict = {}
    for c, d in zip(dfparam.columns, dfparam.dtypes):
        if 'object' in str(d):
            dtypedict.update({c: String()})
        if 'datetime' in str(d):
            dtypedict.update({c: Date()})
        if 'float' in str(d):
            dtypedict.update({c: Numeric()})
        if 'int' in str(d):
            dtypedict.update({c: Integer()})
        if c in ('lat', 'lon', 'beoordeling'):
            dtypedict.update({c: Numeric()})

    return dtypedict


def write_to_db(s1: list, s2: list, s3: set, data: pd.DataFrame) -> None:
    """Write lists with data to database."""
    from psql import Psql
    from Bases import Attractie, Activity, Categorie, SCHEMA

    db = Psql(SCHEMA).set_sess_maker().set_engine(echo=False)
    sessie = db.sessie_maker()
    engine = db.engine

    try:
        sessie.add_all([Categorie(*c) for c in s1])
        sessie.add_all([Activity(*a) for a in s2])
        sessie.add_all([Attractie(*a) for a in s3])
        sessie.commit()

    except Exception as ex:
        print(ex.__class__)
        sessie.rollback()
        raise

    finally:
        sessie.close()

    try:
        dtypes = _sqlcol(data)
        data.to_sql('Combined', engine, schema=SCHEMA,
                    if_exists='replace', index=False,
                    method='multi', chunksize=1000,
                    dtype=dtypes)

    except ValueError as e:
        print(e)
        print('FOUT: toevoegen combined mislukt.')


if __name__ == '__main__':

    begin = datetime.now()

    with Browser(headless=True) as browser:
        scrape1 = scrape_1.get_data(browser.driver)
        _running_time(begin)
        print(len(scrape1), 'categories')

    cat_links = _get_links_from_list(scrape1, 1)
    scrape2 = []

    with Browser(headless=True) as browser:
        for i, link in enumerate(cat_links):
            _print_item(i, cat_links, link)

            scrape2.extend(scrape_2.get_data(link, browser.driver))

        _running_time(begin)
        print(len(scrape2), 'activities')

    activ_list = _get_links_from_list(scrape2, 1)
    activ_list = [link for link in activ_list
                  if link.startswith('/Attraction_Review')]

    scrape3 = set()

    with Browser(headless=True) as browser:
        for i, link in enumerate(activ_list):
            _print_item(i, activ_list, link)

            scrape3.add(scrape_3.get_data(link, browser.driver))

            if i % 500 == 0 and i != 0 and i != 1:
                browser.restart()

            if i % 50 == 0 and i != 0 and i != 1:
                from time import sleep
                sleep(60)

        _running_time(begin)
        print(len(scrape3), 'attracties')

    df = create_dataframe(scrape1, scrape2, scrape3)
    df = pivot_categories(df)

    write_to_csv(df)

    write_to_db(scrape1, scrape2, scrape3, df)

    _running_time(begin)